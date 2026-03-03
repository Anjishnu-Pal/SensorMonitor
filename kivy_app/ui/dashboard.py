"""
Dashboard screen showing live sensor readings
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.uix.progressbar import ProgressBar


class DashboardScreen(BoxLayout):
    """Live dashboard displaying current sensor readings"""
    
    def __init__(self, sensor_interface, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10
        
        self.sensor_interface = sensor_interface
        self.sensor_data = sensor_data
        
        # Title
        title = Label(text='SensorMonitor v1.02', size_hint_y=0.15, bold=True, font_size='20sp')
        self.add_widget(title)
        
        # Temperature Card
        temp_layout = BoxLayout(orientation='vertical', size_hint_y=0.25, padding=5)
        temp_layout.canvas.before.clear()
        self.temp_label = Label(text='Temperature\n-- °C', bold=True, font_size='18sp')
        self.temp_bar = ProgressBar(max=60, value=0)
        temp_layout.add_widget(self.temp_label)
        temp_layout.add_widget(self.temp_bar)
        self.add_widget(temp_layout)
        
        # pH Card
        ph_layout = BoxLayout(orientation='vertical', size_hint_y=0.25, padding=5)
        self.ph_label = Label(text='pH Level\n-- ', bold=True, font_size='18sp')
        self.ph_bar = ProgressBar(max=14, value=0)
        ph_layout.add_widget(self.ph_label)
        ph_layout.add_widget(self.ph_bar)
        self.add_widget(ph_layout)
        
        # Glucose Card
        glucose_layout = BoxLayout(orientation='vertical', size_hint_y=0.25, padding=5)
        self.glucose_label = Label(text='Glucose Level\n-- mg/dL', bold=True, font_size='18sp')
        self.glucose_bar = ProgressBar(max=250, value=0)
        glucose_layout.add_widget(self.glucose_label)
        glucose_layout.add_widget(self.glucose_bar)
        self.add_widget(glucose_layout)
        
        # Control buttons
        btn_layout = BoxLayout(size_hint_y=0.15, spacing=5)
        
        start_btn = Button(text='Start Monitoring')
        start_btn.bind(on_press=self.start_monitoring)
        btn_layout.add_widget(start_btn)
        
        stop_btn = Button(text='Stop Monitoring')
        stop_btn.bind(on_press=self.stop_monitoring)
        btn_layout.add_widget(stop_btn)
        
        self.add_widget(btn_layout)
        
        # Status label
        self.status_label = Label(
            text='Waiting for NHS 3152 sensor...', size_hint_y=None, height=25,
            font_size='12sp', color=(1, 0.8, 0.2, 1))
        self.add_widget(self.status_label)

        # Track whether any real data has arrived
        self._has_data = False

        # Auto-start monitoring after a short delay
        self.update_event = None
        Clock.schedule_once(self._auto_start, 1)

    def _auto_start(self, dt):
        """Auto-start monitoring on launch."""
        self.start_monitoring(None)

    def start_monitoring(self, instance):
        """Start monitoring sensors"""
        if self.update_event is None:
            self.update_event = Clock.schedule_interval(self.update_dashboard, 2)
            if not self._has_data:
                self.status_label.text = 'Scanning for NHS 3152 sensor...'
                self.status_label.color = (1, 0.8, 0.2, 1)
            else:
                self.status_label.text = 'Monitoring active — sensor connected'
                self.status_label.color = (0.5, 1, 0.5, 1)

    def stop_monitoring(self, instance):
        """Stop monitoring sensors"""
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
            self.status_label.text = 'Monitoring stopped'
            self.status_label.color = (1, 0.5, 0.5, 1)

    def _show_null_values(self):
        """Display null placeholder values for all three data types."""
        self.temp_label.text = 'Temperature\n-- °C'
        self.temp_bar.value = 0
        self.ph_label.text = 'pH Level\n--'
        self.ph_bar.value = 0
        self.glucose_label.text = 'Glucose Level\n-- mg/dL'
        self.glucose_bar.value = 0

    def update_dashboard(self, dt):
        """Update dashboard values from sensor readings."""
        readings = self.sensor_data.get_all_readings()
        if readings:
            latest = readings[-1]

            # First data arrival — update status
            if not self._has_data:
                self._has_data = True
                self.status_label.text = 'NHS 3152 sensor connected — live data'
                self.status_label.color = (0.3, 1, 0.3, 1)

            # Update temperature
            temp = latest.temperature
            self.temp_label.text = f'Temperature\n{temp:.1f} °C'
            self.temp_bar.value = max(0, min(temp, 60))

            # Update pH
            ph = latest.ph
            self.ph_label.text = f'pH Level\n{ph:.1f}'
            self.ph_bar.value = max(0, min(ph, 14.0))

            # Update Glucose
            glucose = latest.glucose
            self.glucose_label.text = f'Glucose Level\n{glucose:.1f} mg/dL'
            self.glucose_bar.value = max(30, min(glucose, 250))
        else:
            # No readings yet — show null values
            self._show_null_values()
            self.status_label.text = 'Waiting for NHS 3152 sensor...'
            self.status_label.color = (1, 0.8, 0.2, 1)
