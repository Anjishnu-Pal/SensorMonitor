"""
Main screen — Live sensor data table (RecyclerView equivalent).

Displays the last 50 readings in a scrollable 4-column grid, newest row
at the top.  Refreshes the instant SensorData notifies via the observer
callback — no polling timer required.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock

# Column header names and per-column text colours for visual distinction
_HEADERS = ['Timestamp', 'Temp (°C)', 'pH', 'Glucose (mg/dL)']
_COL_COLOURS = [
    (1.00, 1.00, 1.00, 1),   # timestamp — white
    (1.00, 0.85, 0.30, 1),   # temperature — amber
    (0.40, 0.80, 1.00, 1),   # pH — blue
    (0.30, 1.00, 0.50, 1),   # glucose — green
]
_ROW_HEIGHT = 34


class MainScreen(BoxLayout):
    """Scrollable live-data table, observer-driven for instant updates.

    Registers itself on ``sensor_data`` so every time a new reading is
    committed by the 2-second NFC polling loop (or an on-tap NFC intent),
    the table rebuilds immediately — satisfying the "instant update within
    the same 2-second window" requirement without any separate polling timer.
    """

    def __init__(self, csv_handler, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = [8, 6, 8, 6]
        self.spacing = 4

        self.csv_handler = csv_handler
        self.sensor_data = sensor_data

        # ── Header bar ──────────────────────────────────────────────────────
        hdr_row = BoxLayout(size_hint_y=None, height=32, spacing=6)
        title_lbl = Label(
            text='Live Sensor Readings',
            bold=True, font_size='15sp', size_hint_x=0.65)
        self.count_label = Label(
            text='0 readings',
            font_size='11sp', color=(0.55, 0.85, 1, 1), size_hint_x=0.35)
        hdr_row.add_widget(title_lbl)
        hdr_row.add_widget(self.count_label)
        self.add_widget(hdr_row)

        # ── Column headers (fixed, outside the ScrollView) ──────────────────
        col_hdr = GridLayout(
            cols=4, size_hint_y=None, height=30, spacing=2)
        for h in _HEADERS:
            col_hdr.add_widget(
                Label(text=h, bold=True, font_size='11sp',
                      color=(0.40, 0.80, 1, 1)))
        self.add_widget(col_hdr)

        # ── Scrollable data rows ────────────────────────────────────────────
        scroll = ScrollView()
        self.data_grid = GridLayout(
            cols=4, spacing=2,
            size_hint_y=None, row_default_height=_ROW_HEIGHT)
        self.data_grid.bind(minimum_height=self.data_grid.setter('height'))
        scroll.add_widget(self.data_grid)
        self.add_widget(scroll)

        # ── Bottom action buttons ───────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=44, spacing=6)
        clear_btn = Button(
            text='Clear Memory',
            background_color=(0.55, 0.18, 0.18, 1))
        clear_btn.bind(on_press=self._on_clear)
        export_btn = Button(
            text='Export CSV',
            background_color=(0.18, 0.42, 0.65, 1))
        export_btn.bind(on_press=self._on_export)
        btn_row.add_widget(clear_btn)
        btn_row.add_widget(export_btn)
        self.add_widget(btn_row)

        # ── Register as observer for instant, reactive updates ───────────────
        # Called synchronously on the Kivy main thread when add_reading() fires.
        sensor_data.add_observer(self._on_new_reading)

        # Populate table with any readings already captured before this screen
        Clock.schedule_once(self._rebuild_table, 0)

    # ── Observer callback ───────────────────────────────────────────────────

    def _on_new_reading(self, _reading):
        """Triggered immediately when SensorData receives a new reading.

        Because add_reading() is always called from Clock callbacks (main
        thread), this is safe to touch Kivy widgets directly.
        """
        self._rebuild_table()

    # ── Table management ─────────────────────────────────────────────────────

    def _rebuild_table(self, *_):
        """Rebuild the data grid from the current SensorData snapshot.

        Shows the last 50 readings, newest first.  Creates ~200 Labels at
        most — fast enough on Android even at 2-second update intervals.
        """
        self.data_grid.clear_widgets()
        readings = self.sensor_data.get_all_readings()
        self.count_label.text = f'{len(readings)} readings'

        for reading in reversed(readings[-50:]):  # newest first
            ts_str = (
                reading.timestamp.strftime('%H:%M:%S')
                if hasattr(reading.timestamp, 'strftime')
                else str(reading.timestamp)[:19]
            )
            cells = [
                ts_str,
                f'{reading.temperature:.2f}',
                f'{reading.ph:.3f}',
                f'{reading.glucose:.1f}',
            ]
            for cell, colour in zip(cells, _COL_COLOURS):
                self.data_grid.add_widget(
                    Label(text=cell, font_size='12sp',
                          size_hint_y=None, height=_ROW_HEIGHT,
                          color=colour))

    # ── Button handlers ──────────────────────────────────────────────────────

    def _on_clear(self, *_):
        """Clear in-memory readings and rebuild the (now empty) table."""
        self.sensor_data.clear_readings()
        self._rebuild_table()

    def _on_export(self, *_):
        try:
            self.csv_handler.export_all_data(
                self.sensor_data.get_all_readings())
        except Exception as e:
            print(f'Export error: {e}')

    # Keep legacy method name so any code calling refresh_data() still works
    def refresh_data(self, *_):
        self._rebuild_table()
