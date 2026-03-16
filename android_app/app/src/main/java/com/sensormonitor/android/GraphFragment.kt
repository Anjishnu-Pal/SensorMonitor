package com.sensormonitor.android

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.github.mikephil.charting.charts.LineChart
import com.github.mikephil.charting.components.Description
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import com.github.mikephil.charting.formatter.ValueFormatter
import kotlinx.coroutines.launch

/**
 * Requirement 7 — Tab 2: Graphical Plot.
 *
 * CRITICAL layout rule: Three completely SEPARATE chart containers stacked
 * vertically (not one chart with three datasets). Each container is its own
 * CardView holding its own LineChart with a fully independent Y-axis scale:
 *
 *   CardView #1  ──►  LineChart  (Temperature only, Y-axis: °C)
 *   CardView #2  ──►  LineChart  (pH only,          Y-axis: 0-14)
 *   CardView #3  ──►  LineChart  (Glucose only,      Y-axis: mg/dL)
 *
 * X-axis is time, rendered from the timestamp strings stored in the ViewModel.
 *
 * Requirement 6 fix: collects from NfcViewModel.sensorReadings StateFlow
 * with repeatOnLifecycle(STARTED) — both this Fragment and DataFragment
 * receive their own StateFlow emission on the same coroutine frame, so both
 * tabs redraw within the same 2-second poll window simultaneously.
 */
class GraphFragment : Fragment() {

    private val viewModel: NfcViewModel by activityViewModels()

    private lateinit var chartTemp:    LineChart
    private lateinit var chartPh:      LineChart
    private lateinit var chartGlucose: LineChart

    // Retained for the TimeAxisFormatter — mapping index → "HH:mm:ss" label
    private var xTimeLabels: List<String> = emptyList()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_graph, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        chartTemp    = view.findViewById(R.id.chart_temperature)
        chartPh      = view.findViewById(R.id.chart_ph)
        chartGlucose = view.findViewById(R.id.chart_glucose)

        // Each chart is configured independently — separate descriptions,
        // separate Y-axis ranges, separate line colours, no shared state.
        setupChart(chartTemp,    "Temperature (°C)")
        setupChart(chartPh,      "pH")
        setupChart(chartGlucose, "Glucose (mg/dL)")

        // Requirement 6: collect StateFlow instantly when a new reading arrives
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.sensorReadings.collect { readings ->
                    updateAllCharts(readings)
                }
            }
        }
    }

    // ── Chart initialisation ──────────────────────────────────────────────────

    private fun setupChart(chart: LineChart, descriptionText: String) {
        chart.apply {
            description = Description().apply {
                text     = descriptionText
                textSize = 12f
                textColor = Color.WHITE
            }
            setBackgroundColor(Color.rgb(30, 30, 50))
            setTouchEnabled(true)
            isDragEnabled    = true
            setScaleEnabled  (true)
            setPinchZoom     (true)
            isDoubleTapToZoomEnabled = true
            legend.isEnabled = false

            // Right Y-axis disabled — only left axis scales independently per chart
            axisRight.isEnabled = false

            axisLeft.apply {
                textColor     = Color.LTGRAY
                gridColor     = Color.rgb(60, 60, 80)
                axisLineColor = Color.LTGRAY
                granularity   = 0.01f
                isGranularityEnabled = true
            }

            xAxis.apply {
                position      = XAxis.XAxisPosition.BOTTOM
                textColor     = Color.LTGRAY
                gridColor     = Color.rgb(60, 60, 80)
                axisLineColor = Color.LTGRAY
                granularity   = 1f
                isGranularityEnabled = true
                labelRotationAngle  = -45f
                valueFormatter      = TimeAxisFormatter()
            }
        }
    }

    // ── Chart update ──────────────────────────────────────────────────────────

    private fun updateAllCharts(readings: List<SensorReading>) {
        if (readings.isEmpty()) return

        // Store time labels for the X-axis formatter
        xTimeLabels = readings.map { it.timestamp }

        val tempEntries    = ArrayList<Entry>(readings.size)
        val phEntries      = ArrayList<Entry>(readings.size)
        val glucoseEntries = ArrayList<Entry>(readings.size)

        readings.forEachIndexed { i, r ->
            val x = i.toFloat()
            tempEntries.add   (Entry(x, r.temperature))
            phEntries.add     (Entry(x, r.ph))
            glucoseEntries.add(Entry(x, r.glucose))
        }

        // Push to three completely separate frames — each invalidates only itself
        renderChart(chartTemp,    tempEntries,    "Temperature",
                    Color.rgb(255, 99, 99),  Color.argb(40, 255, 99, 99))
        renderChart(chartPh,      phEntries,      "pH",
                    Color.rgb(99, 200, 99),  Color.argb(40, 99, 200, 99))
        renderChart(chartGlucose, glucoseEntries, "Glucose",
                    Color.rgb(99, 99, 255),  Color.argb(40, 99, 99, 255))
    }

    /**
     * Pushes one dataset into one LineChart.
     * drawFilled uses the fill colour for a subtle area shade beneath the line.
     * chart.invalidate() redraws only this frame — not the other two charts.
     */
    private fun renderChart(
        chart:     LineChart,
        entries:   List<Entry>,
        label:     String,
        lineColor: Int,
        fillColor: Int
    ) {
        val dataSet = LineDataSet(entries, label).apply {
            color            = lineColor
            setFillColor     (fillColor)
            setCircleColor   (lineColor)
            circleRadius     = 2.5f
            lineWidth        = 2f
            setDrawValues    (false)
            setDrawFilled    (true)
            mode             = LineDataSet.Mode.CUBIC_BEZIER
            cubicIntensity   = 0.2f
        }
        chart.data = LineData(dataSet)
        chart.invalidate()   // redraws ONLY this chart — no cross-chart coupling
    }

    // ── X-axis formatter ──────────────────────────────────────────────────────

    /**
     * Displays only the "HH:mm:ss" portion of the full timestamp string.
     * Shared by all three charts; each chart maintains its own XAxis instance
     * so there is no coupling between frames.
     */
    private inner class TimeAxisFormatter : ValueFormatter() {
        override fun getFormattedValue(value: Float): String {
            val idx = value.toInt()
            if (idx < 0 || idx >= xTimeLabels.size) return ""
            val full = xTimeLabels[idx]
            // "yyyy-MM-dd HH:mm:ss" → "HH:mm:ss" (chars 11-19)
            return if (full.length >= 19) full.substring(11, 19) else full
        }
    }
}
