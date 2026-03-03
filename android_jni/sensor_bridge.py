"""
Python-to-Java bridge using pyjnius for NFC communication with NHS 3152 sensor.
This module wraps the Java SensorBridge class so Python/Kivy can access Android NFC APIs.
"""

import os
import sys
from typing import Optional, List, Dict

# Detect platform
_ANDROID = False
try:
    # On Android (Kivy/p4a), jnius is available
    from jnius import autoclass, cast, PythonJavaClass, java_method
    _ANDROID = True
except ImportError:
    _ANDROID = False


class SensorBridge:
    """
    Python wrapper around the Java SensorBridge class.
    Uses pyjnius on Android to access NFC hardware via the Java NFC APIs.
    Falls back to a mock implementation on non-Android platforms (for testing).
    """

    def __init__(self):
        self._java_bridge = None
        self._nfc_adapter = None
        self._activity = None
        self._connected = False
        self._last_sensor_data = None

        if _ANDROID:
            self._init_android()
        else:
            print("[SensorBridge] Not running on Android — mock mode enabled")

    def _init_android(self):
        """Initialize Java bridge on Android with the current Activity and NFC adapter."""
        try:
            # Get the current Android Activity from Kivy
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self._activity = PythonActivity.mActivity

            # Get NFC adapter
            NfcAdapter = autoclass('android.nfc.NfcAdapter')
            self._nfc_adapter = NfcAdapter.getDefaultAdapter(self._activity)

            if self._nfc_adapter is None:
                print("[SensorBridge] ERROR: Device does not have NFC hardware")
                return

            if not self._nfc_adapter.isEnabled():
                print("[SensorBridge] WARNING: NFC is disabled in device settings")

            # Instantiate the Java SensorBridge with the Activity
            JavaSensorBridge = autoclass('com.sensormonitor.android.SensorBridge')
            self._java_bridge = JavaSensorBridge(self._activity)

            print("[SensorBridge] Android NFC bridge initialized successfully")

        except Exception as e:
            print(f"[SensorBridge] Error initializing Android bridge: {e}")
            self._java_bridge = None

    def connect(self, config: Dict) -> bool:
        """Connect to NFC reader and enable reader mode for tag detection."""
        if _ANDROID and self._java_bridge:
            try:
                # Convert Python dict to Java HashMap
                HashMap = autoclass('java.util.HashMap')
                java_config = HashMap()
                for k, v in config.items():
                    java_config.put(str(k), str(v))

                result = self._java_bridge.connect(java_config)
                self._connected = bool(result)
                return self._connected
            except Exception as e:
                print(f"[SensorBridge] connect error: {e}")
                return False
        else:
            # Mock mode
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from NFC reader."""
        if _ANDROID and self._java_bridge:
            try:
                self._java_bridge.disconnect()
            except Exception as e:
                print(f"[SensorBridge] disconnect error: {e}")
        self._connected = False

    def getSensorReading(self) -> Optional[List[float]]:
        """
        Get the latest sensor reading from the Java bridge.
        Returns [temperature, ph, glucose] or None if no data available.
        """
        if _ANDROID and self._java_bridge:
            try:
                java_data = self._java_bridge.getSensorReading()
                if java_data is not None:
                    # Convert Java float[] to Python list
                    result = [float(java_data[i]) for i in range(len(java_data))]
                    self._last_sensor_data = result
                    return result
                return None
            except Exception as e:
                print(f"[SensorBridge] getSensorReading error: {e}")
                return None
        else:
            return None

    def updateConfig(self, config: Dict) -> bool:
        """Update sensor configuration via Java bridge."""
        if _ANDROID and self._java_bridge:
            try:
                HashMap = autoclass('java.util.HashMap')
                java_config = HashMap()
                for k, v in config.items():
                    java_config.put(str(k), str(v))
                return bool(self._java_bridge.updateConfig(java_config))
            except Exception as e:
                print(f"[SensorBridge] updateConfig error: {e}")
                return False
        return False

    def calibrate(self) -> bool:
        """Calibrate sensors via NFC tag write."""
        if _ANDROID and self._java_bridge:
            try:
                return bool(self._java_bridge.calibrate())
            except Exception as e:
                print(f"[SensorBridge] calibrate error: {e}")
                return False
        return False

    def testConnection(self) -> bool:
        """Test NFC connection and tag detection."""
        if _ANDROID and self._java_bridge:
            try:
                return bool(self._java_bridge.testConnection())
            except Exception as e:
                print(f"[SensorBridge] testConnection error: {e}")
                return False
        return False

    def getFirmwareVersion(self) -> str:
        """Get NFC status / firmware version string."""
        if _ANDROID and self._java_bridge:
            try:
                version = self._java_bridge.getFirmwareVersion()
                return str(version) if version else "Unknown"
            except Exception as e:
                print(f"[SensorBridge] getFirmwareVersion error: {e}")
                return "Error"
        return "NFC Bridge Not Available (Desktop Mode)"

    def isNfcAvailable(self) -> bool:
        """Check if NFC hardware is present and enabled."""
        if _ANDROID and self._nfc_adapter:
            try:
                return bool(self._nfc_adapter.isEnabled())
            except Exception as e:
                print(f"[SensorBridge] isNfcAvailable error: {e}")
                return False
        return False

    def isConnected(self) -> bool:
        """Check if NFC bridge is connected."""
        return self._connected
