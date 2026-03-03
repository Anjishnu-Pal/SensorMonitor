"""
JNI Interface for Android sensor communication via NHS 3152 chip using NFC.
This interface communicates with native C/C++ code through JNI for NFC data exchange.
On non-Android platforms, falls back to mock data for development/testing.
"""

import os
import sys
from datetime import datetime
from typing import Optional, Dict
import random
import logging

logger = logging.getLogger(__name__)

# Detect if running on Android
_ANDROID = False
try:
    from jnius import autoclass
    _ANDROID = True
except ImportError:
    _ANDROID = False


class SensorInterface:
    """Interface for communicating with NHS 3152 sensor via NFC and JNI"""

    def __init__(self):
        self.connected = False
        self.nfc_enabled = False
        self.tag_detected = False  # True only after a real NFC tag is read
        self.bridge = None
        self.config = {
            'nfc_mode': True,
            'nfc_reader_presence_check': 250,  # milliseconds
            'nfc_timeout': 3000,  # milliseconds
            'temp_offset': 0.0,
            'ph_calibration': 7.0,
            'glucose_calibration': 100.0,
            'auto_detect': True,
        }

        # Initialize bridge
        self._init_bridge()

    def _init_bridge(self):
        """Initialize the sensor bridge (Java on Android, mock otherwise)."""
        try:
            from android_jni.sensor_bridge import SensorBridge
            self.bridge = SensorBridge()
            if _ANDROID:
                logger.info("NFC SensorBridge initialized (Android)")
            else:
                logger.info("SensorBridge in mock/desktop mode")
        except Exception as e:
            logger.warning(f"Could not initialize SensorBridge: {e}")
            self.bridge = None

    def connect(self) -> bool:
        """Establish NFC connection to NHS 3152 sensor tag."""
        try:
            if self.bridge and _ANDROID:
                result = self.bridge.connect(self.config)
                self.connected = result
                self.nfc_enabled = result
                if result:
                    logger.info("NFC connected to NHS 3152 sensor")
                else:
                    logger.warning("NFC connection failed")
                return result
            else:
                logger.info("No Android bridge — running in mock/test mode")
                self.connected = False
                return False
        except Exception as e:
            logger.error(f"Error connecting to NFC: {e}")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """Disconnect from sensor."""
        try:
            if self.bridge and _ANDROID:
                self.bridge.disconnect()
            self.connected = False
            self.nfc_enabled = False
            return True
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return False

    def read_sensor_data(self) -> Optional[Dict]:
        """
        Read current sensor data from NHS 3152 NFC tag.
        Returns None until a real NFC tag is detected and read.
        All three data values (temperature, pH, glucose) remain null
        in the UI until the NHS 3152 sensor is physically recognised.
        """
        # On Android, try real NFC reading
        if _ANDROID and self.bridge:
            if not self.connected:
                if not self.connect():
                    logger.debug("NFC not connected, no tag nearby")
                    return None

            try:
                sensor_data = self.bridge.getSensorReading()
                if sensor_data and len(sensor_data) >= 3:
                    self.tag_detected = True
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'temperature': float(sensor_data[0]),
                        'ph': float(sensor_data[1]),
                        'glucose': float(sensor_data[2]),
                    }
                else:
                    logger.debug("No NFC tag detected — waiting for tag...")
                    return None
            except Exception as e:
                logger.error(f"Error reading sensor data: {e}")
                return None
        else:
            # Desktop / no-hardware mode: no data until a real tag is present.
            # Use _get_mock_data() directly in unit tests.
            logger.debug("No NFC hardware — waiting for NHS 3152 sensor")
            return None

    def _get_mock_data(self) -> Dict:
        """Return mock sensor data for testing (no hardware).
        Ranges: temperature 0-60 °C, pH 0-14, glucose 30-250 mg/dL.
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'temperature': round(random.uniform(0, 60), 2),
            'ph': round(random.uniform(0, 14), 2),
            'glucose': round(random.uniform(30, 250), 1),
        }

    def update_configuration(self, config: Dict) -> bool:
        """Update sensor and NFC configuration."""
        try:
            self.config.update(config)
            if self.bridge and self.connected and _ANDROID:
                self.bridge.updateConfig(config)
            return True
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False

    def calibrate_sensors(self) -> bool:
        """Calibrate sensors via NFC (requires tag in range)."""
        try:
            if self.bridge and _ANDROID:
                return self.bridge.calibrate()
            return False
        except Exception as e:
            logger.error(f"Error during calibration: {e}")
            return False

    def test_connection(self) -> bool:
        """Test NFC reader connection and tag detection."""
        try:
            if not self.connected:
                if not self.connect():
                    return False
            if self.bridge and _ANDROID:
                return self.bridge.testConnection()
            return False
        except Exception as e:
            logger.error(f"Error testing connection: {e}")
            return False

    def get_nfc_status(self) -> str:
        """Get NFC reader and tag status."""
        try:
            if self.bridge:
                return self.bridge.getFirmwareVersion()
            return "NFC Bridge Not Available"
        except Exception as e:
            logger.error(f"Error getting NFC status: {e}")
            return "Error"

    def enable_nfc_reader_mode(self) -> bool:
        """Enable NFC reader mode for background tag scanning."""
        try:
            if self.bridge and self.connected and _ANDROID:
                self.nfc_enabled = True
                return True
            return False
        except Exception as e:
            logger.error(f"Error enabling NFC reader: {e}")
            return False

    def disable_nfc_reader_mode(self) -> bool:
        """Disable NFC reader mode."""
        try:
            if self.bridge and _ANDROID:
                self.nfc_enabled = False
                self.disconnect()
                return True
            return False
        except Exception as e:
            logger.error(f"Error disabling NFC reader: {e}")
            return False

    def is_nfc_available(self) -> bool:
        """Check if device has NFC hardware."""
        try:
            if self.bridge and _ANDROID:
                return self.bridge.isNfcAvailable()
            return False
        except Exception as e:
            logger.error(f"Error checking NFC availability: {e}")
            return False

    def is_nfc_enabled(self) -> bool:
        """Check if NFC is currently enabled."""
        return self.nfc_enabled

    def get_status(self) -> Dict:
        """Get complete sensor and NFC status."""
        return {
            'connected': self.connected,
            'nfc_enabled': self.nfc_enabled,
            'tag_detected': self.tag_detected,
            'nfc_status': self.get_nfc_status(),
            'config': self.config.copy(),
            'communication_mode': 'NFC',
            'platform': 'Android' if _ANDROID else 'Desktop/Test',
        }
