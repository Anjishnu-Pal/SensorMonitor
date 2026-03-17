"""
NFC Handler - Enhanced lifecycle management for NHS 3152 sensor detection.
Handles initialization, lifecycle events, and robust Activity management.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ANDROID = False
try:
    from jnius import autoclass
    _ANDROID = True
except ImportError:
    _ANDROID = False


class NFCHandler:
    """
    Robust NFC handler with proper Android lifecycle management.
    Ensures reader mode is enabled/disabled at the right times.
    """
    
    def __init__(self, sensor_interface):
        self.sensor_interface = sensor_interface
        self._activity = None
        self._nfc_adapter = None
        self._reader_mode_enabled = False
        self._dispatch_initialized = False
        
    def initialize_nfc(self) -> bool:
        """
        Initialize NFC after Kivy app is fully loaded.
        Must be called from on_resume() or similar lifecycle method.
        """
        if not _ANDROID:
            logger.debug("Not on Android platform")
            return False
            
        try:
            # Get current Activity from multiple sources
            self._activity = self._get_activity()
            
            if not self._activity:
                logger.error("Could not obtain Android Activity")
                return False
            
            # Get NFC adapter
            if not self._get_nfc_adapter():
                logger.error("NFC adapter not available")
                return False
            
            # Set activity in sensor bridge
            if self.sensor_interface and self.sensor_interface.bridge:
                if self.sensor_interface.bridge._java_bridge:
                    self.sensor_interface.bridge._java_bridge.setActivity(self._activity)
                    logger.info("Activity set in Java SensorBridge")

            # Initialise foreground dispatch once per app lifespan.
            if not self._dispatch_initialized:
                if self.sensor_interface and self.sensor_interface.bridge:
                    self.sensor_interface.bridge.initForegroundDispatch()
                    self._dispatch_initialized = True

            # Enable foreground dispatch for this resume
            if self.sensor_interface and self.sensor_interface.bridge:
                self.sensor_interface.bridge.enableForegroundDispatch()

            # Try to connect
            if self.sensor_interface:
                success = self.sensor_interface.connect()
                if success:
                    logger.info("✓ NFC Handler: Successfully initialized NFC")
                else:
                    logger.warning("✗ NFC Handler: NFC initialization returned False")
                return success
            
            return False
            
        except Exception as e:
            logger.error(f"Error initializing NFC handler: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def on_android_resume(self) -> None:
        """Called when Android app resumes from background.

        Calls initialize_nfc() when reader mode is not yet active (first run or
        after a full disconnect), then ensures foreground dispatch is enabled.
        initForegroundDispatch() is guarded inside initialize_nfc() so it only
        ever runs once per app lifespan.
        """
        logger.debug("NFCHandler.on_android_resume() called")
        if not self._reader_mode_enabled:
            # Full re-initialise: sets up reader mode + foreground dispatch.
            self.initialize_nfc()
            return
        # Already initialised — just re-enable foreground dispatch.
        if self.sensor_interface and self.sensor_interface.bridge:
            self.sensor_interface.bridge.enableForegroundDispatch()

    def on_android_pause(self) -> None:
        """Called when Android app goes to background.

        Disables NFC foreground dispatch so other apps can receive intents.
        Disconnects the sensor and clears the reader-mode flag so
        on_android_resume() performs a full re-initialise.
        """
        logger.debug("NFCHandler.on_android_pause() called")
        self._reader_mode_enabled = False
        if self.sensor_interface and self.sensor_interface.bridge:
            self.sensor_interface.bridge.disableForegroundDispatch()
        if self.sensor_interface:
            self.sensor_interface.disconnect()

    def on_new_intent(self, intent) -> bool:
        """Handle an NFC intent delivered via foreground dispatch.

        Wire this to the p4a ``android.activity`` ``on_new_intent`` event
        (see ``main.py``).  The raw Java ``android.content.Intent`` object
        is passed straight through to the Java NDEF parsing pipeline.

        Parameters
        ----------
        intent : java.lang.Object (android.content.Intent via jnius)

        Returns
        -------
        bool — True when sensor data was parsed successfully.
        """
        logger.debug("NFCHandler.on_new_intent() called")
        if self.sensor_interface and self.sensor_interface.bridge:
            return self.sensor_interface.bridge.handleNfcIntent(intent)
        return False
    
    def _get_activity(self) -> Optional[object]:
        """Get Android Activity from multiple possible sources."""
        if not _ANDROID:
            return None
        
        # Try Method 1: PythonActivity (Kivy standard)
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            if hasattr(PythonActivity, 'mActivity'):
                activity = PythonActivity.mActivity
                if activity:
                    logger.debug("Got Activity from PythonActivity.mActivity")
                    return activity
        except Exception as e:
            logger.debug(f"Method 1 failed: {e}")
        
        # Try Method 2: From Kivy App
        try:
            from kivy.app import App
            app = App.get_running_app()
            if app:
                logger.debug("Got Kivy app instance")
                # Try to get from android module if available
                try:
                    from android import activity as android_activity
                    if hasattr(android_activity, 'PythonActivity'):
                        return android_activity.PythonActivity.mActivity
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Method 2 failed: {e}")
        
        # Try Method 3: Direct jnius autoclass
        try:
            Activity = autoclass('android.app.Activity')
            # This won't work directly, but we can try getting from context
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            return PythonActivity.mActivity
        except Exception as e:
            logger.debug(f"Method 3 failed: {e}")
        
        logger.warning("Could not obtain Activity from any method")
        return None
    
    def _get_nfc_adapter(self) -> bool:
        """Get and validate NFC adapter."""
        try:
            NfcAdapter = autoclass('android.nfc.NfcAdapter')
            self._nfc_adapter = NfcAdapter.getDefaultAdapter(self._activity)
            
            if self._nfc_adapter is None:
                logger.error("Device does not have NFC hardware")
                return False
            
            if not self._nfc_adapter.isEnabled():
                logger.warning("NFC is disabled — user must enable it in Settings")
                return False
            
            logger.debug("NFC adapter available and enabled")
            return True
            
        except Exception as e:
            logger.error(f"Error getting NFC adapter: {e}")
            return False
    
    def is_nfc_available(self) -> bool:
        """Check if NFC is available and enabled."""
        if not _ANDROID or not self._nfc_adapter:
            return False
        try:
            return self._nfc_adapter.isEnabled()
        except Exception:
            return False
    
    def get_nfc_status(self) -> str:
        """Get human-readable NFC status."""
        if not _ANDROID:
            return "Not on Android"
        
        if not self._activity:
            return "Activity not available"
        
        if not self._nfc_adapter:
            return "NFC hardware not available"
        
        try:
            if not self._nfc_adapter.isEnabled():
                return "NFC disabled in Settings"
            
            if self.sensor_interface and self.sensor_interface.connected:
                if self.sensor_interface.tag_detected:
                    return "✓ NHS 3152 Sensor Detected"
                else:
                    return "✓ NFC ready - waiting for sensor"
            
            return "NFC available but not connected"
        except Exception as e:
            return f"Error: {e}"
