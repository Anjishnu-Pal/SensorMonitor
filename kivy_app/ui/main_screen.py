"""
Main screen — Historical sensor readings table using Kivy RecycleView.

RecycleView virtualises the list so only the visible rows are instantiated,
keeping memory use flat regardless of how many readings are stored.  Each
row widget uses Kivy StringProperty bindings so the Kivy binding system
propagates data changes automatically on the main thread.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.properties import StringProperty
from kivy.clock import Clock

# Column header names and per-column text colours for visual distinction
_HEADERS = ['Timestamp', 'Temp (°C)', 'pH', 'Glucose (mg/dL)']
_COL_COLOURS = [
    (1.00, 1.00, 1.00, 1),   # timestamp  — white
    (1.00, 0.85, 0.30, 1),   # temperature — amber
    (0.40, 0.80, 1.00, 1),   # pH          — blue
    (0.30, 1.00, 0.50, 1),   # glucose     — green
]
_ROW_HEIGHT = 34


class ReadingRow(RecycleDataViewBehavior, BoxLayout):
    """Single recycled row widget displayed inside the RecycleView.

    Kivy StringProperty attributes are used for all displayed values so
    the Kivy binding system propagates RecycleView data updates safely on
    the main thread — no manual setText() calls needed.
    """

    ts_text   = StringProperty('')
    temp_text = StringProperty('')
    ph_text   = StringProperty('')
    glu_text  = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = _ROW_HEIGHT
        self.spacing = 2

        self._ts_lbl  = Label(font_size='12sp', color=_COL_COLOURS[0])
        self._tmp_lbl = Label(font_size='12sp', color=_COL_COLOURS[1])
        self._ph_lbl  = Label(font_size='12sp', color=_COL_COLOURS[2])
        self._glu_lbl = Label(font_size='12sp', color=_COL_COLOURS[3])

        for w in (self._ts_lbl, self._tmp_lbl, self._ph_lbl, self._glu_lbl):
            self.add_widget(w)

        self.bind(ts_text=lambda i, v:   setattr(self._ts_lbl,  'text', v))
        self.bind(temp_text=lambda i, v: setattr(self._tmp_lbl, 'text', v))
        self.bind(ph_text=lambda i, v:   setattr(self._ph_lbl,  'text', v))
        self.bind(glu_text=lambda i, v:  setattr(self._glu_lbl, 'text', v))

    def refresh_view_attrs(self, rv, index, data):
        """Called by RecycleView to populate a recycled row with new data."""
        self.ts_text   = data.get('ts',   '')
        self.temp_text = data.get('temp', '')
        self.ph_text   = data.get('ph',   '')
        self.glu_text  = data.get('glu',  '')
        return super().refresh_view_attrs(rv, index, data)


class _SensorRecycleView(RecycleView):
    """RecycleView container pre-configured with ReadingRow and RecycleBoxLayout."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.viewclass = ReadingRow
        layout = RecycleBoxLayout(
            orientation='vertical',
            default_size=(None, _ROW_HEIGHT),
            default_size_hint=(1, None),
            size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))
        self.add_widget(layout)


class MainScreen(BoxLayout):
    """Scrollable historical-data table, observer-driven for instant updates.

    Registers itself on ``sensor_data`` so every time a new reading is
    committed by the 2-second NFC polling loop (or an on-tap NFC intent),
    the RecycleView data list is updated immediately — no separate polling
    timer required.  RecycleView virtualisation keeps rendering fast even
    when hundreds of readings are stored.
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

        # ── Column headers (fixed, outside the RecycleView) ─────────────────
        col_hdr = GridLayout(cols=4, size_hint_y=None, height=30, spacing=2)
        for h in _HEADERS:
            col_hdr.add_widget(
                Label(text=h, bold=True, font_size='11sp',
                      color=(0.40, 0.80, 1, 1)))
        self.add_widget(col_hdr)

        # ── RecycleView (virtualised, memory-efficient list) ─────────────────
        self.rv = _SensorRecycleView(size_hint_y=1)
        self.add_widget(self.rv)

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
        sensor_data.add_observer(self._on_new_reading)

        # Populate with any readings captured before this screen was built
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
        """Refresh RecycleView data from the current SensorData snapshot.

        Shows the last 50 readings, newest first.  Updating rv.data triggers
        RecycleView's internal diffing — only visible rows are re-rendered.
        """
        readings = self.sensor_data.get_all_readings()
        self.count_label.text = f'{len(readings)} readings'

        data = []
        for reading in reversed(readings[-50:]):   # newest first
            ts_str = (
                reading.timestamp.strftime('%H:%M:%S')
                if hasattr(reading.timestamp, 'strftime')
                else str(reading.timestamp)[:19]
            )
            data.append({
                'ts':   ts_str,
                'temp': f'{reading.temperature:.2f}',
                'ph':   f'{reading.ph:.3f}',
                'glu':  f'{reading.glucose:.1f}',
            })

        self.rv.data = data

    # ── Button handlers ──────────────────────────────────────────────────────

    def _on_clear(self, *_):
        """Clear in-memory readings and refresh the (now empty) RecycleView."""
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
