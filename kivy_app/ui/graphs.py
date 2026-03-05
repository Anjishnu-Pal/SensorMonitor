"""
Graphs screen for data visualization with real-time line chart plotting.
Uses Kivy Canvas to draw temperature, pH, and glucose line charts.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle, Ellipse, InstructionGroup
from kivy.clock import Clock
from datetime import datetime, timedelta


# ── Colour palette ────────────────────────────────────────────────────────
COLOUR_TEMP    = (1, 0.3, 0.3, 1)   # red
COLOUR_PH      = (0.3, 0.7, 1, 1)   # blue
COLOUR_GLUCOSE = (0.3, 0.9, 0.3, 1) # green
COLOUR_GRID    = (0.3, 0.3, 0.3, 1) # dark grey
COLOUR_BG      = (0.12, 0.12, 0.14, 1)


class GraphCanvas(Widget):
    """Custom widget that draws a line chart on the Kivy Canvas."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._data_points = []          # list of (value, label_str) tuples
        self._line_colour = (1, 1, 1, 1)
        self._y_min = 0
        self._y_max = 100
        self._y_label = ''
        self._title = ''
        self.bind(size=self._redraw, pos=self._redraw)

    def set_data(self, points, colour, y_min, y_max, y_label='', title=''):
        self._data_points = points
        self._line_colour = colour
        self._y_min = y_min
        self._y_max = y_max
        self._y_label = y_label
        self._title = title
        self._redraw()

    # ── drawing ───────────────────────────────────────────────────────────
    def _redraw(self, *_args):
        self.canvas.clear()
        if not self._data_points:
            with self.canvas:
                Color(1, 1, 1, 0.5)
            return

        pad_l, pad_b, pad_r, pad_t = 60, 40, 20, 30
        w = self.width  - pad_l - pad_r
        h = self.height - pad_b - pad_t
        if w <= 0 or h <= 0:
            return
        ox = self.x + pad_l
        oy = self.y + pad_b

        y_min, y_max = self._y_min, self._y_max
        y_range = y_max - y_min if y_max != y_min else 1.0
        n = len(self._data_points)

        with self.canvas:
            # background
            Color(*COLOUR_BG)
            Rectangle(pos=self.pos, size=self.size)

            # horizontal grid lines (5 lines)
            Color(*COLOUR_GRID)
            for i in range(6):
                yy = oy + h * i / 5
                Line(points=[ox, yy, ox + w, yy], width=1)

            # y-axis labels
            for i in range(6):
                val = y_min + y_range * i / 5
                yy = oy + h * i / 5
                Color(1, 1, 1, 0.7)
                # Draw small label markers (Kivy Label not available on canvas,
                # but the Rectangle+text trick is complex; we use small dots)
                Ellipse(pos=(ox - 6, yy - 3), size=(6, 6))

            # data line
            Color(*self._line_colour)
            pts = []
            for idx, (val, _lbl) in enumerate(self._data_points):
                if n > 1:
                    xx = ox + w * idx / (n - 1)
                else:
                    xx = ox + w / 2
                clamped = max(y_min, min(y_max, val))
                yy = oy + h * (clamped - y_min) / y_range
                pts.extend([xx, yy])

            if len(pts) >= 4:
                Line(points=pts, width=1.5)

            # data dots
            Color(*self._line_colour)
            for i in range(0, len(pts), 2):
                Ellipse(pos=(pts[i] - 4, pts[i + 1] - 4), size=(8, 8))


