package com.sensormonitor.android

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileWriter
import java.io.IOException

/**
 * Requirement 5 — CSV persistence.
 *
 * Stores readings in [context.getExternalFilesDir(null)]/sensor_data.csv.
 *
 * Why getExternalFilesDir():
 *   - App-private external storage (e.g. /sdcard/Android/data/<pkg>/files/)
 *   - No WRITE_EXTERNAL_STORAGE permission required on API 29+ (scoped storage)
 *   - Accessible via USB / file manager for data export
 *   - Automatically cleared when the app is uninstalled
 *
 * The file is opened in APPEND mode so a USB pull mid-session never truncates
 * existing data. The header row is written only once (when the file is new).
 */
class CsvHandler(private val context: Context) {

    private val TAG = "CsvHandler"

    private val HEADER = "timestamp,temperature,ph,glucose,tag_id\n"

    /** Resolves the CSV file path on each access so it always uses the current
     *  external-storage mount point (handles cases where storage is unmounted). */
    private val csvFile: File
        get() {
            val dir = context.getExternalFilesDir(null)
                ?: context.filesDir   // fallback to internal storage
            return File(dir, "sensor_data.csv")
        }

    init {
        ensureHeaderExists()
    }

    private fun ensureHeaderExists() {
        val f = csvFile
        if (!f.exists() || f.length() == 0L) {
            try {
                FileWriter(f, false).use { it.write(HEADER) }
                Log.i(TAG, "CSV created at ${f.absolutePath}")
            } catch (e: IOException) {
                Log.e(TAG, "Failed to create CSV header: ${e.message}")
            }
        }
    }

    /**
     * Requirement 5 — Append one reading row (timestamp, temp, pH, glucose, tagId).
     * FileWriter(file, true) = append mode.
     *
     * This method is called from a Dispatchers.IO coroutine in NfcSensorManager
     * immediately after each successful transceive(), so every poll is persisted
     * before the UI callback fires.
     */
    fun save(reading: SensorReading) {
        try {
            FileWriter(csvFile, true).use { fw ->
                fw.write(
                    "${reading.timestamp}," +
                    "%.2f,%.3f,%.1f,${reading.tagId}\n".format(
                        reading.temperature, reading.ph, reading.glucose)
                )
            }
            Log.d(TAG,
                "CSV row: ${reading.timestamp} " +
                "T=${reading.temperature} pH=${reading.ph} G=${reading.glucose}")
        } catch (e: IOException) {
            Log.e(TAG, "CSV write error: ${e.message}")
        }
    }

    /**
     * Load all historical rows from CSV.
     * Called on Dispatchers.IO from MainActivity.onCreate() to pre-populate
     * the ViewModel before the first NFC tag is tapped.
     */
    fun loadAll(): List<SensorReading> {
        val file = csvFile
        if (!file.exists()) return emptyList()
        val readings = mutableListOf<SensorReading>()
        try {
            file.bufferedReader().useLines { lines ->
                lines.drop(1)           // skip header
                    .filter { it.isNotBlank() }
                    .forEach { line -> parseLine(line)?.let { readings.add(it) } }
            }
        } catch (e: IOException) {
            Log.e(TAG, "CSV read error: ${e.message}")
        }
        Log.i(TAG, "Loaded ${readings.size} historical reading(s) from CSV")
        return readings
    }

    private fun parseLine(line: String): SensorReading? {
        return try {
            val p = line.split(",")
            if (p.size < 4) return null
            SensorReading(
                timestamp   = p[0].trim(),
                temperature = p[1].trim().toFloat(),
                ph          = p[2].trim().toFloat(),
                glucose     = p[3].trim().toFloat(),
                tagId       = if (p.size > 4) p[4].trim() else ""
            )
        } catch (_: Exception) { null }
    }

    /** Absolute path for display in SettingsFragment or share intent. */
    fun getFilePath(): String = csvFile.absolutePath
}
