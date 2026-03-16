package com.sensormonitor.android

import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Requirement 6 — Reactive architecture (StateFlow).
 *
 * All NHS 3152 sensor data flows through this ViewModel via MutableStateFlow.
 * Both DataFragment and GraphFragment collect from the same flows, so the
 * instant a background coroutine calls [addReading], BOTH fragments redraw
 * within the same Kivy/coroutine frame — solving the "data not showing" bug.
 *
 * StateFlow vs LiveData:
 *   - StateFlow is coroutine-native, always has a current value, and is safe
 *     to collect from Fragment.viewLifecycleOwner.lifecycleScope (no leaks).
 *   - repeatOnLifecycle(STARTED) ensures collection stops when the Fragment
 *     goes to the back stack and resumes when it becomes visible again.
 */
class NfcViewModel : ViewModel() {

    // ── Sensor readings list ──────────────────────────────────────────────────
    // Backed by a MutableStateFlow so every new emission causes Fragments to
    // recompose (ListAdapter.submitList / chart.invalidate).
    private val _sensorReadings = MutableStateFlow<List<SensorReading>>(emptyList())
    val sensorReadings: StateFlow<List<SensorReading>> = _sensorReadings.asStateFlow()

    // ── Latest single reading (for live value display / status card) ──────────
    private val _latestReading = MutableStateFlow<SensorReading?>(null)
    val latestReading: StateFlow<SensorReading?> = _latestReading.asStateFlow()

    // ── Human-readable connection status displayed in the MainActivity bar ─────
    private val _connectionStatus = MutableStateFlow("Waiting for NHS 3152 sensor…")
    val connectionStatus: StateFlow<String> = _connectionStatus.asStateFlow()

    // ── Boolean flag for toolbar icon colouring ────────────────────────────────
    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    // ── Adds one new reading and immediately notifies all collectors ───────────
    fun addReading(reading: SensorReading) {
        // Append to immutable snapshot — StateFlow emits the new list to all
        // active collectors on the Main dispatcher instantly.
        _sensorReadings.value = _sensorReadings.value + reading
        _latestReading.value  = reading
        _isConnected.value    = true
        _connectionStatus.value = "✓ NHS 3152 connected — live data"
    }

    // ── Bulk-load historical CSV data on startup (no duplicate observers) ─────
    fun loadReadings(readings: List<SensorReading>) {
        _sensorReadings.value = readings
        if (readings.isNotEmpty()) {
            _latestReading.value = readings.last()
        }
    }

    // ── Called by NfcSensorManager when TagLostException is caught ────────────
    fun setDisconnected() {
        _isConnected.value      = false
        _connectionStatus.value = "Sensor out of range"
    }

    // ── Arbitrary status string (e.g. "tag detected — reading…") ─────────────
    fun setStatus(status: String) {
        _connectionStatus.value = status
    }
}
