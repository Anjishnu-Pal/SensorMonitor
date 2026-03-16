"""
Python-to-Java bridge using pyjnius for NFC communication with NHS 3152 sensor.
This module wraps the Java SensorBridge class so Python/Kivy can access Android NFC APIs.
"""

import os
import sys
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

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
            logger.debug("[SensorBridge] Not running on Android — mock mode enabled")

    def _init_android(self):
        """Initialize Java bridge on Android with the current Activity and NFC adapter."""
        try:
            # Try multiple ways to get the Android Activity
            self._activity = None
            
            # Method 1: Try PythonActivity (Kivy default)
            try:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                self._activity = PythonActivity.mActivity
                logger.info("[SensorBridge] Got activity from PythonActivity")
            except Exception:
                pass
            
            # Method 2: Try to get from Kivy app's root widget if Method 1 fails
            if self._activity is None:
                try:
                    from kivy.app import App
                    app = App.get_running_app()
                    if app and hasattr(app, 'android_activity'):
                        self._activity = app.android_activity
                        logger.info("[SensorBridge] Got activity from Kivy app")
                except Exception:
                    pass
            
            # Method 3: Use PythonService/Jnius to get from context
            if self._activity is None:
                try:
                    from android.app import PythonService
                    self._activity = PythonService.mService
                    logger.info("[SensorBridge] Got activity from PythonService")
                except Exception:
                    pass
            
            if self._activity is None:
                logger.error("[SensorBridge] ERROR: Could not obtain Android Activity reference")
                logger.error("[SensorBridge] DEBUG: This may happen if called before Kivy app is fully initialized")
                return

            # Get NFC adapter
            NfcAdapter = autoclass('android.nfc.NfcAdapter')
            self._nfc_adapter = NfcAdapter.getDefaultAdapter(self._activity)

            if self._nfc_adapter is None:
                logger.error("[SensorBridge] ERROR: Device does not have NFC hardware")
                return

            if not self._nfc_adapter.isEnabled():
                logger.warning("[SensorBridge] WARNING: NFC is disabled in device settings")

            # Instantiate the Java SensorBridge with the Activity
            JavaSensorBridge = autoclass('com.sensormonitor.android.SensorBridge')
            self._java_bridge = JavaSensorBridge(self._activity)

            logger.info("[SensorBridge] Android NFC bridge initialized successfully")

        except Exception as e:
            logger.error(f"[SensorBridge] Error initializing Android bridge: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            self._java_bridge = None

    def connect(self, config: Dict) -> bool:
        """Connect to NFC reader and enable reader mode for tag detection."""
        if _ANDROID and self._java_bridge:
            try:
                # If we have an activity, explicitly set it in the bridge
                if self._activity:
                    self._java_bridge.setActivity(self._activity)
                
                # Convert Python dict to Java HashMap
                HashMap = autoclass('java.util.HashMap')
                java_config = HashMap()
                for k, v in config.items():
                    java_config.put(str(k), str(v))

                result = self._java_bridge.connect(java_config)
                self._connected = bool(result)
                
                if self._connected:
                    logger.info(f"[SensorBridge] NFC connected. Reader mode active: {self._java_bridge.isReaderModeActive()}")
                else:
                    logger.warning("[SensorBridge] connect() returned False — check NFC hardware status")
                
                return self._connected
            except Exception as e:
                logger.error(f"[SensorBridge] connect error: {e}")
                import traceback
                logger.debug(traceback.format_exc())
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
                logger.error(f"[SensorBridge] disconnect error: {e}")
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
                logger.error(f"[SensorBridge] getSensorReading error: {e}")
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
                logger.error(f"[SensorBridge] updateConfig error: {e}")
                return False
        return False

    def calibrate(self) -> bool:
        """Calibrate sensors via NFC tag write."""
        if _ANDROID and self._java_bridge:
            try:
                return bool(self._java_bridge.calibrate())
            except Exception as e:
                logger.error(f"[SensorBridge] calibrate error: {e}")
                return False
        return False

    def testConnection(self) -> bool:
        """Test NFC connection and tag detection."""
        if _ANDROID and self._java_bridge:
            try:
                return bool(self._java_bridge.testConnection())
            except Exception as e:
                logger.error(f"[SensorBridge] testConnection error: {e}")
                return False
        return False

    def getFirmwareVersion(self) -> str:
        """Get NFC status / firmware version string."""
        if _ANDROID and self._java_bridge:
            try:
                version = self._java_bridge.getFirmwareVersion()
                return str(version) if version else "Unknown"
            except Exception as e:
                logger.error(f"[SensorBridge] getFirmwareVersion error: {e}")
                return "Error"
        return "NFC Bridge Not Available (Desktop Mode)"

    def isNfcAvailable(self) -> bool:
        """Check if NFC hardware is present and enabled."""
        if _ANDROID and self._nfc_adapter:
            try:
                return bool(self._nfc_adapter.isEnabled())
            except Exception as e:
                logger.error(f"[SensorBridge] isNfcAvailable error: {e}")
                return False
        return False

    def isConnected(self) -> bool:
        """Check if NFC bridge is connected."""
        return self._connected

    def getLastTagId(self) -> str:
        """Return the UID of the most recently scanned NFC tag as a hex string.

        Delegates to Java SensorBridge.getLastTagId().
        Returns an empty string when no tag has been seen yet.
        """
        if not (_ANDROID and self._java_bridge):
            return ""
        try:
            uid = self._java_bridge.getLastTagId()
            return str(uid) if uid else ""
        except Exception as e:
            logger.error(f"[SensorBridge] getLastTagId error: {e}")
            return ""

    def getLastDataAgeMs(self) -> int:
        """Return milliseconds since the last valid sensor data was parsed.

        Delegates to Java SensorBridge.getLastDataAgeMs().
        Returns a very large number when no data has ever been parsed OR
        when the tag left range and the Java periodic re-read cleared the data.
        Python uses this to stop displaying/storing once the threshold is exceeded.
        """
        if not (_ANDROID and self._java_bridge):
            return 2_147_483_647   # effectively infinite on non-Android
        try:
            age = self._java_bridge.getLastDataAgeMs()
            return int(age)
        except Exception as e:
            logger.error(f"[SensorBridge] getLastDataAgeMs error: {e}")
            return 2_147_483_647

    def initForegroundDispatch(self) -> bool:
        """
        Initialise the PendingIntent + IntentFilter arrays required by
        enableForegroundDispatch.  Must be called once the Activity is fully
        available (e.g. from on_start / after permissions are granted).

        Calls Java SensorBridge.initForegroundDispatch(Activity).
        """
        if not (_ANDROID and self._java_bridge and self._activity):
            logger.debug("[SensorBridge] initForegroundDispatch skipped — not on Android or no activity")
            return False
        try:
            self._java_bridge.initForegroundDispatch(self._activity)
            logger.info("[SensorBridge] initForegroundDispatch() OK")
            return True
        except Exception as e:
            logger.error(f"[SensorBridge] initForegroundDispatch error: {e}")
            return False

    def enableForegroundDispatch(self) -> bool:
        """
        Give this app priority over all others when an NFC tag is tapped.
        Call from App.on_resume() — after initForegroundDispatch() has run.

        Calls Java SensorBridge.enableForegroundDispatch().
        If NFC is off, the Java layer automatically sends the user to Settings.
        """
        if not (_ANDROID and self._java_bridge):
            return False
        try:
            self._java_bridge.enableForegroundDispatch()
            logger.info("[SensorBridge] enableForegroundDispatch() OK")
            return True
        except Exception as e:
            logger.error(f"[SensorBridge] enableForegroundDispatch error: {e}")
            return False

    def disableForegroundDispatch(self) -> bool:
        """
        Release foreground dispatch priority so other apps can receive NFC
        intents when this app is not in the foreground.
        Call from App.on_pause().

        Calls Java SensorBridge.disableForegroundDispatch().
        """
        if not (_ANDROID and self._java_bridge):
            return False
        try:
            self._java_bridge.disableForegroundDispatch()
            logger.info("[SensorBridge] disableForegroundDispatch() OK")
            return True
        except Exception as e:
            logger.error(f"[SensorBridge] disableForegroundDispatch error: {e}")
            return False

    def handleNfcIntent(self, intent) -> bool:
        """
        Route a Java Intent received in onNewIntent() to the Java parsing
        pipeline (NDEF extraction → RTD_TEXT decoding → binary fallback).

        Parameters
        ----------
        intent : java.lang.Object (android.content.Intent via jnius)
            The intent passed to the Activity's onNewIntent().

        Returns
        -------
        bool — True if sensor data was successfully parsed and stored.
        """
        if not (_ANDROID and self._java_bridge):
            return False
        if intent is None:
            return False
        try:
            result = bool(self._java_bridge.handleNfcIntent(intent))
            if result:
                logger.info("[SensorBridge] handleNfcIntent() parsed sensor data successfully")
            else:
                logger.debug("[SensorBridge] handleNfcIntent() — no sensor data in this intent")
            return result
        except Exception as e:
            logger.error(f"[SensorBridge] handleNfcIntent error: {e}")
            return False

    def promptEnableNfc(self) -> None:
        """Open the system NFC Settings screen so the user can enable NFC."""
        if not (_ANDROID and self._java_bridge):
            return
        try:
            self._java_bridge.promptEnableNfc()
        except Exception as e:
            logger.error(f"[SensorBridge] promptEnableNfc error: {e}")
