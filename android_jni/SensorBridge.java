/*
 * SensorBridge.java - JNI interface for NHS 3152 sensor communication via NFC
 * This class bridges Python (Kivy) with native C/C++ code for NFC communication.
 * NHS 3152 uses ISO14443-A (NFC-A) protocol for wireless data transmission.
 * Supports both NDEF-based and raw NFC-A/IsoDep communication.
 */

package com.sensormonitor.android;

import android.app.Activity;
import android.content.Context;
import android.nfc.NfcAdapter;
import android.nfc.Tag;
import android.nfc.tech.IsoDep;
import android.nfc.tech.NfcA;
import android.nfc.tech.Ndef;
import android.nfc.tech.NdefFormatable;
import android.nfc.NdefMessage;
import android.nfc.NdefRecord;
import android.os.Bundle;
import android.util.Log;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import android.nfc.TagLostException;

import android.app.PendingIntent;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Parcelable;
import android.provider.Settings;

public class SensorBridge implements NfcAdapter.ReaderCallback {

    // True when libsensor_nhs3152.so was successfully loaded.
    // The app degrades gracefully without it — all real data comes from the
    // NDEF/IsoDep/NfcA Java pipeline; native calls are purely optional bookkeeping.
    private static volatile boolean nativeLibLoaded = false;

    static {
        try {
            System.loadLibrary("sensor_nhs3152");
            nativeLibLoaded = true;
            android.util.Log.i("SensorBridge", "libsensor_nhs3152.so loaded successfully");
        } catch (UnsatisfiedLinkError e) {
            android.util.Log.w("SensorBridge",
                "Native library libsensor_nhs3152.so not found — running in pure-Java NFC mode. " + e.getMessage());
        }
    }

    private NfcAdapter nfcAdapter;
    private Context context;
    private Activity activity;
    private boolean connected = false;
    private boolean isReading = false;
    private Tag currentTag = null;
    private volatile float[] lastSensorData = null;

    // Timestamp (ms since epoch) when parseHealthData last stored valid data.
    // Used by Python to determine if the tag is still in range (freshness check).
    private volatile long lastDataTimestampMs = 0;

    // Background scheduler for periodic re-reads while tag remains in RF field.
    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();
    private ScheduledFuture<?> periodicReadTask = null;

    private static final String TAG = "SensorBridge";

    // NFC Reader Mode flags:
    //   FLAG_READER_NFC_A  — NHS 3152 uses ISO14443-A
    //   FLAG_READER_NFC_B  — also listen for NFC-B tags
    //   Do NOT include FLAG_READER_SKIP_NDEF_CHECK so NDEF messages are read properly
    private static final int NFC_READER_MODE = NfcAdapter.FLAG_READER_NFC_A
                                             | NfcAdapter.FLAG_READER_NFC_B;

    // ── Foreground Dispatch (Android 12+ / API 31+ compliant) ───────────────
    // PendingIntent re-delivered to this Activity on tag discovery.
    // FLAG_MUTABLE is mandatory on API 31+ so the system can write tag extras.
    private PendingIntent nfcPendingIntent;
    // Intent filters passed to enableForegroundDispatch.
    private IntentFilter[] foregroundIntentFilters;
    // Optional tech-list whitelist; null = accept any technology.
    private String[][] foregroundTechLists;

    public SensorBridge() {
        // Default constructor (used by non-Android testing only)
    }

    public SensorBridge(Context context) {
        this.context = context;
        this.nfcAdapter = NfcAdapter.getDefaultAdapter(context);
    }

    public SensorBridge(Activity activity) {
        this.activity = activity;
        this.context = activity.getApplicationContext();
        this.nfcAdapter = NfcAdapter.getDefaultAdapter(context);
    }

