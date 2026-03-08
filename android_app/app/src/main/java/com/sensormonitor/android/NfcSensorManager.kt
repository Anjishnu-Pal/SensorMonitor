package com.sensormonitor.android

import android.nfc.NdefMessage
import android.nfc.NdefRecord
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.nfc.tech.Ndef
import android.nfc.tech.NfcA
import android.util.Log
import kotlinx.coroutines.*
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.text.SimpleDateFormat
import java.util.*

/**
 * Requirements 4 + 3 + 5 — NHS 3152 NFC Sensor Manager.
 *
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │  DATA FLOW                                                              │
 * │                                                                         │
 * │  1.  MainActivity.onNewIntent()  ──►  handleNfcIntent()                │
 * │         │                                                              │
 * │         ├─ Extract NDEF messages  ──►  parseNdefMessage()              │
 * │         │       └─ RTD_TEXT / MIME text / binary  ──►  SensorReading   │
 * │         │                                                              │
 * │         └─ Extract Tag  ──►  processTag()                              │
 * │               └─ Coroutine (Dispatchers.IO)                            │
 * │                     ├─ tryReadNdef() — immediate first read            │
 * │                     └─ startNfcAPolling()   ── 2 s loop               │
 * │                           NfcA.transceive(READ_CMD)                    │
 * │                           TagLostException → break                     │
 * │                                                                        │
 * │  2.  Every successful read  ──►  CsvHandler.save()                     │
 * │                               ──►  onReadingReceived()                 │
 * │                                       └─►  ViewModel.addReading()      │
 * │                                                └─►  StateFlow emits    │
 * │                                                       └─►  BOTH Frags  │
 * │                                                             redraw NOW  │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * Callbacks are always delivered on Dispatchers.Main so the ViewModel
 * (and hence both Fragments) updates within the same coroutine frame.
 */
