"""
Main screen for displaying sensor data
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock


class MainScreen(BoxLayout):
    """Main screen showing sensor data readings"""
    
    def __init__(self, csv_handler, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10
        
        self.csv_handler = csv_handler
        self.sensor_data = sensor_data
        
        # Title
        title = Label(text='Sensor Data Readings', size_hint_y=0.1, bold=True)
        self.add_widget(title)
        
        # Scrollable data display
        scroll = ScrollView()
        self.data_grid = GridLayout(cols=4, spacing=5, size_hint_y=None)
        self.data_grid.bind(minimum_height=self.data_grid.setter('height'))
        
        # Header row
        headers = ['Timestamp', 'Temperature (°C)', 'pH', 'Glucose (mg/dL)']
        for header in headers:
            self.data_grid.add_widget(
                Label(text=header, bold=True, size_hint_y=None, height=40)
            )
        
        scroll.add_widget(self.data_grid)
        self.add_widget(scroll)
        
        # Refresh button
        refresh_btn = Button(text='Refresh Data', size_hint_y=0.1)
        refresh_btn.bind(on_press=self.refresh_data)
        self.add_widget(refresh_btn)
        
        # Export button
        export_btn = Button(text='Export to CSV', size_hint_y=0.1)
        export_btn.bind(on_press=self.export_data)
        self.add_widget(export_btn)
        
        # Initial load + auto-refresh every 5 s
        Clock.schedule_once(self.refresh_data, 0)
        Clock.schedule_interval(self.refresh_data, 5.0)
    
    def refresh_data(self, instance=None):
        """Refresh displayed data"""
        self.data_grid.clear_widgets()
        
        # Re-add headers
        headers = ['Timestamp', 'Temperature (°C)', 'pH', 'Glucose (mg/dL)']
        for header in headers:
            self.data_grid.add_widget(
                Label(text=header, bold=True, size_hint_y=None, height=40)
            )
        
        # Load and display readings
        readings = self.sensor_data.get_all_readings()
        for reading in reversed(readings[-20:]):  # Show last 20 readings
            self.data_grid.add_widget(
                Label(text=str(reading.timestamp), size_hint_y=None, height=40)
            )
            self.data_grid.add_widget(
                Label(text=f"{reading.temperature:.2f}", size_hint_y=None, height=40)
            )
            self.data_grid.add_widget(
                Label(text=f"{reading.ph:.2f}", size_hint_y=None, height=40)
            )
            self.data_grid.add_widget(
                Label(text=f"{reading.glucose:.2f}", size_hint_y=None, height=40)
            )
    
    def export_data(self, instance):
        """Export all data to CSV"""
        try:
            self.csv_handler.export_all_data(self.sensor_data.get_all_readings())
            print("Data exported successfully")
        except Exception as e:
            print(f"Error exporting data: {e}")
