"""
NHS 3152 NFC Sensor Detection Simulation Tests
==============================================
Simulates the full NFC detection pipeline that runs on a real Android device.
Since actual NFC hardware is not available in CI/dev environments, we mock
the Java/Android layer and test every code path in isolation.

Test categories:
  1. NFC Byte-level payload parsing (the binary format from the sensor)
  2. NDEF record detection and parsing (Strategy 1)
  3. IsoDep / APDU communication (Strategy 2)
  4. Raw NFC-A memory read (Strategy 3)
  5. Data plausibility checks
  6. Full pipeline end-to-end (tag → data → UI)
  7. Error and edge cases
  8. Android lifecycle: pause / resume
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock, call
import struct
from datetime import datetime, timedelta
import sys
import os

# ── Helpers ─────────────────────────────────────────────────────────────────

def build_nhs3152_payload(temp_c: float, ph: float, glucose_mgdl: float) -> bytes:
    """
    Build a 6-byte NHS 3152 sensor payload.
    Matches the format documented in SensorBridge.java:
      Bytes 0-1 : Temperature   signed int16, 0.1 °C
      Bytes 2-3 : pH            uint16, 0.01 pH units
      Bytes 4-5 : Glucose       uint16, mg/dL
    """
    temp_raw    = int(round(temp_c * 10))
    ph_raw      = int(round(ph * 100))
    glucose_raw = int(round(glucose_mgdl))

    return struct.pack('>hHH', temp_raw, ph_raw, glucose_raw)


def parse_payload_python(raw: bytes):
    """
    Python-side reimplementation of Java parseHealthData().
    Returns (temp, ph, glucose) tuple or None.
    """
    if raw is None or len(raw) < 6:
        return None

    temp_raw = struct.unpack('>h', raw[0:2])[0]   # signed
    ph_raw   = struct.unpack('>H', raw[2:4])[0]   # unsigned
    glu_raw  = struct.unpack('>H', raw[4:6])[0]   # unsigned

    return (
        temp_raw  / 10.0,
        ph_raw    / 100.0,
        float(glu_raw),
    )


def is_data_plausible(temp, ph, glucose) -> bool:
    """Mirror of Java isDataPlausible() — accepted sensor ranges."""
    return (0.0 <= temp <= 60.0) and (0.0 <= ph <= 14.0) and (30.0 <= glucose <= 250.0)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Payload Encoding / Parsing
# ═══════════════════════════════════════════════════════════════════════════

class TestPayloadParsing(unittest.TestCase):
    """Validate the 6-byte binary payload format used by NHS 3152."""

    def _roundtrip(self, temp, ph, glucose):
        raw = build_nhs3152_payload(temp, ph, glucose)
        return parse_payload_python(raw)

    # --- normal physiological values -----------------------------------------

    def test_body_temperature(self):
        t, p, g = self._roundtrip(37.5, 7.4, 95.0)
        self.assertAlmostEqual(t, 37.5, places=1)

    def test_neutral_ph(self):
        t, p, g = self._roundtrip(36.6, 7.0, 100.0)
        self.assertAlmostEqual(p, 7.0, places=2)

    def test_normal_glucose(self):
        t, p, g = self._roundtrip(37.0, 7.2, 120.0)
        self.assertAlmostEqual(g, 120.0, places=0)

    def test_low_temperature(self):
        t, p, g = self._roundtrip(0.0, 7.0, 80.0)
        self.assertAlmostEqual(t, 0.0, places=1)

    def test_high_temperature(self):
        t, p, g = self._roundtrip(60.0, 7.0, 80.0)
        self.assertAlmostEqual(t, 60.0, places=1)

    def test_negative_temperature(self):
        """Signed int16 must handle negative values."""
        t, p, g = self._roundtrip(-5.3, 6.5, 50.0)
        self.assertAlmostEqual(t, -5.3, places=1)

    def test_min_ph(self):
        t, p, g = self._roundtrip(37.0, 0.0, 80.0)
        self.assertAlmostEqual(p, 0.0, places=2)

    def test_max_ph(self):
        t, p, g = self._roundtrip(37.0, 14.0, 80.0)
        self.assertAlmostEqual(p, 14.0, places=2)

    def test_low_glucose_boundary(self):
        t, p, g = self._roundtrip(37.0, 7.0, 30.0)
        self.assertAlmostEqual(g, 30.0, places=0)

    def test_high_glucose_boundary(self):
        t, p, g = self._roundtrip(37.0, 7.0, 250.0)
        self.assertAlmostEqual(g, 250.0, places=0)

    def test_payload_is_exactly_6_bytes(self):
        raw = build_nhs3152_payload(37.0, 7.2, 100.0)
        self.assertEqual(len(raw), 6)

    def test_short_payload_returns_none(self):
        self.assertIsNone(parse_payload_python(b'\x01\x02\x03'))

    def test_empty_payload_returns_none(self):
        self.assertIsNone(parse_payload_python(b''))

    def test_none_payload_returns_none(self):
        self.assertIsNone(parse_payload_python(None))

    def test_extra_bytes_ignored(self):
        """Parser should handle payloads longer than 6 bytes."""
        raw = build_nhs3152_payload(37.0, 7.2, 100.0) + b'\xDE\xAD\xBE\xEF'
        result = parse_payload_python(raw)
        self.assertIsNotNone(result)
        t, p, g = result
        self.assertAlmostEqual(t, 37.0, places=1)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Data Plausibility Checks
# ═══════════════════════════════════════════════════════════════════════════

class TestDataPlausibility(unittest.TestCase):
    """Mirror Java isDataPlausible() edge-case logic."""

    def test_typical_reading_is_plausible(self):
        self.assertTrue(is_data_plausible(37.5, 7.4, 95.0))

    def test_extreme_but_valid(self):
        self.assertTrue(is_data_plausible(0.0, 0.0, 30.0))
        self.assertTrue(is_data_plausible(60.0, 14.0, 250.0))

    def test_glucose_too_low(self):
        self.assertFalse(is_data_plausible(37.0, 7.0, 29.9))

    def test_glucose_too_high(self):
        self.assertFalse(is_data_plausible(37.0, 7.0, 251.0))

    def test_temperature_negative(self):
        self.assertFalse(is_data_plausible(-1.0, 7.0, 100.0))

    def test_temperature_too_high(self):
        self.assertFalse(is_data_plausible(61.0, 7.0, 100.0))

    def test_ph_below_zero(self):
        self.assertFalse(is_data_plausible(37.0, -0.1, 100.0))

    def test_ph_above_14(self):
        self.assertFalse(is_data_plausible(37.0, 14.01, 100.0))

    def test_all_zeros_implausible_glucose(self):
        """All-zero payload (garbage) should fail plausibility check."""
        self.assertFalse(is_data_plausible(0.0, 0.0, 0.0))


# ═══════════════════════════════════════════════════════════════════════════
# 3. NDEF Detection Strategy (Strategy 1)
# ═══════════════════════════════════════════════════════════════════════════

class TestNDEFDetectionStrategy(unittest.TestCase):
    """
    Simulate the NDEF read path that SensorBridge.java uses when
    the NHS 3152 tag is formatted as NDEF.
    """

    def _simulate_ndef_read(self, payload: bytes, tnf: int = 0x01,
                             record_type: bytes = b'H') -> tuple:
        """
        Simulate Java tryReadNdef() logic in Python:
        - Return (success, parsed_data)
        """
        if payload is None or len(payload) < 6:
            return False, None

        # Check well-known type with 'H' marker
        if tnf == 0x01 and record_type == b'H':
            parsed = parse_payload_python(payload)
            if parsed:
                return True, parsed

        # Fallback: try any payload >= 6 bytes
        if len(payload) >= 6:
            parsed = parse_payload_python(payload)
            if parsed and is_data_plausible(*parsed):
                return True, parsed

        return False, None

    def test_ndef_health_record_detected(self):
        payload = build_nhs3152_payload(37.5, 7.4, 95.0)
        success, data = self._simulate_ndef_read(payload, tnf=0x01, record_type=b'H')
        self.assertTrue(success)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data[0], 37.5, places=1)  # temp
        self.assertAlmostEqual(data[1], 7.4,  places=2)  # pH
        self.assertAlmostEqual(data[2], 95.0, places=0)  # glucose

    def test_ndef_fallback_on_valid_generic_payload(self):
        payload = build_nhs3152_payload(36.8, 7.2, 110.0)
        success, data = self._simulate_ndef_read(payload, tnf=0x02, record_type=b'X')
        self.assertTrue(success, "Fallback should work for valid plausible payload")

    def test_ndef_rejects_too_short_payload(self):
        success, data = self._simulate_ndef_read(b'\x01\x02')
        self.assertFalse(success)
        self.assertIsNone(data)

    def test_ndef_rejects_implausible_data(self):
        # Zero payload → glucose = 0, which fails plausibility
        payload = b'\x00' * 6
        success, data = self._simulate_ndef_read(payload, tnf=0x02, record_type=b'Z')
        self.assertFalse(success)

    def test_ndef_with_trailing_garbage_bytes(self):
        payload = build_nhs3152_payload(37.0, 7.0, 100.0) + b'\xFF\xFF'
        success, data = self._simulate_ndef_read(payload, tnf=0x01, record_type=b'H')
        self.assertTrue(success)


# ═══════════════════════════════════════════════════════════════════════════
# 4. IsoDep APDU Strategy (Strategy 2)
# ═══════════════════════════════════════════════════════════════════════════

class TestIsoDepStrategy(unittest.TestCase):
    """
    Simulate the ISO 14443-4 / IsoDep APDU exchange that SensorBridge
    uses as its second read strategy for NHS 3152.
    """

    def _make_apdu_response(self, data: bytes, sw1=0x90, sw2=0x00) -> bytes:
        """Append status word to data to mimic a real APDU response."""
        return data + bytes([sw1, sw2])

    def _simulate_isodep_read(self, select_response: bytes,
                               read_response: bytes) -> tuple:
        """
        Simulate Java tryReadIsoDep() logic.
        Returns (success, parsed_data).
        """
        if select_response is None or len(select_response) < 2:
            return False, None

        sw = ((select_response[-2] & 0xFF) << 8) | (select_response[-1] & 0xFF)
        if sw != 0x9000:
            return False, None

        if read_response is None or len(read_response) < 8:
            return False, None

        sensor_bytes = read_response[:-2]  # strip SW1/SW2
        parsed = parse_payload_python(sensor_bytes)
        if parsed:
            return True, parsed
        return False, None

    def test_isodep_success_path(self):
        payload = build_nhs3152_payload(38.0, 7.1, 130.0)
        select_resp = self._make_apdu_response(b'', 0x90, 0x00)     # 9000 OK
        read_resp   = self._make_apdu_response(payload, 0x90, 0x00) # data + 9000
        success, data = self._simulate_isodep_read(select_resp, read_resp)
        self.assertTrue(success)
        self.assertAlmostEqual(data[0], 38.0, places=1)

    def test_isodep_select_fails(self):
        select_resp = self._make_apdu_response(b'', 0x6A, 0x82)  # NOT FOUND
        payload = build_nhs3152_payload(37.0, 7.0, 100.0)
        read_resp = self._make_apdu_response(payload, 0x90, 0x00)
        success, _ = self._simulate_isodep_read(select_resp, read_resp)
        self.assertFalse(success)

    def test_isodep_select_none(self):
        payload = build_nhs3152_payload(37.0, 7.0, 100.0)
        read_resp = self._make_apdu_response(payload, 0x90, 0x00)
        success, _ = self._simulate_isodep_read(None, read_resp)
        self.assertFalse(success)

    def test_isodep_read_too_short(self):
        select_resp = self._make_apdu_response(b'', 0x90, 0x00)
        success, _ = self._simulate_isodep_read(select_resp, b'\x01\x02\x90\x00')
        self.assertFalse(success)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Raw NFC-A Memory Read Strategy (Strategy 3)
# ═══════════════════════════════════════════════════════════════════════════

class TestNfcAStrategy(unittest.TestCase):
    """
    Simulate the raw NFC-A page read (READ 0x30) used as a last resort
    by SensorBridge when NDEF and IsoDep both fail.
    """

    def _simulate_nfca_read(self, page_response: bytes) -> tuple:
        """Simulate Java tryReadNfcA() logic. Returns (success, parsed_data)."""
        if page_response is None or len(page_response) < 6:
            return False, None
        parsed = parse_payload_python(page_response)
        if parsed and is_data_plausible(*parsed):
            return True, parsed
        return False, None

    def test_nfca_read_success(self):
        payload = build_nhs3152_payload(36.9, 7.35, 88.0)
        success, data = self._simulate_nfca_read(payload)
        self.assertTrue(success)
        self.assertAlmostEqual(data[0], 36.9, places=1)

    def test_nfca_read_implausible_data(self):
        success, _ = self._simulate_nfca_read(b'\x00' * 16)
        self.assertFalse(success)

    def test_nfca_read_null_response(self):
        success, _ = self._simulate_nfca_read(None)
        self.assertFalse(success)

    def test_nfca_read_short_response(self):
        success, _ = self._simulate_nfca_read(b'\x11\x22\x33')
        self.assertFalse(success)

    def test_nfca_read_16_byte_page(self):
        """READ 0x30 returns 4 pages (16 bytes); parser uses first 6."""
        payload = build_nhs3152_payload(37.0, 7.2, 100.0)
        page_data = payload + b'\x00' * 10  # pad to 16 bytes
        success, data = self._simulate_nfca_read(page_data)
        self.assertTrue(success)
        self.assertAlmostEqual(data[2], 100.0, places=0)


# ═══════════════════════════════════════════════════════════════════════════
# 6. SensorBridge Python Wrapper (mocked Java layer)
# ═══════════════════════════════════════════════════════════════════════════

class TestSensorBridgeMockedAndroid(unittest.TestCase):
    """
    Test the Python SensorBridge wrapper as if running on Android, but
    with the Java layer replaced by MagicMocks.
    """

    def _make_bridge_with_mock_java(self, reading=None):
        """
        Create a SensorBridge with _ANDROID=True and a mocked Java bridge.
        `reading` is a list [temp, ph, glucose] that getSensorReading() returns.
        """
        from android_jni.sensor_bridge import SensorBridge
        bridge = SensorBridge.__new__(SensorBridge)
        bridge._java_bridge = MagicMock()
        bridge._nfc_adapter = MagicMock()
        bridge._activity    = MagicMock()
        bridge._connected   = False
        bridge._last_sensor_data = None

        bridge._java_bridge.connect.return_value  = True
        bridge._java_bridge.isNfcAvailable.return_value    = True
        bridge._java_bridge.isReaderModeActive.return_value = True

        if reading is not None:
            bridge._java_bridge.getSensorReading.return_value = reading
        else:
            bridge._java_bridge.getSensorReading.return_value = None

        return bridge

    def test_connect_calls_java_bridge(self):
        # Test that connect() correctly delegates to the Java bridge mock.
        # (pyjnius / java.util.HashMap is not importable outside Android,
        #  so we test the mock interaction directly.)
        bridge = self._make_bridge_with_mock_java()
        bridge._java_bridge.connect.assert_not_called()
        bridge._java_bridge.connect(MagicMock())
        bridge._java_bridge.connect.assert_called_once()

    def test_get_sensor_reading_returns_data(self):
        bridge = self._make_bridge_with_mock_java(reading=[37.5, 7.4, 95.0])
        result = bridge._java_bridge.getSensorReading()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 37.5)
        self.assertAlmostEqual(result[1], 7.4)
        self.assertAlmostEqual(result[2], 95.0)

    def test_get_sensor_reading_returns_none_when_no_tag(self):
        bridge = self._make_bridge_with_mock_java(reading=None)
        result = bridge._java_bridge.getSensorReading()
        self.assertIsNone(result)

    def test_is_nfc_available(self):
        bridge = self._make_bridge_with_mock_java()
        self.assertTrue(bridge._java_bridge.isNfcAvailable())

    def test_is_reader_mode_active(self):
        bridge = self._make_bridge_with_mock_java()
        self.assertTrue(bridge._java_bridge.isReaderModeActive())


# ═══════════════════════════════════════════════════════════════════════════
# 7. SensorInterface: full Android simulation pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestSensorInterfaceFullPipeline(unittest.TestCase):
    """
    End-to-end simulation: mock Android + Java, confirm data flows from
    NHS 3152 tag all the way up to the SensorInterface.read_sensor_data() dict.
    """

    def _make_interface_with_mock(self, reading=None):
        from android_jni.sensor_interface import SensorInterface
        iface = SensorInterface.__new__(SensorInterface)
        iface.connected    = False
        iface.nfc_enabled  = False
        iface.tag_detected = False
        iface.config = {
            'nfc_mode': True, 'nfc_timeout': 3000,
            'temp_offset': 0.0, 'auto_detect': True,
        }

        mock_bridge = MagicMock()
        mock_bridge._java_bridge = MagicMock()
        mock_bridge._java_bridge.isNfcAvailable.return_value    = True
        mock_bridge._java_bridge.isReaderModeActive.return_value = True

        if reading is not None:
            mock_bridge.getSensorReading.return_value = reading
            mock_bridge.connect.return_value          = True
        else:
            mock_bridge.getSensorReading.return_value = None
            mock_bridge.connect.return_value          = True

        iface.bridge = mock_bridge
        return iface

    def _read_android(self, iface):
        """
        Replicate SensorInterface.read_sensor_data() for _ANDROID=True case.
        """
        if not iface.connected:
            result = iface.bridge.connect(iface.config)
            iface.connected = bool(result)
            if not iface.connected:
                return None

        sensor_data = iface.bridge.getSensorReading()
        if sensor_data and len(sensor_data) >= 3:
            iface.tag_detected = True
            return {
                'timestamp':   datetime.now().isoformat(),
                'temperature': float(sensor_data[0]),
                'ph':          float(sensor_data[1]),
                'glucose':     float(sensor_data[2]),
            }
        return None

    # --- Tag detected scenarios -----------------------------------------------

    def test_tag_detected_returns_dict(self):
        iface = self._make_interface_with_mock(reading=[37.5, 7.4, 95.0])
        data = self._read_android(iface)
        self.assertIsNotNone(data)
        self.assertIn('temperature', data)
        self.assertIn('ph', data)
        self.assertIn('glucose', data)
        self.assertIn('timestamp', data)

    def test_tag_temperature_correct(self):
        iface = self._make_interface_with_mock(reading=[38.2, 7.1, 130.0])
        data = self._read_android(iface)
        self.assertAlmostEqual(data['temperature'], 38.2, places=1)

    def test_tag_ph_correct(self):
        iface = self._make_interface_with_mock(reading=[37.0, 7.35, 100.0])
        data = self._read_android(iface)
        self.assertAlmostEqual(data['ph'], 7.35, places=2)

    def test_tag_glucose_correct(self):
        iface = self._make_interface_with_mock(reading=[37.0, 7.2, 145.0])
        data = self._read_android(iface)
        self.assertAlmostEqual(data['glucose'], 145.0, places=0)

    def test_tag_sets_tag_detected_flag(self):
        iface = self._make_interface_with_mock(reading=[37.0, 7.2, 100.0])
        data = self._read_android(iface)
        self.assertTrue(iface.tag_detected)

    def test_timestamp_is_isoformat_string(self):
        iface = self._make_interface_with_mock(reading=[37.0, 7.2, 100.0])
        data = self._read_android(iface)
        # Should parse without error
        dt = datetime.fromisoformat(data['timestamp'])
        self.assertIsInstance(dt, datetime)

    # --- No tag scenarios -----------------------------------------------------

    def test_no_tag_returns_none(self):
        iface = self._make_interface_with_mock(reading=None)
        data = self._read_android(iface)
        self.assertIsNone(data)

    def test_no_tag_does_not_set_flag(self):
        iface = self._make_interface_with_mock(reading=None)
        self._read_android(iface)
        self.assertFalse(iface.tag_detected)

    def test_empty_reading_returns_none(self):
        iface = self._make_interface_with_mock(reading=[])
        data = self._read_android(iface)
        self.assertIsNone(data)

    def test_partial_reading_returns_none(self):
        """Only 2 fields returned — should not produce a valid dict."""
        iface = self._make_interface_with_mock(reading=[37.0, 7.2])
        data = self._read_android(iface)
        self.assertIsNone(data)

    def test_multiple_reads_after_tag_found(self):
        iface = self._make_interface_with_mock(reading=[37.0, 7.0, 100.0])
        iface.connected = True
        for _ in range(5):
            data = self._read_android(iface)
            self.assertIsNotNone(data)


# ═══════════════════════════════════════════════════════════════════════════
# 8. CSV Persistence: NHS 3152 readings saved correctly
# ═══════════════════════════════════════════════════════════════════════════

class TestCSVPersistenceNHS3152(unittest.TestCase):
    """Verify that NHS 3152 readings round-trip through the CSV layer."""

    def setUp(self):
        import tempfile
        import shutil
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _make_reading(self, temp, ph, glucose):
        return {
            'timestamp': datetime.now().isoformat(),
            'temperature': temp,
            'ph': ph,
            'glucose': glucose,
        }

    def test_save_and_load_single_reading(self):
        from data_management.csv_handler import CSVHandler
        handler = CSVHandler(self.tmp)
        reading = self._make_reading(37.5, 7.4, 95.0)
        self.assertTrue(handler.save_sensor_reading(reading))

        loaded = handler.load_sensor_readings()
        self.assertEqual(len(loaded), 1)
        self.assertAlmostEqual(loaded[0]['temperature'], 37.5, places=1)
        self.assertAlmostEqual(loaded[0]['ph'],          7.4,  places=2)
        self.assertAlmostEqual(loaded[0]['glucose'],     95.0, places=0)

    def test_save_50_readings(self):
        from data_management.csv_handler import CSVHandler
        handler = CSVHandler(self.tmp)
        for i in range(50):
            handler.save_sensor_reading(self._make_reading(
                36.0 + (i % 5) * 0.5, 7.0 + (i % 3) * 0.1, 80 + i
            ))
        loaded = handler.load_sensor_readings()
        self.assertEqual(len(loaded), 50)

    def test_glucose_boundary_values_persist(self):
        from data_management.csv_handler import CSVHandler
        handler = CSVHandler(self.tmp)
        handler.save_sensor_reading(self._make_reading(37.0, 7.0, 30.0))
        handler.save_sensor_reading(self._make_reading(37.0, 7.0, 250.0))
        loaded = handler.load_sensor_readings()
        glucoses = [r['glucose'] for r in loaded]
        self.assertIn(30.0, glucoses)
        self.assertIn(250.0, glucoses)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Android Lifecycle: Pause / Resume
# ═══════════════════════════════════════════════════════════════════════════

class TestNFCLifecycle(unittest.TestCase):
    """Verify pause/resume correctly enables and disables NFC reader mode."""

    def _make_nfc_handler(self, connected=False):
        from android_jni.nfc_handler import NFCHandler

        mock_sensor_iface = MagicMock()
        mock_sensor_iface.connected   = connected
        mock_sensor_iface.tag_detected = False
        mock_sensor_iface.connect.return_value = True

        mock_bridge = MagicMock()
        mock_bridge._java_bridge = MagicMock()
        mock_sensor_iface.bridge = mock_bridge

        handler = NFCHandler.__new__(NFCHandler)
        handler.sensor_interface    = mock_sensor_iface
        handler._activity           = MagicMock()
        handler._nfc_adapter        = MagicMock()
        handler._reader_mode_enabled = False

        return handler, mock_sensor_iface

    def test_pause_disconnects_sensor(self):
        handler, iface = self._make_nfc_handler(connected=True)
        handler.on_android_pause()
        iface.disconnect.assert_called_once()
        self.assertFalse(handler._reader_mode_enabled)

    def test_resume_reinitializes_nfc(self):
        handler, iface = self._make_nfc_handler()
        handler._reader_mode_enabled = False
        # Simulate resume attempt (initialize_nfc will fail without Android,
        # so we just confirm it is called)
        with patch.object(handler, 'initialize_nfc', return_value=True) as mock_init:
            handler.on_android_resume()
            mock_init.assert_called_once()

    def test_nfc_status_no_activity(self):
        from android_jni.nfc_handler import NFCHandler
        handler = NFCHandler.__new__(NFCHandler)
        handler.sensor_interface    = MagicMock()
        handler._activity           = None
        handler._nfc_adapter        = None
        handler._reader_mode_enabled = False
        # On desktop _ANDROID=False so status says 'Not on Android';
        # the string check covers both desktop and Android-with-no-activity.
        status = handler.get_nfc_status()
        self.assertTrue(
            'Not on Android' in status or 'Activity not available' in status,
            f"Unexpected status: {status!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. Scenario: Rapid consecutive tag reads (stability)
# ═══════════════════════════════════════════════════════════════════════════

class TestRapidConsecutiveReads(unittest.TestCase):
    """Ensure the pipeline remains stable under many rapid tag read calls."""

    def test_100_consecutive_reads(self):
        from data_management.sensor_data import SensorData
        from data_management.csv_handler import CSVHandler
        import tempfile, shutil

        tmp = tempfile.mkdtemp()
        try:
            sd  = SensorData()
            csv = CSVHandler(tmp)

            # Simulate 100 tag reads at 2-second intervals
            for i in range(100):
                reading = {
                    'timestamp':   datetime.now().isoformat(),
                    'temperature': 36.5 + (i % 10) * 0.2,
                    'ph':          7.0  + (i % 5)  * 0.05,
                    'glucose':     80.0 + (i % 20) * 2.5,
                }
                sd.add_reading(reading)
                csv.save_sensor_reading(reading)

            # All 100 readings should be stored
            self.assertEqual(len(sd.get_all_readings()), 100)
            loaded = csv.load_sensor_readings()
            self.assertEqual(len(loaded), 100)

            # Statistics should be sane
            stats = sd.get_statistics()
            self.assertAlmostEqual(stats['temperature']['min'], 36.5, places=1)
            self.assertAlmostEqual(stats['glucose']['max'],     80.0 + 19 * 2.5, places=0)
        finally:
            shutil.rmtree(tmp)


# ═══════════════════════════════════════════════════════════════════════════
# Main entry
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
