"""
Dashboard screen showing live sensor readings
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, RoundedRectangle
from datetime import datetime


class _Card(BoxLayout):
    """A rounded-rect container for grouping related sensor widgets."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.18, 0.18, 0.22, 1)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size


class DashboardScreen(BoxLayout):
    """Live dashboard displaying current sensor readings, scan controls,
    and a 'Last Captured Data' card updated on every NFC tap."""

    def __init__(self, sensor_interface, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 8

        self.sensor_interface = sensor_interface
        self.sensor_data = sensor_data
        self._has_data = False
        self.update_event = None

        # ── Title ─────────────────────────────────────────────────────────────
        title = Label(text='SensorMonitor v1.04',
                      size_hint_y=0.08, bold=True, font_size='20sp')
        self.add_widget(title)

        # ── NFC Status Bar ─────────────────────────────────────────────
        self.status_label = Label(
            text='Waiting for NHS 3152 sensor...',
            size_hint_y=0.06, font_size='12sp', color=(1, 0.8, 0.2, 1))
        self.add_widget(self.status_label)

        # ── SCAN NFC Button (prominent) ────────────────────────────────
        scan_btn = Button(
            text='\U0001f4f6  SCAN NFC',
            size_hint_y=0.10,
            font_size='18sp', bold=True,
            background_color=(0.18, 0.55, 1, 1))
        scan_btn.bind(on_press=self._on_scan_pressed)
        self.add_widget(scan_btn)

        # ── Live Readings (progress-bar cards) ──────────────────────────
        readings_card = _Card(
            orientation='vertical', size_hint_y=0.30, padding=6, spacing=4)

        readings_card.add_widget(
            Label(text='Live Readings', bold=True, size_hint_y=None,
                  height=22, font_size='13sp', color=(0.7, 0.9, 1, 1)))

        temp_row = BoxLayout(size_hint_y=None, height=42, spacing=6)
        self.temp_label = Label(text='Temp: -- °C', size_hint_x=0.35, font_size='14sp')
        self.temp_bar   = ProgressBar(max=60, value=0, size_hint_x=0.65)
        temp_row.add_widget(self.temp_label)
        temp_row.add_widget(self.temp_bar)
        readings_card.add_widget(temp_row)

        ph_row = BoxLayout(size_hint_y=None, height=42, spacing=6)
        self.ph_label = Label(text='pH:   --', size_hint_x=0.35, font_size='14sp')
        self.ph_bar   = ProgressBar(max=14, value=0, size_hint_x=0.65)
        ph_row.add_widget(self.ph_label)
        ph_row.add_widget(self.ph_bar)
        readings_card.add_widget(ph_row)

        glu_row = BoxLayout(size_hint_y=None, height=42, spacing=6)
        self.glucose_label = Label(text='Glu:  -- mg/dL', size_hint_x=0.35, font_size='14sp')
        self.glucose_bar   = ProgressBar(max=250, value=0, size_hint_x=0.65)
        glu_row.add_widget(self.glucose_label)
        glu_row.add_widget(self.glucose_bar)
        readings_card.add_widget(glu_row)

        self.add_widget(readings_card)

        # ── Last Captured Data Card ──────────────────────────────────
        # Updated only when an actual NFC tap event fires (not on polling).
        last_card = _Card(
            orientation='vertical', size_hint_y=0.22, padding=6, spacing=2)

        last_card.add_widget(
            Label(text='Last Captured Data (NFC Tap)',
                  bold=True, size_hint_y=None, height=22,
                  font_size='13sp', color=(0.3, 1, 0.6, 1)))

        self.last_time_label = Label(
            text='Time:     --',
            size_hint_y=None, height=26, font_size='12sp',
            color=(0.9, 0.9, 0.9, 1), halign='left')
        self.last_time_label.bind(
            size=lambda w, _: setattr(w, 'text_size', (w.width, None)))
        last_card.add_widget(self.last_time_label)

        self.last_values_label = Label(
            text='Temp: --  |  pH: --  |  Glu: --',
            size_hint_y=None, height=26, font_size='12sp',
            color=(0.9, 0.9, 0.9, 1), halign='left')
        self.last_values_label.bind(
            size=lambda w, _: setattr(w, 'text_size', (w.width, None)))
        last_card.add_widget(self.last_values_label)

        self.last_tagid_label = Label(
            text='Tag ID:   --',
            size_hint_y=None, height=26, font_size='12sp',
            color=(0.7, 0.7, 0.7, 1), halign='left')
        self.last_tagid_label.bind(
            size=lambda w, _: setattr(w, 'text_size', (w.width, None)))
        last_card.add_widget(self.last_tagid_label)

        self.add_widget(last_card)

        # ── Monitoring controls ───────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=0.10, spacing=6)

        start_btn = Button(text='Start Monitoring',
                           background_color=(0.2, 0.7, 0.3, 1))
        start_btn.bind(on_press=self.start_monitoring)
        btn_row.add_widget(start_btn)

        stop_btn = Button(text='Stop Monitoring',
                          background_color=(0.7, 0.2, 0.2, 1))
        stop_btn.bind(on_press=self.stop_monitoring)
        btn_row.add_widget(stop_btn)

        self.add_widget(btn_row)

        # Auto-start polling after render
        Clock.schedule_once(self._auto_start, 1)

    # ── Scan button ──────────────────────────────────────────────────

    def _on_scan_pressed(self, instance):
        """User tapped the Scan NFC button: (re)connect the NFC reader.

        This triggers a foreground connect attempt so the reader mode is
        active and the device actively polls for a nearby NHS 3152 tag.
        On Android, if NFC is off, the Java layer will show the NFC
        Settings screen automatically.
        """
        self.status_label.text = 'Scanning — hold NHS 3152 near phone NFC area...'
        self.status_label.color = (0.4, 0.9, 1, 1)
        try:
            if self.sensor_interface:
                self.sensor_interface.connect()
        except Exception as e:
            self.status_label.text = f'Scan error: {e}'
            self.status_label.color = (1, 0.4, 0.4, 1)

    # ── NFC Tap notification (called from main.py on_new_intent) ────────

    def notify_tap(self, data: dict) -> None:
        """Update 'Last Captured Data' card AND live readings bars with NFC tap data.

        Called by ``SensorMonitorApp._on_android_new_intent`` whenever the
        foreground dispatch delivers a successfully parsed NFC intent.
        Updates both the last-captured card AND the live temperature / pH /
        glucose progress bars so data is always shown on tap.
        """
        try:
            ts = data.get('timestamp', '')
            if ts:
                try:
                    ts_obj = datetime.fromisoformat(ts)
                    ts = ts_obj.strftime('%Y-%m-%d  %H:%M:%S')
                except Exception:
                    pass

            temp    = data.get('temperature', None)
            ph      = data.get('ph', None)
            glucose = data.get('glucose', None)

            # ── Update Last Captured Data card ────────────────────────────
            self.last_time_label.text   = f'Time:     {ts}'
            if temp is not None and ph is not None and glucose is not None:
                self.last_values_label.text = (
                    f"Temp: {float(temp):.1f} °C  "
                    f"pH: {float(ph):.2f}  "
                    f"Glu: {float(glucose):.0f} mg/dL"
                )
            else:
                self.last_values_label.text = 'Temp: --  |  pH: --  |  Glu: --'

            tag_id = data.get('tag_id', '') or 'N/A'
            self.last_tagid_label.text  = f'Tag ID:   {tag_id}'

            # ── Also update live readings bars immediately ─────────────────
            # (The observer pattern via sensor_data.add_reading handles this too,
            # but updating here ensures the bars refresh on the same Kivy tick
            # as notify_tap, even if the observer fires slightly later.)
            if temp is not None and ph is not None and glucose is not None:
                self._apply_reading(float(temp), float(ph), float(glucose))

            # ── Status bar ────────────────────────────────────────────────
            self.status_label.text  = '\u2713 NHS 3152 tag captured successfully'
            self.status_label.color = (0.3, 1, 0.3, 1)
            self._has_data = True
        except Exception as e:
            self.status_label.text = f'Tap notification error: {e}'

    # ── Monitoring lifecycle ─────────────────────────────────────────

    def _auto_start(self, dt):
        self.start_monitoring(None)

    def start_monitoring(self, instance):
        """Start the 1-second polling loop."""
        if self.update_event is None:
            self.update_event = Clock.schedule_interval(self.update_dashboard, 1)
            if not self._has_data:
                self.status_label.text  = 'Scanning for NHS 3152 sensor...'
                self.status_label.color = (1, 0.8, 0.2, 1)
            else:
                self.status_label.text  = 'Monitoring active — sensor connected'
                self.status_label.color = (0.5, 1, 0.5, 1)

    def stop_monitoring(self, instance):
        """Stop the polling loop."""
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        self.status_label.text  = 'Monitoring stopped'
        self.status_label.color = (1, 0.5, 0.5, 1)

    def _show_null_values(self):
        self.temp_label.text    = 'Temp: -- °C'
        self.temp_bar.value     = 0
        self.ph_label.text      = 'pH:   --'
        self.ph_bar.value       = 0
        self.glucose_label.text = 'Glu:  -- mg/dL'
        self.glucose_bar.value  = 0

    def update_dashboard(self, dt):
        """Periodic poll: update the live readings bar with the freshest data.

        Queries ``sensor_interface.read_sensor_data()`` directly so the display
        reflects whatever the Java periodic re-read last stored in
        ``lastSensorData``, with no extra polling lag.  Falls back to the stored
        ``sensor_data`` history when no live data is available (e.g. tag not in
        range but a previous reading exists).
        """
        live = None
        if self.sensor_interface:
            try:
                live = self.sensor_interface.read_sensor_data()
            except Exception:
                pass

        if live:
            self._apply_reading(
                live['temperature'], live['ph'], live['glucose'])
            if not self._has_data:
                self._has_data = True
                self.status_label.text  = 'NHS 3152 sensor connected — live data'
                self.status_label.color = (0.3, 1, 0.3, 1)
            return

        # No live data — fall back to the most recent stored reading
        readings = self.sensor_data.get_all_readings()
        if readings:
            latest = readings[-1]
            self._apply_reading(
                latest.temperature, latest.ph, latest.glucose)
            if not self._has_data:
                self._has_data = True
                self.status_label.text  = 'NHS 3152 sensor connected — live data'
                self.status_label.color = (0.3, 1, 0.3, 1)
        else:
            self._show_null_values()
            self.status_label.text  = 'Waiting for NHS 3152 sensor...'
            self.status_label.color = (1, 0.8, 0.2, 1)

    def _apply_reading(self, temp: float, ph: float, glucose: float) -> None:
        """Push one set of sensor values into all live-display widgets."""
        self.temp_label.text    = f'Temp: {temp:.1f} °C'
        self.temp_bar.value     = max(0, min(temp, 60))
        self.ph_label.text      = f'pH:   {ph:.2f}'
        self.ph_bar.value       = max(0, min(ph, 14.0))
        self.glucose_label.text = f'Glu:  {glucose:.1f} mg/dL'
        self.glucose_bar.value  = max(0, min(glucose, 250))
    