class GraphsScreen(BoxLayout):
    """Screen for displaying sensor data graphs with real chart plotting."""

    def __init__(self, csv_handler, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        self.csv_handler = csv_handler
        self.sensor_data = sensor_data

        # Title
        self.title_label = Label(
            text='Sensor Data Graphs',
            size_hint_y=0.07, bold=True, font_size='18sp')
        self.add_widget(self.title_label)

        # Status / stats bar
        self.stats_label = Label(
            text='Select a data type to plot',
            size_hint_y=0.06, font_size='13sp',
            color=(0.8, 0.8, 0.8, 1))
        self.add_widget(self.stats_label)

        # Graph canvas
        self.graph_canvas = GraphCanvas(size_hint_y=0.55)
        self.add_widget(self.graph_canvas)

        # Text data scroll area (below the graph)
        scroll = ScrollView(size_hint_y=0.17)
        self.data_layout = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self.data_layout.bind(minimum_height=self.data_layout.setter('height'))
        scroll.add_widget(self.data_layout)
        self.add_widget(scroll)

        # Button layout
        btn_layout = BoxLayout(size_hint_y=0.15, spacing=5)

        temp_btn = Button(text='Temperature', size_hint_y=None, height=50,
                          background_color=COLOUR_TEMP)
        temp_btn.bind(on_press=self.show_temperature)
        btn_layout.add_widget(temp_btn)

        ph_btn = Button(text='pH Level', size_hint_y=None, height=50,
                        background_color=COLOUR_PH)
        ph_btn.bind(on_press=self.show_ph)
        btn_layout.add_widget(ph_btn)

        glucose_btn = Button(text='Glucose', size_hint_y=None, height=50,
                             background_color=COLOUR_GLUCOSE)
        glucose_btn.bind(on_press=self.show_glucose)
        btn_layout.add_widget(glucose_btn)

        all_btn = Button(text='All Data', size_hint_y=None, height=50)
        all_btn.bind(on_press=self.show_all)
        btn_layout.add_widget(all_btn)

        self.add_widget(btn_layout)


    # ── helpers ───────────────────────────────────────────────────────────\n
    def _fmt_time(self, ts):
        if isinstance(ts, datetime):
            return ts.strftime('%H:%M:%S')
        return str(ts)

    def _compute_stats(self, values):
        if not values:
            return ''
        mn = min(values)
        mx = max(values)
        avg = sum(values) / len(values)
        return f'Min: {mn:.2f}  |  Max: {mx:.2f}  |  Avg: {avg:.2f}  |  Points: {len(values)}'

    # ── plot helpers ──────────────────────────────────────────────────────
    def show_temperature(self, instance=None):
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self._display_message('No temperature data available')
            return

        points = [(r.temperature, self._fmt_time(r.timestamp)) for r in readings]
        vals = [p[0] for p in points]
        self.graph_canvas.set_data(
            points, COLOUR_TEMP,
            y_min=0,
            y_max=60,
            y_label='°C', title='Temperature (0-60 °C)')
        self.title_label.text = 'Temperature (°C)'
        self.stats_label.text = self._compute_stats(vals)
        self._show_text_table(readings, 'temperature', '°C')

    def show_ph(self, instance=None):
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self._display_message('No pH data available')
            return

        points = [(r.ph, self._fmt_time(r.timestamp)) for r in readings]
        vals = [p[0] for p in points]
        self.graph_canvas.set_data(
            points, COLOUR_PH,
            y_min=0,
            y_max=14,
            y_label='pH', title='pH Level (0-14)')
        self.title_label.text = 'pH Level'
        self.stats_label.text = self._compute_stats(vals)
        self._show_text_table(readings, 'ph', '')

    def show_glucose(self, instance=None):
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self._display_message('No glucose data available')
            return

        points = [(r.glucose, self._fmt_time(r.timestamp)) for r in readings]
        vals = [p[0] for p in points]
        self.graph_canvas.set_data(
            points, COLOUR_GLUCOSE,
            y_min=30,
            y_max=250,
            y_label='mg/dL', title='Glucose (30-250 mg/dL)')
        self.title_label.text = 'Glucose (mg/dL)'
        self.stats_label.text = self._compute_stats(vals)
        self._show_text_table(readings, 'glucose', 'mg/dL')

    def show_all(self, instance=None):
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self._display_message('No sensor data available')
            return

        # Show temperature graph by default for "All" view
        points = [(r.temperature, self._fmt_time(r.timestamp)) for r in readings]
        vals = [p[0] for p in points]
        self.graph_canvas.set_data(
            points, COLOUR_TEMP,
            y_min=0,
            y_max=250,
            y_label='', title='All Data (combined scale)')
        self.title_label.text = 'All Sensor Data'

        temps = [r.temperature for r in readings]
        phs = [r.ph for r in readings]
        glus = [r.glucose for r in readings]
        self.stats_label.text = (
            f'Temp: {min(temps):.1f}-{max(temps):.1f}°C | '
            f'pH: {min(phs):.2f}-{max(phs):.2f} | '
            f'Glu: {min(glus):.0f}-{max(glus):.0f} mg/dL')

        # Show all data in text table
        self.data_layout.clear_widgets()
        header = Label(
            text='Time | Temp (°C) | pH | Glucose (mg/dL)',
            size_hint_y=None, height=35, bold=True)
        self.data_layout.add_widget(header)
        for r in readings[-50:]:
            text = (f"{self._fmt_time(r.timestamp)} | "
                    f"{r.temperature:.2f} | {r.ph:.2f} | {r.glucose:.0f}")
            self.data_layout.add_widget(
                Label(text=text, size_hint_y=None, height=28, font_size='12sp'))

    def _show_text_table(self, readings, field, unit):
        self.data_layout.clear_widgets()
        header = Label(
            text=f'Time | {field.title()} ({unit})',
            size_hint_y=None, height=35, bold=True)
        self.data_layout.add_widget(header)
        for r in readings[-50:]:
            val = getattr(r, field, 0)
            text = f"{self._fmt_time(r.timestamp)} | {val:.2f} {unit}"
            self.data_layout.add_widget(
                Label(text=text, size_hint_y=None, height=28, font_size='12sp'))

    def _display_message(self, message):
        self.graph_canvas.set_data([], (1, 1, 1, 1), 0, 1)
        self.data_layout.clear_widgets()
        self.stats_label.text = message
        msg_label = Label(text=message, size_hint_y=None, height=50)
        self.data_layout.add_widget(msg_label)
