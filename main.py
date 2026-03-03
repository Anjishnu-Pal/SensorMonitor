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
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock

from kivy_app.ui.main_screen import MainScreen
from kivy_app.ui.dashboard import DashboardScreen
from kivy_app.ui.graphs import GraphsScreen
from kivy_app.ui.settings import SettingsScreen
from android_jni.sensor_interface import SensorInterface
from data_management.csv_handler import CSVHandler
from data_management.sensor_data import SensorData


class SensorMonitorApp(App):
    """Main Kivy application for sensor monitoring"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "SensorMonitor v1.02"
        self.sensor_interface = None
        self.csv_handler = None
        self.sensor_data = None
        self.data_update_event = None
        
    def build(self):
        """Build the main UI"""
        # Initialize sensor interface and data management
        self.sensor_interface = SensorInterface()
        self.csv_handler = CSVHandler()
        self.sensor_data = SensorData()
        
        # Create main tab panel
        main_layout = TabbedPanel()
        
        # Dashboard Tab
        dashboard_tab = TabbedPanelItem(text='Dashboard')
        dashboard_tab.content = DashboardScreen(
            sensor_interface=self.sensor_interface,
            sensor_data=self.sensor_data
        )
        main_layout.add_widget(dashboard_tab)
        
        # Data View Tab
        data_tab = TabbedPanelItem(text='Data')
        data_tab.content = MainScreen(
            csv_handler=self.csv_handler,
            sensor_data=self.sensor_data
        )
        main_layout.add_widget(data_tab)
        
        # Graphs Tab
        graphs_tab = TabbedPanelItem(text='Graphs')
        graphs_tab.content = GraphsScreen(
            csv_handler=self.csv_handler,
            sensor_data=self.sensor_data
        )
        main_layout.add_widget(graphs_tab)
        
        # Settings Tab
        settings_tab = TabbedPanelItem(text='Settings')
        settings_tab.content = SettingsScreen(
            sensor_interface=self.sensor_interface
        )
        main_layout.add_widget(settings_tab)
        
        # Attempt initial NFC connection
        Clock.schedule_once(self._initial_connect, 2)
        
        # Schedule periodic data updates
        self.data_update_event = Clock.schedule_interval(
            self.update_sensor_data, 2  # Poll every 2 seconds for responsive NFC
        )
        
        return main_layout
    
    def _initial_connect(self, dt):
        """Try to establish NFC connection after app start."""
        try:
            if self.sensor_interface.connect():
                logger.info("NFC connection established")
            else:
                logger.info("NFC not connected yet — will retry on data poll")
        except Exception as e:
            logger.warning(f"Initial NFC connect failed: {e}")

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
        """Handle Android pause (app goes to background)."""
        return True
    
    def on_resume(self):
        """Handle Android resume — re-enable NFC reader mode."""
        if self.sensor_interface:
            try:
                self.sensor_interface.connect()
            except Exception as e:
                logger.warning(f"Error resuming NFC: {e}")


if __name__ == '__main__':
    SensorMonitorApp().run()
