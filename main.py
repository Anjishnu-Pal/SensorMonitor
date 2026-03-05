"""
SensorMonitor: Mobile App for Health Sensor Data Monitoring
Monitors Temperature, pH, and Glucose levels using NHS 3152 sensors via NFC.
Works on Android with real NFC hardware, or on desktop with mock data.
"""

import os
import sys
import logging

# Configure logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('SensorMonitor')

from kivy.app import App
from kivy.core.window import Window
Window.title = "SensorMonitor v1.03"
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock

from kivy_app.ui.main_screen import MainScreen
from kivy_app.ui.dashboard import DashboardScreen
from kivy_app.ui.graphs import GraphsScreen
from kivy_app.ui.settings import SettingsScreen
from kivy_app.ui.permission_screen import PermissionScreen
from android_jni.sensor_interface import SensorInterface
from android_jni.nfc_handler import NFCHandler
from android_jni.permission_manager import PermissionManager
from data_management.csv_handler import CSVHandler
from data_management.sensor_data import SensorData

# Detect Android platform (same pattern used across android_jni modules)
_ANDROID = False
try:
    from jnius import autoclass as _autoclass  # noqa: F401 — import for side-effect check
    _ANDROID = True
except ImportError:
    pass


class SensorMonitorApp(App):
    """Main Kivy application for sensor monitoring"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "SensorMonitor v1.03"
        self.sensor_interface = None
        self.nfc_handler = None
        self.csv_handler = None
        self.sensor_data = None
        self.data_update_event = None
        self.permission_manager = None
        # Root container; permission overlay lives here before the main UI
        self._root = FloatLayout()

    def build(self):
        """
        Build the root layout.

        On Android the app shows a full-screen permission overlay first.
        On desktop (or when all permissions are already granted) it goes
        straight to the tabbed main UI.
        """
        self.permission_manager = PermissionManager()

        # Check whether we need to ask for permissions at all.
        # On desktop _ANDROID is False so all permissions are pre-granted.
        if self.permission_manager.are_critical_permissions_granted():
            logger.info("All critical permissions already granted — skipping overlay")
            self._build_main_ui()
        else:
            logger.info("Showing permission request overlay")
            self._show_permission_screen()

        return self._root

    # ── Permission flow ──────────────────────────────────────────────────────

    def _show_permission_screen(self) -> None:
        """Add the permission overlay on top of the (empty) root layout."""
        perm_screen = PermissionScreen(
            permission_manager=self.permission_manager,
            on_complete=self._on_permissions_complete,
            size_hint=(1, 1)
        )
        self._root.add_widget(perm_screen)

    def _on_permissions_complete(self, granted: bool, results: dict) -> None:
        """
        Called by PermissionScreen once the user has responded.
        Remove the overlay and build the main UI regardless of the result —
        the app degrades gracefully when permissions are denied.
        """
        logger.info(
            f"Permission flow complete — critical granted: {granted}  "
            f"details: { {k.split('.')[-1]: v for k, v in results.items()} }"
        )
        # Remove permission overlay
        self._root.clear_widgets()
        # Build the main tabbed UI
        self._build_main_ui()

    # ── Main UI ──────────────────────────────────────────────────────────────

    def _build_main_ui(self) -> None:
        """Initialise services and build the tabbed panel UI."""
        # Services
        self.sensor_interface = SensorInterface()
        self.csv_handler = CSVHandler()
        self.sensor_data = SensorData()
        self.nfc_handler = NFCHandler(self.sensor_interface)

        # Tab panel
        main_layout = TabbedPanel()

        self.dashboard_screen = DashboardScreen(
            sensor_interface=self.sensor_interface,
            sensor_data=self.sensor_data
        )
        dashboard_tab = TabbedPanelItem(text='Dashboard')
        dashboard_tab.content = self.dashboard_screen
        main_layout.add_widget(dashboard_tab)

        data_tab = TabbedPanelItem(text='Raw Data')
        data_tab.content = MainScreen(
            csv_handler=self.csv_handler,
            sensor_data=self.sensor_data
        )
        main_layout.add_widget(data_tab)

        graphs_tab = TabbedPanelItem(text='Graphs')
        graphs_tab.content = GraphsScreen(
            csv_handler=self.csv_handler,
            sensor_data=self.sensor_data
        )
        main_layout.add_widget(graphs_tab)

        settings_tab = TabbedPanelItem(text='Settings')
        settings_tab.content = SettingsScreen(
            sensor_interface=self.sensor_interface,
            permission_manager=self.permission_manager,
            csv_handler=self.csv_handler
        )
        main_layout.add_widget(settings_tab)

        self._root.add_widget(main_layout)

        # ── Android NFC lifecycle binding ────────────────────────────────────
        # Use p4a's android.activity EventDispatcher to receive onNewIntent
        # callbacks when an NFC tag is tapped while the app is in the foreground.
        # This is the correct Python-side hook for foreground dispatch intents.
        if _ANDROID:
            try:
                from android import activity as _android_activity
                _android_activity.bind(on_new_intent=self._on_android_new_intent)
                logger.info("Bound android.activity on_new_intent")
            except Exception as _e:
                logger.warning(f"Could not bind android.activity on_new_intent: {_e}")

        # NFC initialisation (staggered to let Kivy render first)
        Clock.schedule_once(self._setup_nfc, 0.5)
        Clock.schedule_once(self._initial_connect, 2)

        self.data_update_event = Clock.schedule_interval(
            self.update_sensor_data, 2
        )

    def _on_android_new_intent(self, intent) -> None:
        """Receive NFC intents from the foreground dispatch system.

        When an intent resolves to sensor data we:
        1. Save immediately to CSV + JSON tap history (tap-triggered storage).
        2. Add to the in-memory SensorData model.
        3. Notify the Dashboard's 'Last Captured Data' card.
        """
        logger.info("on_new_intent received — routing to NFC handler")
        if not self.nfc_handler:
            return
        parsed = self.nfc_handler.on_new_intent(intent)
        if not parsed:
            logger.debug("NFC intent: no recognised sensor data")
            return

        # ── Tap-triggered storage ────────────────────────────────────
        data = self.sensor_interface.read_sensor_data()
        if data:
            # In-memory model
            self.sensor_data.add_reading(data)
            # Persistent CSV row
            if self.csv_handler:
                self.csv_handler.save_sensor_reading(data)
                # Persistent JSON tap event (SharedPreferences equivalent)
                self.csv_handler.save_tap_event(data)
            # Notify Dashboard 'Last Captured Data' card
            if hasattr(self, 'dashboard_screen') and self.dashboard_screen:
                self.dashboard_screen.notify_tap(data)
            logger.info(
                f"NFC tap stored — Temp: {data.get('temperature')} °C  "
                f"pH: {data.get('ph')}  Glu: {data.get('glucose')} mg/dL  "
                f"Tag: {data.get('tag_id', 'N/A')}")
        else:
            logger.warning("NFC intent parsed but read_sensor_data() returned None")

    def _initial_connect(self, dt):
        """Try to establish NFC connection after app start."""
        try:
            if self.nfc_handler:
                self.nfc_handler.initialize_nfc()
            elif self.sensor_interface and self.sensor_interface.connect():
                logger.info("NFC connection established")
        except Exception as e:
            logger.warning(f"Initial NFC connect failed: {e}")

    def _setup_nfc(self, dt):
        """Early NFC setup attempt during build."""
        try:
            if self.nfc_handler:
                self.nfc_handler.initialize_nfc()
        except Exception as e:
            logger.debug(f"Early NFC setup not ready yet: {e}")

    def update_sensor_data(self, dt):
        """Periodically poll for sensor data via NFC."""
        try:
            data = self.sensor_interface.read_sensor_data()
            
            if data:
                # Store in sensor data object
                self.sensor_data.add_reading(data)
                
                # Save to CSV
                self.csv_handler.save_sensor_reading(data)
                
        except Exception as e:
            logger.error(f"Error updating sensor data: {e}")
    
    def on_stop(self):
        """Clean up on app stop."""
        if self.data_update_event:
            self.data_update_event.cancel()
        if self.sensor_interface:
            try:
                self.sensor_interface.disconnect()
            except Exception:
                pass
        logger.info("SensorMonitor stopped")
    
    def on_pause(self):
        """Handle Android pause — disable NFC foreground dispatch."""
        logger.info("App going to background — disabling foreground dispatch")
        if self.nfc_handler:
            self.nfc_handler.on_android_pause()
        return True

    def on_resume(self):
        """Handle Android resume — re-enable NFC foreground dispatch."""
        logger.info("App resuming from background — enabling foreground dispatch")
        if self.nfc_handler:
            self.nfc_handler.on_android_resume()
        elif self.sensor_interface:
            try:
                self.sensor_interface.connect()
            except Exception as e:
                logger.warning(f"Error resuming NFC: {e}")


if __name__ == '__main__':
    SensorMonitorApp().run()
