package com.sensormonitor.android

/**
 * Immutable data class for a single NHS 3152 sensor reading.
 *
 * Ranges (NHS 3152 datasheet §4):
 *   temperature : -10 … 80 °C   (int16 LE × 0.1 °C/LSB)
 *   ph          :   0 … 14      (uint16 LE × 0.01 pH/LSB)
 *   glucose     :   0 … 500 mg/dL (uint16 LE, direct mg/dL)
 *   tagId       : NFC UID hex string, e.g. "04A1B2C3D4E5F6"
 */
data class SensorReading(
    val timestamp:   String,
    val temperature: Float,
    val ph:          Float,
    val glucose:     Float,
    val tagId:       String = ""
)
