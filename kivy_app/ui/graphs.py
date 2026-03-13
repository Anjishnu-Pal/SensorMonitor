"""
Graphs screen — Single matplotlib Figure with shared X-axis and three
independent Y-axes (Temperature left, pH right, Glucose offset-right).

Rendered with the Agg backend to a raw RGBA buffer which is uploaded to
a Kivy Texture and displayed via an Image widget.  The figure is created
once and redrawn in-place on every SensorData observer callback.

Y-axis layout
-------------
ax1  (left)             — Temperature  °C   (red)
ax2  (right)            — pH                (blue)   twinx of ax1
ax3  (right + outward)  — Glucose  mg/dL    (green)  twinx of ax1, offset 60 pt
"""

import io
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.graphics.texture import Texture
from kivy.properties import StringProperty
from kivy.clock import Clock

# ── Colour palette ─────────────────────────────────────────────────────────
_FIG_BG    = '#16161a'
_AX_BG     = '#1c1c22'
_CLR_TEMP  = '#ff5555'   # red
_CLR_PH    = '#4db8ff'   # blue
_CLR_GLUC  = '#4dea66'   # green
_CLR_TICK  = '#cccccc'
_DPI       = 80          # render DPI → balances sharpness vs render time


class GraphsScreen(BoxLayout):
    """Single matplotlib Figure with a shared X-axis and three independent
    Y-axes, embedded in a Kivy Image widget as a dynamically updated texture.

    Registers itself as a SensorData observer so the chart redraws the
    instant new sensor data arrives — no button press or polling required.
    Uses a StringProperty for the stats bar so Kivy binding keeps the label
    in sync without manual .text assignments elsewhere.
    """

    # Kivy reactive property — bound to the stats label in __init__
    stats_text = StringProperty(
        'Hold NHS 3152 near phone NFC area to start plotting')

    def __init__(self, csv_handler, sensor_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = [6, 4, 6, 4]
        self.spacing = 4

        self.csv_handler = csv_handler
        self.sensor_data = sensor_data

        # ── Pre-build a persistent matplotlib figure ─────────────────────
        # Creating once avoids the overhead of plt.subplots() on every redraw.
        self._fig, self._ax1 = plt.subplots(
            figsize=(7, 4.5), facecolor=_FIG_BG)
        self._ax1.set_facecolor(_AX_BG)

        # ax2 — pH, right Y-axis (shares X-axis with ax1 via twinx)
        self._ax2 = self._ax1.twinx()

        # ax3 — Glucose, second right Y-axis offset 60 pt outward
        self._ax3 = self._ax1.twinx()
        self._ax3.spines['right'].set_position(('outward', 60))

        # ── Header label ─────────────────────────────────────────────────
        hdr = Label(
            text='Live Sensor Charts',
            size_hint_y=None, height=28,
            bold=True, font_size='15sp')
        self.add_widget(hdr)

        # ── Image widget — receives the rendered matplotlib texture ───────
        self.graph_image = Image(
            size_hint_y=1,
            allow_stretch=True,
            keep_ratio=True)
        self.add_widget(self.graph_image)

        # ── Stats bar driven by StringProperty ───────────────────────────
        self.stats_label = Label(
            text=self.stats_text,
            size_hint_y=None, height=26,
            font_size='11sp', color=(0.75, 0.75, 0.75, 1))
        self.add_widget(self.stats_label)
        self.bind(stats_text=lambda i, v: setattr(self.stats_label, 'text', v))

        # ── Register as SensorData observer ──────────────────────────────
        sensor_data.add_observer(self._on_new_reading)

        # Populate with any readings captured before this screen was built
        Clock.schedule_once(self._initial_load, 0)

    # ── Observer callback ────────────────────────────────────────────────────

    def _on_new_reading(self, _reading):
        """Called synchronously on the Kivy main thread when new data arrives."""
        self._refresh_graph()

    # ── Graph refresh ────────────────────────────────────────────────────────

    def _initial_load(self, _dt):
        self._refresh_graph()

    def _refresh_graph(self):
        """Redraw the matplotlib figure and upload the result as a Kivy texture."""
        readings = self.sensor_data.get_all_readings()
        if not readings:
            self.stats_text = (
                'Hold NHS 3152 near phone NFC area to start plotting')
            return

        # Limit to the last 100 samples so rendering stays fast on Android
        recent = readings[-100:]

        times = [
            r.timestamp.strftime('%H:%M:%S')
            if hasattr(r.timestamp, 'strftime') else str(r.timestamp)[:8]
            for r in recent
        ]
        temps = [r.temperature for r in recent]
        phs   = [r.ph          for r in recent]
        glucs = [r.glucose     for r in recent]
        xs    = range(len(recent))

        # ── Clear and redraw all three axes ──────────────────────────────
        ax1, ax2, ax3 = self._ax1, self._ax2, self._ax3

        for ax in (ax1, ax2, ax3):
            ax.cla()
            ax.set_facecolor(_AX_BG)
            for spine in ax.spines.values():
                spine.set_color('#444450')
            ax.tick_params(colors=_CLR_TICK, labelsize=8)

        # Temperature — left Y-axis
        ax1.plot(xs, temps, color=_CLR_TEMP, linewidth=1.6, label='Temp °C')
        ax1.set_ylabel('Temp (°C)', color=_CLR_TEMP, fontsize=9)
        ax1.tick_params(axis='y', colors=_CLR_TEMP)
        ax1.set_ylim(0, 60)

        # pH — right Y-axis
        ax2.plot(xs, phs, color=_CLR_PH, linewidth=1.6, label='pH')
        ax2.set_ylabel('pH', color=_CLR_PH, fontsize=9)
        ax2.tick_params(axis='y', colors=_CLR_PH)
        ax2.spines['right'].set_color(_CLR_PH)
        ax2.set_ylim(0, 14)

        # Glucose — offset right Y-axis (+60 pt outward)
        ax3.spines['right'].set_position(('outward', 60))
        ax3.spines['right'].set_color(_CLR_GLUC)
        ax3.plot(xs, glucs, color=_CLR_GLUC, linewidth=1.6, label='Glu mg/dL')
        ax3.set_ylabel('Glucose (mg/dL)', color=_CLR_GLUC, fontsize=9)
        ax3.tick_params(axis='y', colors=_CLR_GLUC)
        ax3.set_ylim(0, 500)

        # Shared X-axis labels (sparse — first / quarter / half / 3-quarter / last)
        n = len(recent)
        ticks = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
        ax1.set_xticks(ticks)
        ax1.set_xticklabels([times[i] for i in ticks], rotation=20, fontsize=8)
        ax1.tick_params(axis='x', colors=_CLR_TICK)

        # Combined legend from all three axes
        lines  = ax1.get_lines() + ax2.get_lines() + ax3.get_lines()
        labels = [ln.get_label() for ln in lines]
        ax1.legend(lines, labels, loc='upper left', fontsize=8,
                   facecolor=_AX_BG, labelcolor='white', framealpha=0.6)

        self._fig.suptitle(
            'NHS 3152 Sensor — Live Readings',
            color='white', fontsize=10, y=0.99)

        # Leave right margin for the offset Glucose axis label
        self._fig.tight_layout(rect=[0, 0.02, 0.82, 0.97])

        # ── Render to raw RGBA bytes → Kivy Texture → Image widget ───────
        buf = io.BytesIO()
        self._fig.savefig(buf, format='raw', dpi=_DPI, facecolor=_FIG_BG)
        buf.seek(0)
        raw = np.frombuffer(buf.read(), dtype=np.uint8)

        w = int(self._fig.get_figwidth()  * _DPI)
        h = int(self._fig.get_figheight() * _DPI)
        raw = raw.reshape((h, w, 4))[::-1]   # flip Y — Kivy origin is bottom-left

        tex = Texture.create(size=(w, h), colorfmt='rgba')
        tex.blit_buffer(raw.tobytes(), colorfmt='rgba', bufferfmt='ubyte')
        self.graph_image.texture = tex

        # ── Update stats bar via StringProperty ──────────────────────────
        self.stats_text = (
            f'T: {min(temps):.1f}–{max(temps):.1f} °C  |  '
            f'pH: {min(phs):.2f}–{max(phs):.2f}  |  '
            f'Glu: {min(glucs):.0f}–{max(glucs):.0f} mg/dL  '
            f'({len(readings)} readings)'
        )
