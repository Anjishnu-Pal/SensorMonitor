"""
Unit tests for SensorInterface and SensorBridge modules.
Tests run in desktop (mock) mode since Android NFC hardware is not available.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from android_jni.sensor_interface import SensorInterface
from android_jni.sensor_bridge import SensorBridge


class TestSensorBridgeDesktop(unittest.TestCase):
    """Test SensorBridge in desktop/mock mode (no Android)."""

    def test_bridge_creation(self):
        """Bridge should instantiate without errors on desktop."""
        bridge = SensorBridge()
        self.assertIsNotNone(bridge)

    def test_connect_returns_false(self):
        """connect() should return False on desktop (no NFC hardware)."""
        bridge = SensorBridge()
        result = bridge.connect({'nfc_mode': True})
        self.assertFalse(result)

    def test_get_sensor_reading_returns_none(self):
        """getSensorReading() should return None on desktop."""
        bridge = SensorBridge()
        self.assertIsNone(bridge.getSensorReading())

    def test_firmware_version_desktop(self):
        """getFirmwareVersion() should indicate desktop mode."""
        bridge = SensorBridge()
        version = bridge.getFirmwareVersion()
        self.assertIn('Not Available', version)

    def test_is_nfc_available_false(self):
        """isNfcAvailable() should return False on desktop."""
        bridge = SensorBridge()
        self.assertFalse(bridge.isNfcAvailable())

    def test_calibrate_returns_false(self):
        """calibrate() should return False on desktop."""
        bridge = SensorBridge()
        self.assertFalse(bridge.calibrate())

    def test_disconnect(self):
        """disconnect() should not raise on desktop."""
        bridge = SensorBridge()
        bridge.disconnect()  # Should not raise
        self.assertFalse(bridge.isConnected())


class TestSensorInterface(unittest.TestCase):
    """Test SensorInterface in desktop/mock mode."""

    def setUp(self):
        self.interface = SensorInterface()

    def test_creation(self):
        """SensorInterface should instantiate."""
        self.assertIsNotNone(self.interface)

    def test_connect_desktop(self):
        """connect() should return False on desktop."""
        result = self.interface.connect()
        self.assertFalse(result)

    def test_read_sensor_data_returns_none_without_tag(self):
        """read_sensor_data() should return None on desktop (no NFC tag)."""
        data = self.interface.read_sensor_data()
        self.assertIsNone(data)

    def test_tag_detected_initially_false(self):
        """tag_detected flag should be False before any NFC tag is read."""
        self.assertFalse(self.interface.tag_detected)

    def test_mock_data_helper_returns_valid_data(self):
        """_get_mock_data() should return data with all fields."""
        data = self.interface._get_mock_data()
        self.assertIsNotNone(data)
        self.assertIn('timestamp', data)
        self.assertIn('temperature', data)
        self.assertIn('ph', data)
        self.assertIn('glucose', data)

    def test_mock_data_ranges(self):
        """Mock data should be in plausible ranges."""
        data = self.interface._get_mock_data()
        self.assertIsNotNone(data)
        self.assertTrue(0 <= data['temperature'] <= 60)
        self.assertTrue(0 <= data['ph'] <= 14)
        self.assertTrue(30 <= data['glucose'] <= 250)

    def test_update_configuration(self):
        """update_configuration() should succeed."""
        result = self.interface.update_configuration({'temp_offset': 0.5})
        self.assertTrue(result)
        self.assertEqual(self.interface.config['temp_offset'], 0.5)

    def test_get_status(self):
        """get_status() should return a dict with expected keys."""
        status = self.interface.get_status()
        self.assertIn('connected', status)
        self.assertIn('nfc_enabled', status)
        self.assertIn('nfc_status', status)
        self.assertIn('config', status)
        self.assertIn('communication_mode', status)
        self.assertEqual(status['communication_mode'], 'NFC')

    def test_disconnect(self):
        """disconnect() should succeed."""
        result = self.interface.disconnect()
        self.assertTrue(result)
        self.assertFalse(self.interface.connected)

    def test_is_nfc_available_desktop(self):
        """is_nfc_available() should return False on desktop."""
        self.assertFalse(self.interface.is_nfc_available())

    def test_calibrate_desktop(self):
        """calibrate_sensors() should return False on desktop."""
        self.assertFalse(self.interface.calibrate_sensors())

    def test_test_connection_desktop(self):
        """test_connection() should return False on desktop."""
        self.assertFalse(self.interface.test_connection())


class TestSensorInterfaceDataFlow(unittest.TestCase):
    """Test end-to-end data flow from sensor_interface to sensor_data."""

    def test_no_data_without_tag(self):
        """read_sensor_data() returns None — no data stored without NFC tag."""
        from data_management.sensor_data import SensorData
        interface = SensorInterface()
        sensor_data = SensorData()

        data = interface.read_sensor_data()
        self.assertIsNone(data)
        self.assertEqual(len(sensor_data.get_all_readings()), 0)

    def test_mock_data_to_sensor_data(self):
        """Mock data (from helper) should be storable in SensorData."""
        from data_management.sensor_data import SensorData
        interface = SensorInterface()
        sensor_data = SensorData()

        data = interface._get_mock_data()
        self.assertIsNotNone(data)

        sensor_data.add_reading(data)
        readings = sensor_data.get_all_readings()
        self.assertEqual(len(readings), 1)
        self.assertIsInstance(readings[0].timestamp, datetime)

    def test_mock_data_to_csv(self):
        """Mock data (from helper) should be saveable to CSV."""
        import tempfile
        import shutil
        from data_management.csv_handler import CSVHandler

        temp_dir = tempfile.mkdtemp()
        try:
            interface = SensorInterface()
            csv_handler = CSVHandler(temp_dir)

            data = interface._get_mock_data()
            self.assertIsNotNone(data)

            result = csv_handler.save_sensor_reading(data)
            self.assertTrue(result)

            readings = csv_handler.load_sensor_readings()
            self.assertEqual(len(readings), 1)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()