class NfcSensorManager(
    private val csvHandler: CsvHandler,
    private val onReadingReceived: (SensorReading) -> Unit,
    private val onConnectionLost:  () -> Unit
) {
    private val TAG = "NfcSensorManager"

    // Independent CoroutineScope — not tied to any Activity/Fragment lifecycle.
    // SupervisorJob ensures one failed coroutine does not cancel the others.
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var pollingJob: Job? = null

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Called from MainActivity.handleIntent() when a Tag object is extracted.
     * Cancels any previous polling loop, then:
     *  1. Performs an NDEF read for an immediate first result.
     *  2. Opens an NfcA connection for continuous 2-second polling.
     */
    fun processTag(tag: Tag) {
        pollingJob?.cancel()
        pollingJob = scope.launch {
            // Immediate first read via NDEF (faster than raw NfcA for first poll)
            val firstReading = tryReadNdef(tag)
            if (firstReading != null) {
                csvHandler.save(firstReading)
                withContext(Dispatchers.Main) { onReadingReceived(firstReading) }
            }
            // Continuous NfcA polling while tag stays in RF field
            startNfcAPolling(tag)
        }
    }

    /**
     * Parse an NdefMessage that arrived via foreground dispatch intent.
     * Called directly from handleIntent() when EXTRA_NDEF_MESSAGES is present.
     */
    fun parseNdefMessage(message: NdefMessage, tagId: String = ""): SensorReading? {
        for (record in message.records) {

            // ── Priority 1: RTD_TEXT (NFC Forum Text Record Type Definition) ──
            // NHS 3152 firmware writes CSV data as a standard NDEF text record.
            // The payload has a status byte + IANA language code prefix that
            // must be stripped before parsing the actual sensor CSV string.
            if (record.tnf == NdefRecord.TNF_WELL_KNOWN &&
                record.type.contentEquals(NdefRecord.RTD_TEXT)) {
                val text = parseTextRecord(record)
                if (text != null) {
                    Log.i(TAG, "RTD_TEXT: \"$text\"")
                    return parseCsvSensorText(text, tagId)
                }
                continue // skip binary fallback for text records
            }

            // ── Priority 2: MIME text/* (TNF_MIME_MEDIA) ──────────────────────
            // Some NHS 3152 firmware variants write text/plain MIME records.
            // Payload is raw UTF-8 with no status/language-code prefix.
            if (record.tnf == NdefRecord.TNF_MIME_MEDIA) {
                val mimeType = String(record.type, Charsets.US_ASCII)
                if (mimeType.startsWith("text/")) {
                    val payload = record.payload ?: continue
                    val text = String(payload, Charsets.UTF_8).trim()
                    Log.i(TAG, "MIME $mimeType: \"$text\"")
                    val r = parseCsvSensorText(text, tagId)
                    if (r != null) return r
                    continue // don't fall through to binary for text MIME
                }
            }

            // ── Priority 3: Text-first then binary fallback ───────────────────
            // For TNF_UNKNOWN or external-type records, try decoding as UTF-8
            // text first (covers misconfigured NHS 3152 tags). Only if the
            // payload is NOT printable ASCII do we attempt binary decoding.
            val payload = record.payload ?: continue
            if (payload.size >= 3 && isPrintableAscii(payload)) {
                val text = String(payload, Charsets.UTF_8).trim()
                val r = parseCsvSensorText(text, tagId)
                if (r != null) return r
            }
            if (payload.size >= 6) {
                val r = parseSensorBytes(payload, tagId)
                if (r != null) return r
            }
        }
        return null
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Requirement 4 — Continuous NfcA polling loop.
     *
     * Runs on Dispatchers.IO (already in scope.launch). Opens the NfcA
     * interface for direct ISO 14443-3A communication and reads sensor memory
     * every 2 seconds using the NFC Type 2 Tag READ command (0x30).
     *
     * TagLostException extends IOException — catching IOException covers both
     * "tag physically removed" and "transceive I/O error" reliably.
     */
    private suspend fun startNfcAPolling(tag: Tag) {
        val nfcA = NfcA.get(tag) ?: run {
            Log.w(TAG, "Tag does not support NfcA — polling aborted")
            withContext(Dispatchers.Main) { onConnectionLost() }
            return
        }
        try {
            nfcA.connect()
            nfcA.timeout = 3000   // 3 s transceive timeout
            val tagId = bytesToHex(tag.id)
            Log.i(TAG, "NfcA polling started — tag $tagId")

            // Requirement 4: while (isActive && connected) loop
            while (currentCoroutineContext().isActive) {
                try {
                    // NHS 3152 NFC Type 2 Tag READ: 0x30, pageAddress
                    // Page 4 (byte offset 16) is the standard sensor data start.
                    // Response: 16 bytes (4 pages × 4 bytes).
                    val response = nfcA.transceive(
                        byteArrayOf(0x30.toByte(), 0x04.toByte())
                    )
                    if (response != null && response.size >= 6) {
                        val reading = parseSensorBytes(response, tagId)
                        if (reading != null) {
                            Log.i(TAG,
                                "NfcA poll: T=${reading.temperature} " +
                                "pH=${reading.ph} G=${reading.glucose}")
                            csvHandler.save(reading)                 // ← persist CSV
                            withContext(Dispatchers.Main) {
                                onReadingReceived(reading)           // ← triggers StateFlow
                            }
                        }
                    }
                    // Requirement 4: poll not more than every 2 seconds
                    delay(2_000L)

                } catch (e: IOException) {
                    // TagLostException extends IOException.
                    // This is the normal, expected way the loop exits when the
                    // user moves the phone away from the sensor.
                    Log.i(TAG, "Tag left RF field (${e.javaClass.simpleName}): ${e.message}")
                    break
                }
            }
        } catch (e: IOException) {
            Log.w(TAG, "NfcA connect error: ${e.message}")
        } finally {
            try { nfcA.close() } catch (_: Exception) {}
            withContext(Dispatchers.Main) { onConnectionLost() }
            Log.i(TAG, "NfcA polling stopped")
        }
    }

    /** Immediate NDEF read (one-shot, not looping). */
    private fun tryReadNdef(tag: Tag): SensorReading? {
        val ndef = Ndef.get(tag) ?: return null
        return try {
            ndef.connect()
            val message = ndef.ndefMessage
            ndef.close()
            message?.let { parseNdefMessage(it, bytesToHex(tag.id)) }
        } catch (e: Exception) {
            Log.d(TAG, "NDEF one-shot read: ${e.message}")
            null
        }
    }

    /**
     * Requirement 3 — Strip the Status Byte and IANA language code from an
     * NFC Forum RTD_TEXT record payload.
     *
     * Payload structure:
     *   Byte 0      : Status byte
     *     Bit 7     : 0 = UTF-8, 1 = UTF-16
     *     Bits 5-0  : language-code length (e.g. "en" → 2)
     *   Bytes 1…L   : Language code (ASCII)
     *   Bytes (1+L)…: Actual text in declared encoding
     */
    private fun parseTextRecord(record: NdefRecord): String? {
        return try {
            val payload = record.payload ?: return null
            if (payload.isEmpty()) return null
            val statusByte  = payload[0]
            val isUtf16     = (statusByte.toInt() and 0x80) != 0
            val langCodeLen = statusByte.toInt() and 0x3F
            if (1 + langCodeLen >= payload.size) return null
            val charset = if (isUtf16) Charsets.UTF_16 else Charsets.UTF_8
            String(payload, 1 + langCodeLen, payload.size - 1 - langCodeLen, charset).trim()
        } catch (e: Exception) {
            Log.e(TAG, "parseTextRecord error: ${e.message}")
            null
        }
    }

    /**
     * Parse CSV / semicolon / labeled sensor text.
     *
     * Supported formats from NHS 3152 firmware variants:
     *   "36.6,7.40,95"                  — plain CSV
     *   "36.6;7.40;95"                  — semicolon
     *   "T:36.6,pH:7.40,G:95"           — labeled colon-sep
     *   "Temp=36.6 pH=7.40 Glucose=95"  — labeled equals-sep
     */
    private fun parseCsvSensorText(text: String, tagId: String): SensorReading? {
        val ts = nowTimestamp()

        // Strategy 1: plain positional (CSV / semicolon / whitespace)
        val parts = text.trim().split(Regex("[,;\\s]+"))
        if (parts.size >= 3) {
            runCatching {
                val r = SensorReading(ts,
                    parts[0].trim().toFloat(),
                    parts[1].trim().toFloat(),
                    parts[2].trim().toFloat(),
                    tagId)
                if (isPlausible(r)) return r
            }
        }

        // Strategy 2: key=value or key:value pairs
        var temp = Float.NaN; var ph = Float.NaN; var glucose = Float.NaN
        for (token in text.trim().split(Regex("[,;\\s]+"))) {
            val kv = token.split(Regex("[=:]"), 2)
            if (kv.size == 2) {
                val key = kv[0].trim().lowercase(Locale.ROOT)
                val v   = kv[1].trim().toFloatOrNull() ?: continue
                when {
                    key.startsWith("t") || "temp" in key -> temp    = v
                    key.startsWith("p") || "ph"   in key -> ph      = v
                    key.startsWith("g") || "glu"  in key -> glucose = v
                }
            }
        }
        if (!temp.isNaN() && !ph.isNaN() && !glucose.isNaN()) {
            val r = SensorReading(ts, temp, ph, glucose, tagId)
            if (isPlausible(r)) return r
        }
        return null
    }

    /**
     * Requirement 5 — NHS 3152 datasheet binary decoding.
     *
     * NHS 3152 runs an ARM Cortex-M0+ core → data stored LITTLE-ENDIAN.
     *
     * Binary format (6 bytes minimum):
     *   Bytes 0-1: Temperature  signed  int16 LE  ×0.1  °C/LSB
     *   Bytes 2-3: pH           unsigned uint16 LE ×0.01 pH/LSB
     *   Bytes 4-5: Glucose      unsigned uint16 LE direct mg/dL
     *
     * Falls back to big-endian if little-endian produces implausible values.
     */
    private fun parseSensorBytes(data: ByteArray, tagId: String): SensorReading? {
        if (data.size < 6) return null
        val ts = nowTimestamp()
        return try {
            // Primary: little-endian (native byte order for NHS 3152)
            val bufLE = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            val tempLE    = bufLE.short.toInt() / 10.0f                     // signed int16, 0.1 °C
            val phLE      = (bufLE.short.toInt() and 0xFFFF) / 100.0f       // uint16, 0.01 pH
            val glucoseLE = (bufLE.short.toInt() and 0xFFFF).toFloat()       // uint16, mg/dL
            val rLE = SensorReading(ts, tempLE, phLE, glucoseLE, tagId)
            if (isPlausible(rLE)) return rLE

            // Fallback: big-endian
            val bufBE = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
            val tempBE    = bufBE.short.toInt() / 10.0f
            val phBE      = (bufBE.short.toInt() and 0xFFFF) / 100.0f
            val glucoseBE = (bufBE.short.toInt() and 0xFFFF).toFloat()
            val rBE = SensorReading(ts, tempBE, phBE, glucoseBE, tagId)
            if (isPlausible(rBE)) rBE else null

        } catch (e: Exception) {
            Log.e(TAG, "parseSensorBytes error: ${e.message}")
            null
        }
    }

    /**
     * Physiological plausibility check.
     * Wide ranges to accommodate all NHS 3152 calibration states and edge cases.
     */
    private fun isPlausible(r: SensorReading): Boolean =
        r.temperature in -10f..80f &&
        r.ph          in 0f..14f   &&
        r.glucose     in 0f..500f

    /** True if every byte in [data] maps to a printable ASCII character. */
    private fun isPrintableAscii(data: ByteArray): Boolean {
        for (b in data) {
            val c = b.toInt() and 0xFF
            if (c < 0x20 || c > 0x7E) return false
        }
        return true
    }

    private fun bytesToHex(bytes: ByteArray): String =
        bytes.joinToString("") { "%02X".format(it) }

    private fun nowTimestamp(): String =
        SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    /** Call from Activity.onDestroy() to cancel all in-flight coroutines. */
    fun destroy() {
        scope.cancel()
    }
}
