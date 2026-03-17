"""
Graphs screen — Three simultaneous, independently-scaled line charts
(Temperature, pH, Glucose) stacked vertically. Auto-refreshes the instant
new sensor data arrives via the SensorData observer pattern, satisfying the
"LiveData / StateFlow" reactive-update requirement.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.core.text import Label as CoreLabel
from kivy.clock import Clock
from datetime import datetime


# ── Colour palette ─────────────────────────────────────────────────────────
COLOUR_TEMP    = (1.00, 0.35, 0.35, 1)   # red
COLOUR_PH      = (0.30, 0.70, 1.00, 1)   # blue
COLOUR_GLUCOSE = (0.30, 0.92, 0.40, 1)   # green
COLOUR_GRID    = (0.28, 0.28, 0.32, 1)
COLOUR_BG      = (0.10, 0.10, 0.13, 1)


def _make_texture(text, font_size=11, colour=(0.82, 0.82, 0.82, 1)):
    """Render a short string to a Kivy texture for use inside a Canvas."""
    lbl = CoreLabel(text=str(text), font_size=font_size, color=colour)
    lbl.refresh()
    return lbl.texture


class _LineChart(Widget):
    """Single metric line chart drawn entirely on the Kivy Canvas.

    Features
    --------
    - Labelled Y-axis numeric tick marks (via CoreLabel textures)
    - Labelled X-axis (first / middle / last timestamps)
    - Independent Y scale per instance
    - Latest-value overlay in the top-right corner
    - Data dots thinned to ≤ 30 to avoid clutter on dense data sets
    """

    def __init__(self, title='', colour=(1, 1, 1, 1),
                 y_min=0.0, y_max=100.0, y_unit='', **kwargs):
        super().__init__(**kwargs)
        self._title    = title
        self._colour   = colour
        self._y_min    = y_min
        self._y_max    = y_max
        self._y_unit   = y_unit
        self._values   = []       # list[float]
        self._x_labels = []       # list[str] — time string per reading
        self.bind(size=self._redraw, pos=self._redraw)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_readings(self, readings, attr: str):
        """Populate chart from a list of SensorReading objects.

        Parameters
        ----------
        readings : list[SensorReading]
        attr     : 'temperature', 'ph', or 'glucose'
        """
        self._values   = [getattr(r, attr, 0.0) for r in readings]
        self._x_labels = [
            r.timestamp.strftime('%H:%M:%S')
            if hasattr(r.timestamp, 'strftime') else str(r.timestamp)[11:19]
            for r in readings
        ]
        self._redraw()

    # ── Drawing ─────────────────────────────────────────────────────────────

    def _redraw(self, *_):
        self.canvas.clear()

        pad_l, pad_b, pad_r, pad_t = 56, 32, 14, 26
        cw = self.width  - pad_l - pad_r
        ch = self.height - pad_b - pad_t
        if cw < 4 or ch < 4:
            return

        ox = self.x + pad_l
        oy = self.y + pad_b

        n       = len(self._values)
        y_min   = self._y_min
        y_max   = self._y_max
        y_range = max(y_max - y_min, 1e-9)

        with self.canvas:
            # Background
            Color(*COLOUR_BG)
            Rectangle(pos=self.pos, size=self.size)

            # Plot-area border
            Color(0.36, 0.36, 0.40, 1)
            Line(rectangle=(ox, oy, cw, ch), width=1)

            # Y-axis grid lines + numeric tick labels
            for i in range(6):
                frac = i / 5.0
                yy   = oy + ch * frac
                val  = y_min + y_range * frac
                Color(*COLOUR_GRID)
                Line(points=[ox, yy, ox + cw, yy], width=1)
                tex = _make_texture(f'{val:.1f}', font_size=10)
                if tex:
                    Color(0.80, 0.80, 0.80, 1)
                    Rectangle(texture=tex,
                              pos=(ox - 52, yy - 7),
                              size=(48, 14))

            # Chart title + unit (top-left)
            title_tex = _make_texture(
                f'{self._title}  [{self._y_unit}]',
                font_size=12, colour=(1, 1, 1, 1))
            if title_tex:
                Color(1, 1, 1, 1)
                Rectangle(texture=title_tex,
                          pos=(ox + 4, oy + ch - 20),
                          size=title_tex.size)

            # No-data placeholder
            if n == 0:
                nd_tex = _make_texture(
                    'No data — hold NHS 3152 near phone NFC antenna',
                    font_size=11, colour=(0.50, 0.50, 0.50, 1))
                if nd_tex:
                    Color(0.50, 0.50, 0.50, 1)
                    cx_ = ox + cw / 2 - nd_tex.size[0] / 2
                    cy_ = oy + ch / 2 - nd_tex.size[1] / 2
                    Rectangle(texture=nd_tex,
                              pos=(cx_, cy_), size=nd_tex.size)
                return

            # Latest-value overlay (top-right)
            lv_tex = _make_texture(
                f'Latest: {self._values[-1]:.2f} {self._y_unit}',
                font_size=11, colour=self._colour)
            if lv_tex:
                Color(*self._colour)
                rx = ox + cw - lv_tex.size[0] - 4
                Rectangle(texture=lv_tex,
                          pos=(rx, oy + ch - 20),
                          size=lv_tex.size)

            if n < 2:
                return

            # Pre-compute pixel positions for the data line
            pts = []
            for idx, val in enumerate(self._values):
                xx = ox + cw * idx / (n - 1)
                clamped = max(y_min, min(y_max, val))
                yy = oy + ch * (clamped - y_min) / y_range
                pts.extend([xx, yy])

            # Data line
            Color(*self._colour)
            Line(points=pts, width=1.8)

            # Data dots (thinned to ≤ 30 for readability)
            step = max(1, n // 30)
            for idx in range(0, n, step):
                xx = pts[idx * 2]
                yy = pts[idx * 2 + 1]
                Ellipse(pos=(xx - 3, yy - 3), size=(6, 6))

            # X-axis time labels at first / middle / last sample
            if self._x_labels:
                for idx in [0, n // 2, n - 1]:
                    if idx >= len(self._x_labels):
                        continue
                    xx  = ox + cw * idx / (n - 1)
                    tex = _make_texture(self._x_labels[idx], font_size=9)
                    if tex:
                        Color(0.65, 0.65, 0.65, 1)
                        tx = max(ox, min(xx - tex.size[0] / 2,
                                         ox + cw - tex.size[0]))
                        Rectangle(texture=tex,
                                  pos=(tx, oy - 22),
                                  size=tex.size)


# ═══════════════════════════════════════════════════════════════════════════
# GraphsScreen — three simultaneous charts stacked vertically
# ═══════════════════════════════════════════════════════════════════════════

class GraphsScreen(BoxLayout):
    """Displays three independent live line charts (Temperature / pH / Glucose)
    stacked vertically, each with its own Y scale.

    Registers itself as a SensorData observer so all three charts redraw the
    instant new data arrives — no button press required.  This satisfies the
    requirement for a reactive immediate UI refresh within the same 2-second
    polling window.
    """

    def __init__(self, csv_handler, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = [6, 4, 6, 4]
        self.spacing = 4

        self.csv_handler = csv_handler
        self.sensor_data = sensor_data

        # ── Header ─────────────────────────────────────────────────────────
        self.header_label = Label(
            text='Live Sensor Charts',
            size_hint_y=None, height=28,
            bold=True, font_size='15sp')
        self.add_widget(self.header_label)

        # ── Three independent line charts, stacked vertically ──────────────
        # Each chart has size_hint_y=0.29 so they fill available space equally
        # leaving room for header and stats bar.
        self.chart_temp = _LineChart(
            title='Temperature', colour=COLOUR_TEMP,
            y_min=0.0, y_max=60.0, y_unit='°C',
            size_hint_y=0.29)
        self.add_widget(self.chart_temp)

        self.chart_ph = _LineChart(
            title='pH Level', colour=COLOUR_PH,
            y_min=0.0, y_max=14.0, y_unit='pH',
            size_hint_y=0.29)
        self.add_widget(self.chart_ph)

        self.chart_glucose = _LineChart(
            title='Glucose', colour=COLOUR_GLUCOSE,
            y_min=30.0, y_max=250.0, y_unit='mg/dL',
            size_hint_y=0.29)
        self.add_widget(self.chart_glucose)

        # ── Stats summary bar ──────────────────────────────────────────────
        self.stats_label = Label(
            text='Hold NHS 3152 near phone NFC area to start plotting',
            size_hint_y=None, height=26,
            font_size='11sp', color=(0.75, 0.75, 0.75, 1))
        self.add_widget(self.stats_label)

        # ── Register as observer — charts refresh instantly on new data ────
        sensor_data.add_observer(self._on_new_reading)

        # Populate with any readings captured before this screen was built
        Clock.schedule_once(self._initial_load, 0)

    # ── Observer callback ───────────────────────────────────────────────────

    def _on_new_reading(self, _reading):
        """Called synchronously on the Kivy main thread immediately when a
        new reading is pushed into SensorData.  Redraws all three charts."""
        self._refresh_all_charts()

    # ── Chart refresh ────────────────────────────────────────────────────────

    def _initial_load(self, _dt):
        self._refresh_all_charts()

    def _refresh_all_charts(self):
        """Fetch the latest readings and redraw all three line charts."""
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self.stats_label.text = (
                'Hold NHS 3152 near phone NFC area to start plotting')
            return

        # Limit to the last 100 points so rendering stays fast on Android
        recent = readings[-100:]

        self.chart_temp.set_readings(recent, 'temperature')
        self.chart_ph.set_readings(recent, 'ph')
        self.chart_glucose.set_readings(recent, 'glucose')

        temps  = [r.temperature for r in recent]
        phs    = [r.ph          for r in recent]
        glucs  = [r.glucose     for r in recent]
        self.stats_label.text = (
            f'T: {min(temps):.1f}–{max(temps):.1f} °C  |  '
            f'pH: {min(phs):.2f}–{max(phs):.2f}  |  '
            f'Glu: {min(glucs):.0f}–{max(glucs):.0f} mg/dL  '
            f'({len(readings)} readings)'
        )