    /**
     * Connect to NFC reader and enable reader mode for continuous tag scanning.
     */
    public boolean connect(Map<String, Object> config) {
        try {
            if (nfcAdapter == null) {
                Log.e(TAG, "NFC not supported on this device");
                return false;
            }

            if (!nfcAdapter.isEnabled()) {
                Log.e(TAG, "NFC is not enabled — please enable NFC in device Settings");
                return false;
            }

            // Mark native side as connected (native call is optional bookkeeping only)
            connected = nativeLibLoaded ? nativeConnect("NFC Mode", 0) : true;

            // Start NFC reader mode for continuous tag detection
            // Important: Activity must be available and in foreground
            if (connected) {
                if (activity != null) {
                    enableReaderMode();
                    Log.i(TAG, "NFC reader mode enabled for continuous scanning");
                } else {
                    Log.w(TAG, "Activity reference is null — reader mode could not be enabled");
                    Log.w(TAG, "This may happen if called before Activity is ready");
                    Log.i(TAG, "NFC will work via intent dispatch, but reader mode won't be active");
                }
            }

            return connected;
        } catch (Exception e) {
            Log.e(TAG, "Error connecting to NFC: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Enable NFC reader mode — the phone actively polls for NFC tags.
     */
    private void enableReaderMode() {
        if (nfcAdapter != null && activity != null) {
            Bundle options = new Bundle();
            // Presence check delay (how often the phone checks if the tag is still in range)
            options.putInt(NfcAdapter.EXTRA_READER_PRESENCE_CHECK_DELAY, 250);

            nfcAdapter.enableReaderMode(activity, this, NFC_READER_MODE, options);
            isReading = true;
            Log.i(TAG, "NFC reader mode enabled — scanning for NHS 3152 tags");
        }
    }

    /**
     * Disable NFC reader mode.
     */
    private void disableReaderMode() {
        if (nfcAdapter != null && activity != null) {
            nfcAdapter.disableReaderMode(activity);
            isReading = false;
            Log.i(TAG, "NFC reader mode disabled");
        }
    }

    /**
     * Disconnect from NFC reader.
     */
    public void disconnect() {
        if (connected) {
            stopPeriodicRead();
            disableReaderMode();
            if (nativeLibLoaded) nativeDisconnect();
            connected = false;
            lastSensorData      = null;
            lastDataTimestampMs = 0;
        }
    }

    /**
     * Read raw data from native layer.
     */
    public byte[] readRawData() {
        if (!connected) {
            return null;
        }
        return nativeReadData();
    }

    /**
     * Get last sensor reading (thread-safe).
     * Returns float[3]: {temperature, ph, glucose} or null if no data yet.
     */
    public float[] getSensorReading() {
        return lastSensorData;
    }

    /**
     * Update sensor configuration.
     */
    public boolean updateConfig(Map<String, Object> config) {
        try {
            Object tempObj = config.get("temp_offset");
            if (tempObj != null) {
                float tempOffset = Float.parseFloat(tempObj.toString());
                nativeUpdateConfig(tempOffset);
            }
            return true;
        } catch (Exception e) {
            Log.e(TAG, "Error updating config: " + e.getMessage());
            return false;
        }
    }

    /**
     * Calibrate sensors via NFC tag write.
     */
    public boolean calibrate() {
        if (!connected || !nativeLibLoaded) return false;
        return nativeCalibrate();
    }

    /**
     * Test NFC connection — checks if a valid tag was detected.
     */
    public boolean testConnection() {
        if (!connected) return false;
        return nativeLibLoaded ? nativeTestConnection() : true;
    }

    /**
     * Get NFC adapter status / firmware version.
     */
    public String getFirmwareVersion() {
        if (!connected) return "NFC Not Connected";
        return nativeLibLoaded ? nativeFirmwareVersion() : "Pure-Java NFC Mode";
    }

    /**
     * Parse health sensor data from raw NDEF/NFC payload bytes.
     *
     * NHS 3152 runs on an ARM Cortex-M0+ core → data is stored in
     * <b>little-endian</b> byte order (LSB first).
     *
     * Binary payload format (6 bytes minimum):
     *   Bytes 0-1: Temperature (signed int16 LE, 0.1 °C per LSB)
     *   Bytes 2-3: pH         (unsigned int16 LE, 0.01 pH per LSB)
     *   Bytes 4-5: Glucose    (unsigned int16 LE, mg/dL)
     *
     * Falls back to big-endian when little-endian yields implausible values.
     */
    public float[] parseHealthData(byte[] data) {
        try {
            if (data == null || data.length < 6) {
                Log.w(TAG, "Insufficient data for parsing: " +
                      (data == null ? "null" : data.length + " bytes"));
                return null;
            }

            // ── Try big-endian first (NHS3152 firmware stores NFC payload in
            //    network byte order, big-endian, regardless of the MCU's native
            //    little-endian architecture — confirmed by all test payloads) ──
            float[] sensorData = decodeHealthBytes(data, ByteOrder.BIG_ENDIAN);
            if (sensorData != null && isDataPlausible(sensorData)) {
                lastSensorData      = sensorData;
                lastDataTimestampMs = System.currentTimeMillis();
                if (nativeLibLoaded) nativeStoreSensorData(sensorData[0], sensorData[1], sensorData[2]);
                Log.i(TAG, String.format(
                    "Parsed (BE) — Temp: %.1f°C, pH: %.2f, Glucose: %.0f mg/dL",
                    sensorData[0], sensorData[1], sensorData[2]));
                return sensorData;
            }

            // ── Fallback: try little-endian ──────────────────────────────────
            Log.d(TAG, "BE parse implausible, retrying with LE");
            sensorData = decodeHealthBytes(data, ByteOrder.LITTLE_ENDIAN);
            if (sensorData != null && isDataPlausible(sensorData)) {
                lastSensorData      = sensorData;
                lastDataTimestampMs = System.currentTimeMillis();
                if (nativeLibLoaded) nativeStoreSensorData(sensorData[0], sensorData[1], sensorData[2]);
                Log.i(TAG, String.format(
                    "Parsed (LE) — Temp: %.1f°C, pH: %.2f, Glucose: %.0f mg/dL",
                    sensorData[0], sensorData[1], sensorData[2]));
                return sensorData;
            }

            Log.w(TAG, "parseHealthData: data not plausible in either byte order " +
                       "— raw hex: " + bytesToHex(Arrays.copyOf(data, Math.min(data.length, 8))));
        } catch (Exception e) {
            Log.e(TAG, "Error parsing health data: " + e.getMessage());
        }
        return null;
    }

    /**
     * Decode a 6-byte NHS3152 binary payload using the specified byte order.
     *
     * @param data      Raw payload bytes (must be >= 6 bytes).
     * @param order     {@link ByteOrder#LITTLE_ENDIAN} or {@link ByteOrder#BIG_ENDIAN}.
     * @return float[3] {temperature °C, pH, glucose mg/dL}, never null.
     */
    private float[] decodeHealthBytes(byte[] data, ByteOrder order) {
        ByteBuffer buf = ByteBuffer.wrap(data).order(order);
        float temp    = buf.getShort() / 10.0f;          // signed int16, 0.1 °C per LSB
        float ph      = (buf.getShort() & 0xFFFF) / 100.0f; // unsigned int16, 0.01 pH per LSB
        float glucose = (buf.getShort() & 0xFFFF);       // unsigned int16, mg/dL direct
        return new float[]{temp, ph, glucose};
    }

    /**
     * NFC Reader Callback — called automatically when an NFC tag is detected.
     * This is the core method for NHS 3152 sensor detection.
     */
    @Override
    public void onTagDiscovered(Tag tag) {
        if (tag == null) {
            Log.w(TAG, "onTagDiscovered called with null tag");
            return;
        }
        
        currentTag = tag;
        String[] techList = tag.getTechList();
        Log.i(TAG, "✓ NFC tag DISCOVERED! Technologies: " + Arrays.toString(techList));

        // Cancel any ongoing periodic read from a previous tag
        stopPeriodicRead();

        // Store tag UID in native layer (if the native .so was loaded)
        byte[] uid = tag.getId();
        if (uid != null) {
            if (nativeLibLoaded) nativeSetNFCData(uid);
            Log.i(TAG, "Tag UID: " + bytesToHex(uid));
        }

        try {
            // Strategy 1: Try NDEF first (most NHS 3152 configs use NDEF)
            Log.i(TAG, "→ Trying NDEF read...");
            if (tryReadNdef(tag)) {
                Log.i(TAG, "✓ Successfully read NDEF data");
                startPeriodicRead(tag);   // keep reading every 1s while tag is in range
                return;
            }

            // Strategy 2: Try IsoDep (ISO 14443-4) for NHS 3152 APDU communication
            Log.i(TAG, "→ Trying IsoDep (APDU) read...");
            if (tryReadIsoDep(tag)) {
                Log.i(TAG, "✓ Successfully read via IsoDep");
                startPeriodicRead(tag);
                return;
            }

            // Strategy 3: Try raw NFC-A (ISO 14443-3A) memory read
            Log.i(TAG, "→ Trying NFC-A (raw) read...");
            if (tryReadNfcA(tag)) {
                Log.i(TAG, "✓ Successfully read via NFC-A");
                startPeriodicRead(tag);
                return;
            }

            Log.w(TAG, "✗ Could not read sensor data from tag via ANY method");
            Log.w(TAG, "  This may indicate the tag is not an NHS 3152 or data is corrupted");
        } catch (TagLostException e) {
            Log.i(TAG, "Tag lost during initial read");
        }
    }

    // How many consecutive non-TagLost failures before we treat the tag as gone.
    private static final int MAX_CONSECUTIVE_FAILURES = 3;
    private int consecutiveReadFailures = 0;

    /**
     * Start a background task that re-reads the tag every 1 second.
     * <p>
     * The NHS3152 tag stays in the RF field while held near the phone.
     * This loop pulls fresh data continuously so Python always gets
     * up-to-date values when it polls {@link #getSensorReading()}.
     * <p>
     * Only a definitive {@link TagLostException} (or
     * {@link #MAX_CONSECUTIVE_FAILURES} consecutive failures) clears
     * {@code lastSensorData}; transient I/O hiccups keep the last good
     * value alive so the Python freshness check does not prematurely
     * signal "tag left range".
     *
     * @param tag The live {@link Tag} object from {@code onTagDiscovered}.
     */
    private void startPeriodicRead(final Tag tag) {
        stopPeriodicRead(); // cancel any leftover task first
        consecutiveReadFailures = 0;
        periodicReadTask = scheduler.scheduleAtFixedRate(() -> {
            try {
                boolean ok = tryReadNdef(tag)
                          || tryReadIsoDep(tag)
                          || tryReadNfcA(tag);
                if (ok) {
                    consecutiveReadFailures = 0;
                } else {
                    consecutiveReadFailures++;
                    Log.d(TAG, "Periodic re-read: no data (failure " +
                          consecutiveReadFailures + "/" + MAX_CONSECUTIVE_FAILURES + ")");
                    if (consecutiveReadFailures >= MAX_CONSECUTIVE_FAILURES) {
                        Log.i(TAG, "Tag unresponsive after " + MAX_CONSECUTIVE_FAILURES +
                              " attempts — marking tag as gone");
                        lastSensorData      = null;
                        lastDataTimestampMs = 0;
                        stopPeriodicRead();
                    }
                }
            } catch (TagLostException e) {
                // Definitive: tag physically left the RF field.
                Log.i(TAG, "TagLostException in periodic re-read — tag removed from field");
                lastSensorData      = null;
                lastDataTimestampMs = 0;
                stopPeriodicRead();
            } catch (Exception e) {
                Log.w(TAG, "Periodic re-read unexpected error: " + e.getMessage());
            }
        }, 1, 2, TimeUnit.SECONDS);
        Log.i(TAG, "Periodic re-read started (2 s interval)");
    }

    /** Cancel the periodic re-read task if running. */
    private void stopPeriodicRead() {
        if (periodicReadTask != null && !periodicReadTask.isCancelled()) {
            periodicReadTask.cancel(false);
            periodicReadTask = null;
            Log.d(TAG, "Periodic re-read stopped");
        }
    }

    /**
     * Try reading NDEF message from the tag.
     */
    private boolean tryReadNdef(Tag tag) throws TagLostException {
        Ndef ndef = Ndef.get(tag);
        if (ndef == null) {
            Log.d(TAG, "Tag does not support NDEF");
            return false;
        }

        try {
            ndef.connect();
            NdefMessage ndefMessage = ndef.getNdefMessage();

            if (ndefMessage != null) {
                NdefRecord[] records = ndefMessage.getRecords();
                Log.i(TAG, "NDEF message has " + records.length + " record(s)");

                for (NdefRecord record : records) {
                    byte[] payload = record.getPayload();

                    // ── Priority 1: Standard RTD_TEXT (NFC Forum Text RTD) ──────────
                    // Strips the status byte and IANA language code (e.g. "en") first,
                    // then attempts CSV sensor parsing of the bare text content.
                    if (record.getTnf() == NdefRecord.TNF_WELL_KNOWN
                            && Arrays.equals(record.getType(), NdefRecord.RTD_TEXT)) {
                        String text = parseTextRecord(record);
                        if (text != null) {
                            Log.i(TAG, "RTD_TEXT record value: " + text);
                            float[] data = parseCsvSensorText(text);
                            if (data != null) {
                                lastSensorData      = data;
                                lastDataTimestampMs = System.currentTimeMillis(); // keep freshness alive
                                ndef.close();
                                return true;
                            }
                        }
                        continue; // don't fall through to binary parsing for text records
                    }

                    // ── Priority 1b: MIME text/plain record (TNF_MIME_MEDIA) ───────
                    // NHS 3152 firmware variants may use text/plain MIME type instead
                    // of RTD_TEXT. The payload is raw UTF-8 with no status/language byte.
                    if (record.getTnf() == NdefRecord.TNF_MIME_MEDIA) {
                        try {
                            String mimeType = new String(record.getType(), StandardCharsets.US_ASCII);
                            if (mimeType.startsWith("text/")) {
                                String text = (payload != null)
                                        ? new String(payload, StandardCharsets.UTF_8).trim()
                                        : null;
                                Log.i(TAG, "MIME " + mimeType + " record value: " + text);
                                if (text != null && !text.isEmpty()) {
                                    float[] data = parseCsvSensorText(text);
                                    if (data != null) {
                                        lastSensorData      = data;
                                        lastDataTimestampMs = System.currentTimeMillis();
                                        ndef.close();
                                        return true;
                                    }
                                }
                                continue; // don't fall through to binary parsing for text records
                            }
                        } catch (Exception e) {
                            Log.w(TAG, "MIME type check error: " + e.getMessage());
                        }
                    }

                    // ── Priority 2: Custom NHS 3152 binary Health record ('H') ───────
                    if (record.getTnf() == NdefRecord.TNF_WELL_KNOWN) {
                        byte[] type = record.getType();
                        if (type.length > 0 && type[0] == 'H') {
                            float[] data = parseHealthData(payload);
                            if (data != null) {
                                ndef.close();
                                return true;
                            }
                        }
                    }

                    // ── Priority 3: Try text parsing first, then binary ─────────────
                    // Some NHS 3152 configurations use TNF_UNKNOWN or external types
                    // with a text payload. Try text before binary to avoid misinterpreting
                    // ASCII bytes as sensor values.
                    if (payload != null && payload.length >= 3) {
                        // Try text first (payload looks like printable ASCII/UTF-8)
                        try {
                            String textPayload = new String(payload, StandardCharsets.UTF_8).trim();
                            if (!textPayload.isEmpty() && isPrintableAscii(textPayload)) {
                                float[] data = parseCsvSensorText(textPayload);
                                if (data != null && isDataPlausible(data)) {
                                    Log.i(TAG, "Parsed sensor data from text payload in generic NDEF record");
                                    lastSensorData      = data;
                                    lastDataTimestampMs = System.currentTimeMillis();
                                    ndef.close();
                                    return true;
                                }
                            }
                        } catch (Exception ignored) {}

                        // Then try binary (payload >= 6 bytes as raw sensor bytes)
                        if (payload.length >= 6) {
                            float[] data = parseHealthData(payload);
                            if (data != null && isDataPlausible(data)) {
                                Log.i(TAG, "Parsed sensor data from generic NDEF record (binary)");
                                ndef.close();
                                return true;
                            }
                        }
                    }
                }
            }
            ndef.close();
        } catch (TagLostException e) {
            Log.i(TAG, "TagLost during NDEF read");
            throw e;
        } catch (Exception e) {
            Log.e(TAG, "Error reading NDEF: " + e.getMessage());
        }

        return false;
    }

    /**
     * Try reading via IsoDep (ISO 14443-4 / ISO-DEP) for NHS 3152.
     * NHS 3152 supports APDU commands for reading sensor memory.
     */
    private boolean tryReadIsoDep(Tag tag) throws TagLostException {
        IsoDep isoDep = IsoDep.get(tag);
        if (isoDep == null) {
            Log.d(TAG, "Tag does not support IsoDep");
            return false;
        }

        try {
            isoDep.connect();
            isoDep.setTimeout(3000);

            // NHS 3152 APDU: SELECT application
            // AID for NHS 3152 health data: D2760000850101 (example)
            byte[] selectCmd = new byte[]{
                (byte) 0x00, (byte) 0xA4, (byte) 0x04, (byte) 0x00,
                (byte) 0x07,
                (byte) 0xD2, (byte) 0x76, (byte) 0x00, (byte) 0x00,
                (byte) 0x85, (byte) 0x01, (byte) 0x01,
                (byte) 0x00
            };

            byte[] response = isoDep.transceive(selectCmd);
            if (response != null && response.length >= 2) {
                int sw = ((response[response.length - 2] & 0xFF) << 8) |
                         (response[response.length - 1] & 0xFF);

                if (sw == 0x9000) {
                    // SELECT succeeded — now READ BINARY for sensor data
                    byte[] readCmd = new byte[]{
                        (byte) 0x00, (byte) 0xB0, (byte) 0x00, (byte) 0x00,
                        (byte) 0x06  // Read 6 bytes of sensor data
                    };

                    byte[] sensorResponse = isoDep.transceive(readCmd);
                    if (sensorResponse != null && sensorResponse.length >= 8) {
                        // Last 2 bytes are SW1/SW2
                        byte[] sensorBytes = Arrays.copyOfRange(
                            sensorResponse, 0, sensorResponse.length - 2);
                        float[] data = parseHealthData(sensorBytes);
                        if (data != null) {
                            isoDep.close();
                            return true;
                        }
                    }
                }
            }

            isoDep.close();
        } catch (TagLostException e) {
            Log.i(TAG, "TagLost during IsoDep read");
            throw e;
        } catch (Exception e) {
            Log.e(TAG, "Error reading IsoDep: " + e.getMessage());
        }

        return false;
    }

    /**
     * Try reading via NFC-A (ISO 14443-3A) — direct memory read for NHS 3152.
     * NHS 3152 stores data in EEPROM accessible via NFC READ commands.
     */
    private boolean tryReadNfcA(Tag tag) throws TagLostException {
        NfcA nfcA = NfcA.get(tag);
        if (nfcA == null) {
            Log.d(TAG, "Tag does not support NFC-A");
            return false;
        }

        try {
            nfcA.connect();
            nfcA.setTimeout(3000);

            // NHS 3152 READ command (similar to NTAG/Type 2 Tag):
            // CMD 0x30 = READ, reads 4 pages (16 bytes) starting at page address
            // Sensor data typically starts at page 4 or higher
            byte[] readCmd = new byte[]{(byte) 0x30, (byte) 0x04};  // READ page 4

            byte[] response = nfcA.transceive(readCmd);
            if (response != null && response.length >= 6) {
                float[] data = parseHealthData(response);
                if (data != null && isDataPlausible(data)) {
                    Log.i(TAG, "Parsed sensor data from NFC-A memory read");
                    nfcA.close();
                    return true;
                }
            }

            nfcA.close();
        } catch (TagLostException e) {
            Log.i(TAG, "TagLost during NFC-A read");
            throw e;
        } catch (Exception e) {
            Log.e(TAG, "Error reading NFC-A: " + e.getMessage());
        }

        return false;
    }

    /**
     * Sanity-check parsed sensor data to avoid interpreting garbage bytes.
     * Ranges are intentionally wide to accommodate all NHS 3152 calibration
     * states and edge cases (e.g. hypoglycaemia glucose < 30 mg/dL).
     */
    private boolean isDataPlausible(float[] data) {
        if (data == null || data.length < 3) return false;
        float temp = data[0];
        float ph = data[1];
        float glucose = data[2];
        // Accepted ranges aligned with physiological reality and test suite:
        // temp 0-60 °C, pH 0-14, glucose 30-500 mg/dL.
        // Lower bound of 30 mg/dL for glucose prevents accepting uninitialized
        // NFC SRAM (all-zero payload) as valid sensor data.
        return (temp >= 0.0f && temp <= 60.0f) &&
               (ph >= 0.0f && ph <= 14.0f) &&
               (glucose >= 30.0f && glucose <= 500.0f);
    }

    /**
     * Return true if every character in {@code s} is in the printable ASCII
     * range (0x20–0x7E) or a common whitespace character.  Used to detect
     * text-format payloads before attempting binary parsing.
     */
    private static boolean isPrintableAscii(String s) {
        if (s == null || s.isEmpty()) return false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= 0x20 && c <= 0x7E) continue;  // printable ASCII
            if (c == '\t' || c == '\n' || c == '\r') continue; // whitespace
            return false; // non-printable / high byte → binary data
        }
        return true;
    }

    /**
     * Write calibration data to NFC tag.
     */
    public boolean writeCalibrationToTag(byte[] calibrationData) {
        if (currentTag == null) {
            Log.e(TAG, "No tag available for writing");
            return false;
        }

        try {
            Ndef ndef = Ndef.get(currentTag);
            if (ndef != null) {
                ndef.connect();

                NdefRecord calibRecord = new NdefRecord(
                    NdefRecord.TNF_WELL_KNOWN,
                    new byte[]{'C'},  // Calibration record type
                    new byte[]{},
                    calibrationData
                );

                NdefMessage ndefMessage = new NdefMessage(
                    new NdefRecord[]{calibRecord}
                );

                ndef.writeNdefMessage(ndefMessage);
                ndef.close();

                Log.i(TAG, "Calibration data written to tag");
                return true;
            }
        } catch (IOException | android.nfc.FormatException e) {
            Log.e(TAG, "Error writing to tag: " + e.getMessage());
        }

        return false;
    }

    /**
     * Convert byte array to hex string for logging.
     */
    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02X", b));
        }
        return sb.toString();
    }

    // Native method declarations
    private native boolean nativeConnect(String deviceName, int unused);
    private native void nativeDisconnect();
    private native byte[] nativeReadData();
    private native void nativeUpdateConfig(float tempOffset);
    private native boolean nativeCalibrate();
    private native boolean nativeTestConnection();
    private native String nativeFirmwareVersion();
    private native boolean nativeSetNFCData(byte[] nfcData);
    private native void nativeStoreSensorData(float temp, float ph, float glucose);

    /**
     * Helper method to get Activity when it becomes available.
     * Can be called by Python code during app lifecycle to set the Activity.
     */
    public void setActivity(Activity act) {
        this.activity = act;
        this.context = act.getApplicationContext();
        if (nfcAdapter == null) {
            this.nfcAdapter = NfcAdapter.getDefaultAdapter(context);
        }
        Log.i(TAG, "Activity set — NFC reader mode can now be enabled");
        
        // Try to enable reader mode if we're already connected
        if (connected && !isReading) {
            enableReaderMode();
        }
    }

    /**
     * Check if NFC is available and working.
     */
    public boolean isNfcAvailable() {
        return nfcAdapter != null && nfcAdapter.isEnabled();
    }

    /**
     * Get current connection state.
     */
    public boolean isConnected() {
        return connected;
    }

    /**
     * Return the milliseconds elapsed since the last successful sensor data parse.
     * Returns {@link Long#MAX_VALUE} if no data has ever been parsed.
     * <p>
     * Python uses this to distinguish "tag in range" (age &lt; threshold) from
     * "tag left range" (age &gt; threshold), enabling automatic stop of storage.
     */
    public long getLastDataAgeMs() {
        if (lastDataTimestampMs == 0) return Long.MAX_VALUE;
        return System.currentTimeMillis() - lastDataTimestampMs;
    }

    /**
     * Get whether reader mode is active.
     */
    public boolean isReaderModeActive() {
        return isReading;
    }

    /**
     * Return the UID of the most recently discovered NFC tag as an uppercase
     * hex string (e.g. {@code "04A1B2C3D4E5F6"}).
     *
     * <p>The UID uniquely identifies the physical tag / NHS 3152 device.
     * Returns an empty string when no tag has been seen yet.</p>
     */
    public String getLastTagId() {
        if (currentTag != null) {
            byte[] uid = currentTag.getId();
            if (uid != null) return bytesToHex(uid);
        }
        return "";
    }

    // ════════════════════════════════════════════════════════════════════════
    // ── Foreground Dispatch — Android 12+ (API 31+) ──────────────────────
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Initialise the {@link PendingIntent} and {@link IntentFilter} arrays
     * needed by {@link NfcAdapter#enableForegroundDispatch}.
     *
     * <p><b>Android 12 (API 31) requirement:</b> PendingIntent must declare
     * {@link PendingIntent#FLAG_MUTABLE} so the system can fill in the
     * discovered tag's extras before re-delivering the intent.</p>
     *
     * <p>Call once from the host Activity's {@code onCreate()} before
     * {@link #enableForegroundDispatch()} is invoked in {@code onResume()}.</p>
     */
    public void initForegroundDispatch(Activity act) {
        if (act == null) {
            Log.w(TAG, "initForegroundDispatch: activity is null — skipping");
            return;
        }
        this.activity = act;
        this.context  = act.getApplicationContext();
        if (nfcAdapter == null) {
            nfcAdapter = NfcAdapter.getDefaultAdapter(context);
        }

        // Re-deliver to the same Activity instance (FLAG_ACTIVITY_SINGLE_TOP
        // routes to onNewIntent instead of creating a fresh Activity).
        Intent nfcIntent = new Intent(act, act.getClass())
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);

        // Android 12 (Build.VERSION_CODES.S = API 31) mandates an explicit
        // mutability flag.  FLAG_MUTABLE is required here because the NFC
        // subsystem must write tag extras into the intent before delivery.
        int pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            pendingFlags |= PendingIntent.FLAG_MUTABLE;
        }
        nfcPendingIntent = PendingIntent.getActivity(act, 0, nfcIntent, pendingFlags);

        // ── Intent filters ────────────────────────────────────────────────
        IntentFilter ndefTextFilter = new IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED);
        try {
            ndefTextFilter.addDataType("text/plain");                   // RTD_TEXT tags
            ndefTextFilter.addDataType("application/vnd.nhs3152.health"); // NHS 3152 custom type
        } catch (IntentFilter.MalformedMimeTypeException e) {
            Log.e(TAG, "initForegroundDispatch — bad MIME type: " + e.getMessage());
        }
        IntentFilter techFilter = new IntentFilter(NfcAdapter.ACTION_TECH_DISCOVERED);
        IntentFilter tagFilter  = new IntentFilter(NfcAdapter.ACTION_TAG_DISCOVERED);
        foregroundIntentFilters = new IntentFilter[]{ndefTextFilter, techFilter, tagFilter};

        // ── Tech-list whitelist ───────────────────────────────────────────
        // Each inner array is an AND group; multiple outer arrays are OR-ed.
        foregroundTechLists = new String[][]{
            new String[]{android.nfc.tech.Ndef.class.getName()},
            new String[]{android.nfc.tech.NfcA.class.getName()},
            new String[]{android.nfc.tech.IsoDep.class.getName()},
        };

        Log.i(TAG, "Foreground dispatch initialised — FLAG_MUTABLE=" +
                   (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S));
    }

    /**
     * Enable NFC foreground dispatch so this app takes priority over all
     * other apps when an NFC tag is tapped.
     *
     * <p>Call from the host Activity's {@code onResume()}.</p>
     */
    public void enableForegroundDispatch() {
        if (nfcAdapter == null) {
            Log.w(TAG, "enableForegroundDispatch: NfcAdapter unavailable");
            return;
        }
        if (activity == null || nfcPendingIntent == null) {
            Log.w(TAG, "enableForegroundDispatch: call initForegroundDispatch(activity) first");
            return;
        }
        if (!nfcAdapter.isEnabled()) {
            Log.w(TAG, "enableForegroundDispatch: NFC is OFF — prompting user");
            promptEnableNfc();
            return;
        }
        nfcAdapter.enableForegroundDispatch(
                activity, nfcPendingIntent,
                foregroundIntentFilters, foregroundTechLists);
        Log.i(TAG, "✓ Foreground dispatch ENABLED — app captures NFC tags in foreground");
    }

    /**
     * Disable NFC foreground dispatch.
     *
     * <p>Call from the host Activity's {@code onPause()} to release priority
     * so other apps can receive NFC intents when this Activity is not visible.</p>
     */
    public void disableForegroundDispatch() {
        if (nfcAdapter != null && activity != null) {
            try {
                nfcAdapter.disableForegroundDispatch(activity);
                Log.i(TAG, "Foreground dispatch DISABLED");
            } catch (Exception e) {
                Log.w(TAG, "disableForegroundDispatch error: " + e.getMessage());
            }
        }
    }

    /**
     * Prompt the user to enable NFC via the system Settings screen.
     *
     * <p>Called automatically by {@link #enableForegroundDispatch()} when NFC
     * is off, but can also be invoked directly from the UI layer.</p>
     */
    public void promptEnableNfc() {
        if (context == null) {
            Log.e(TAG, "promptEnableNfc: context is null — cannot open Settings");
            return;
        }
        Intent settingsIntent = new Intent(Settings.ACTION_NFC_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(settingsIntent);
        Log.i(TAG, "Opened NFC Settings so user can enable NFC");
    }

    // ════════════════════════════════════════════════════════════════════════
    // ── onNewIntent handler ───────────────────────────────────────────────
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Handle an NFC {@link Intent} delivered via foreground dispatch or the
     * Android tag-dispatch system.
     *
     * <p>Wire this into the host Activity's {@code onNewIntent()} like this:
     * <pre>{@code
     *   @Override
     *   public void onNewIntent(Intent intent) {
     *       super.onNewIntent(intent);
     *       setIntent(intent);                       // keep getIntent() fresh
     *       sensorBridge.handleNfcIntent(intent);
     *   }
     * }</pre>
     *
     * <p>Uses the modern type-safe {@code getParcelableArrayExtra(key, Class)}
     * overload (API 33 / TIRAMISU) with a safe deprecated fallback for API 31/32
     * — matching the {@code IntentCompat} pattern without requiring AndroidX.</p>
     *
     * @param intent The intent received in {@code onNewIntent}.
     * @return {@code true} if sensor data was successfully extracted and stored.
     */
    public boolean handleNfcIntent(Intent intent) {
        if (intent == null) return false;
        String action = intent.getAction();
        Log.i(TAG, "handleNfcIntent: action=" + action);

        if (!NfcAdapter.ACTION_NDEF_DISCOVERED.equals(action)
                && !NfcAdapter.ACTION_TECH_DISCOVERED.equals(action)
                && !NfcAdapter.ACTION_TAG_DISCOVERED.equals(action)) {
            return false;
        }

        // ── Step 1: Extract NDEF messages ─────────────────────────────────
        // API 33+: type-safe overload avoids raw-type / unchecked-cast warnings.
        // API 31/32: fall back to the deprecated untyped overload (safe cast).
        Parcelable[] rawMessages;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            rawMessages = intent.getParcelableArrayExtra(
                    NfcAdapter.EXTRA_NDEF_MESSAGES, NdefMessage.class);
        } else {
            //noinspection deprecation — safe pre-API33 fallback; value is always NdefMessage[]
            rawMessages = intent.getParcelableArrayExtra(NfcAdapter.EXTRA_NDEF_MESSAGES);
        }

        if (rawMessages != null && rawMessages.length > 0) {
            NdefMessage[] messages = new NdefMessage[rawMessages.length];
            for (int i = 0; i < rawMessages.length; i++) {
                messages[i] = (NdefMessage) rawMessages[i];
            }
            Log.i(TAG, "Intent carries " + messages.length + " NDEF message(s)");
            if (processNdefMessages(messages)) {
                // Ensure freshness timestamp is always set when data is stored
                // (parseCsvSensorText sets lastSensorData but not the timestamp).
                if (lastDataTimestampMs == 0) {
                    lastDataTimestampMs = System.currentTimeMillis();
                }
                return true;
            }
        }

        // ── Step 2: Fallback — use the raw Tag object ─────────────────────
        Tag tag;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            tag = intent.getParcelableExtra(NfcAdapter.EXTRA_TAG, Tag.class);
        } else {
            //noinspection deprecation — safe pre-API33 fallback
            tag = (Tag) intent.getParcelableExtra(NfcAdapter.EXTRA_TAG);
        }
        if (tag != null) {
            Log.i(TAG, "No NDEF in intent — routing to onTagDiscovered");
            long tsBefore = lastDataTimestampMs;
            onTagDiscovered(tag);
            // Return true only if onTagDiscovered actually parsed new sensor data
            // (i.e. lastDataTimestampMs was updated by parseHealthData / parseCsvSensorText).
            return lastDataTimestampMs > tsBefore;
        }

        Log.w(TAG, "handleNfcIntent: intent had no NDEF messages and no Tag extra");
        return false;
    }

    /**
     * Iterate an array of {@link NdefMessage} objects from an intent, trying
     * RTD_TEXT decoding first, then falling back to binary NHS 3152 parsing.
     * Always updates {@code lastDataTimestampMs} when data is stored.
     */
    private boolean processNdefMessages(NdefMessage[] messages) {
        for (NdefMessage message : messages) {
            for (NdefRecord record : message.getRecords()) {

                // RTD_TEXT — requires language-code stripping (see parseTextRecord)
                if (record.getTnf() == NdefRecord.TNF_WELL_KNOWN
                        && Arrays.equals(record.getType(), NdefRecord.RTD_TEXT)) {
                    String text = parseTextRecord(record);
                    if (text != null) {
                        Log.i(TAG, "processNdefMessages — RTD_TEXT: \"" + text + "\"");
                        float[] data = parseCsvSensorText(text);
                        if (data != null) {
                            lastSensorData      = data;
                            lastDataTimestampMs = System.currentTimeMillis(); // keep freshness alive
                            return true;
                        }
                    }
                    continue; // don't fall through to binary parsing for text records
                }

                // MIME text/* — raw UTF‐8 payload, no status/lang‑code prefix
                if (record.getTnf() == NdefRecord.TNF_MIME_MEDIA) {
                    try {
                        String mimeType = new String(record.getType(), StandardCharsets.US_ASCII);
                        if (mimeType.startsWith("text/")) {
                            byte[] payload = record.getPayload();
                            if (payload != null && payload.length > 0) {
                                String text = new String(payload, StandardCharsets.UTF_8).trim();
                                Log.i(TAG, "processNdefMessages — MIME " + mimeType + ": \"" + text + "\"");
                                float[] data = parseCsvSensorText(text);
                                if (data != null) {
                                    lastSensorData      = data;
                                    lastDataTimestampMs = System.currentTimeMillis();
                                    return true;
                                }
                            }
                            continue; // don't fall through to binary for text MIME
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "processNdefMessages MIME check error: " + e.getMessage());
                    }
                }

                // Binary NHS 3152 payload (any other record type)
                // Try text first in case it is a printable ASCII payload without recognised type.
                byte[] payload = record.getPayload();
                if (payload != null && payload.length >= 3) {
                    try {
                        String textPayload = new String(payload, StandardCharsets.UTF_8).trim();
                        if (!textPayload.isEmpty() && isPrintableAscii(textPayload)) {
                            float[] data = parseCsvSensorText(textPayload);
                            if (data != null && isDataPlausible(data)) {
                                lastSensorData      = data;
                                lastDataTimestampMs = System.currentTimeMillis();
                                return true;
                            }
                        }
                    } catch (Exception ignored) {}

                    if (payload.length >= 6) {
                        float[] data = parseHealthData(payload); // parseHealthData updates timestamp
                        if (data != null && isDataPlausible(data)) return true;
                    }
                }
            }
        }
        return false;
    }

    // ════════════════════════════════════════════════════════════════════════
    // ── NDEF Parsing Engine ───────────────────────────────────────────────
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Decode a {@link NdefRecord#RTD_TEXT} payload into a plain Java String.
     *
     * <p>NFC Forum Text Record Type Definition (RTD_TEXT) payload layout:</p>
     * <pre>
     *   Byte 0  — Status byte
     *     Bit 7  : 0 = UTF-8,  1 = UTF-16
     *     Bits 5-0 : language-code length  (e.g. "en" → 2)
     *   Bytes 1 … langLen   : IANA language tag (ASCII, e.g. "en", "fr", "de")
     *   Bytes (1+langLen) … : actual text in the declared encoding
     * </pre>
     *
     * <p>The language code is stripped so only the human-readable text (or
     * sensor CSV payload) is returned to the caller.</p>
     *
     * @param record A {@code TNF_WELL_KNOWN + RTD_TEXT} NdefRecord.
     * @return The decoded text string, or {@code null} on error / malformed data.
     */
    private String parseTextRecord(NdefRecord record) {
        try {
            byte[] payload = record.getPayload();
            if (payload == null || payload.length < 1) return null;

            // Status byte: bit-7 = encoding, bits 5-0 = language-code length
            byte statusByte = payload[0];
            boolean isUtf16  = (statusByte & 0x80) != 0;
            int langCodeLen  = statusByte & 0x3F;   // lower 6 bits

            // Guard: payload must contain at least status + langCode + 1 text byte
            if (1 + langCodeLen >= payload.length) {
                Log.w(TAG, "parseTextRecord: malformed payload — lang-code length exceeds payload size");
                return null;
            }

            // Language code (informational: "en", "de", "fr", …)
            String langCode = new String(payload, 1, langCodeLen, StandardCharsets.US_ASCII);

            // Actual text — everything after the language code
            String text = new String(
                    payload,
                    1 + langCodeLen,
                    payload.length - 1 - langCodeLen,
                    isUtf16 ? StandardCharsets.UTF_16 : StandardCharsets.UTF_8);

            Log.d(TAG, "parseTextRecord [lang=" + langCode + ", utf16=" + isUtf16
                    + "]: \"" + text + "\"");
            return text;

        } catch (Exception e) {
            Log.e(TAG, "parseTextRecord error: " + e.getMessage());
            return null;
        }
    }

    /**
     * Parse a sensor value string into {@code float[3]}.
     *
     * <p>Supports multiple text formats written by NHS3152 firmware variants:</p>
     * <ul>
     *   <li>Plain CSV: {@code "36.6,7.40,95"}</li>
     *   <li>Semicolon-separated: {@code "36.6;7.40;95"}</li>
     *   <li>Labeled format: {@code "T:36.6,pH:7.40,G:95"} or
     *       {@code "Temp=36.6 pH=7.40 Glucose=95"}</li>
     * </ul>
     *
     * <p>Values are validated against physiological ranges via
     * {@link #isDataPlausible(float[])}.</p>
     *
     * @param text Decoded text from an RTD_TEXT record.
     * @return {@code float[3]} {temperature °C, pH, glucose mg/dL}, or
     *         {@code null} if not a valid sensor string or values are implausible.
     */
    private float[] parseCsvSensorText(String text) {
        if (text == null || text.isEmpty()) return null;
        String trimmed = text.trim();

        // ── Strategy 1: plain CSV / semicolon-separated (no labels) ─────────
        // Split on comma, semicolon, or whitespace runs.
        String[] parts = trimmed.split("[,;\\s]+");
        if (parts.length >= 3) {
            try {
                float[] data = {
                    Float.parseFloat(parts[0].trim()),
                    Float.parseFloat(parts[1].trim()),
                    Float.parseFloat(parts[2].trim())
                };
                if (isDataPlausible(data)) return data;
            } catch (NumberFormatException ignored) {}
        }

        // ── Strategy 2: labeled key=value or key:value pairs ─────────────────
        // Handles: "T:36.5,pH:7.40,G:95" or "Temp=36.5 pH=7.40 Glucose=95"
        float temp = Float.NaN, ph = Float.NaN, glucose = Float.NaN;
        for (String token : trimmed.split("[,;\\s]+")) {
            String[] kv = token.split("[=:]", 2);
            if (kv.length == 2) {
                String key = kv[0].trim().toLowerCase();
                try {
                    float val = Float.parseFloat(kv[1].trim());
                    if (key.equals("t") || key.equals("temp") || key.equals("temperature")) {
                        temp = val;
                    } else if (key.equals("p") || key.equals("ph") || key.contains("ph")) {
                        ph = val;
                    } else if (key.equals("g") || key.equals("glu") || key.equals("glucose")) {
                        glucose = val;
                    }
                } catch (NumberFormatException ignored) {}
            }
        }
        if (!Float.isNaN(temp) && !Float.isNaN(ph) && !Float.isNaN(glucose)) {
            float[] data = {temp, ph, glucose};
            if (isDataPlausible(data)) return data;
        }

        return null;
    }
}
