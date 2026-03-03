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
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class SensorBridge implements NfcAdapter.ReaderCallback {

    static {
        // Load native library
        System.loadLibrary("sensor_nhs3152");
    }

    private NfcAdapter nfcAdapter;
    private Context context;
    private Activity activity;
    private boolean connected = false;
    private boolean isReading = false;
    private Tag currentTag = null;
    private volatile float[] lastSensorData = null;

    private static final String TAG = "SensorBridge";

    // NFC Reader Mode flags:
    //   FLAG_READER_NFC_A  — NHS 3152 uses ISO14443-A
    //   FLAG_READER_NFC_B  — also listen for NFC-B tags
    //   Do NOT include FLAG_READER_SKIP_NDEF_CHECK so NDEF messages are read properly
    private static final int NFC_READER_MODE = NfcAdapter.FLAG_READER_NFC_A
                                             | NfcAdapter.FLAG_READER_NFC_B;

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

            // Mark native side as connected
            connected = nativeConnect("NFC Mode", 0);

            // Start NFC reader mode for continuous tag detection
            if (connected && activity != null) {
                enableReaderMode();
            }

            return connected;
        } catch (Exception e) {
            Log.e(TAG, "Error connecting to NFC: " + e.getMessage());
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
            disableReaderMode();
            nativeDisconnect();
            connected = false;
            lastSensorData = null;
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
        if (!connected) {
            return false;
        }
        return nativeCalibrate();
    }

    /**
     * Test NFC connection — checks if a valid tag was detected.
     */
    public boolean testConnection() {
        if (!connected) {
            return false;
        }
        return nativeTestConnection();
    }

    /**
     * Get NFC adapter status / firmware version.
     */
    public String getFirmwareVersion() {
        if (!connected) {
            return "NFC Not Connected";
        }
        return nativeFirmwareVersion();
    }

    /**
     * Parse health sensor data from raw NDEF/NFC payload bytes.
     * NHS 3152 payload format:
     *   Bytes 0-1: Temperature (signed int16, 0.1°C units)
     *   Bytes 2-3: pH (uint16, 0.01 pH units)
     *   Bytes 4-5: Glucose (uint16, mg/dL)
     */
    public float[] parseHealthData(byte[] data) {
        float[] sensorData = new float[3];  // temp, pH, glucose

        try {
            if (data == null || data.length < 6) {
                Log.w(TAG, "Insufficient data for parsing: " +
                      (data == null ? "null" : data.length + " bytes"));
                return null;
            }

            // Temperature (signed 16-bit, 0.1°C resolution)
            int tempRaw = ((data[0] & 0xFF) << 8) | (data[1] & 0xFF);
            if ((tempRaw & 0x8000) != 0) {
                tempRaw = tempRaw - 0x10000;
            }
            sensorData[0] = tempRaw / 10.0f;

            // pH (unsigned 16-bit, 0.01 pH resolution)
            int phRaw = ((data[2] & 0xFF) << 8) | (data[3] & 0xFF);
            sensorData[1] = phRaw / 100.0f;

            // Glucose (unsigned 16-bit, mg/dL)
            int glucoseRaw = ((data[4] & 0xFF) << 8) | (data[5] & 0xFF);
            sensorData[2] = (float) glucoseRaw;

            lastSensorData = sensorData;
            Log.i(TAG, String.format(
                "Parsed sensor data — Temp: %.1f°C, pH: %.2f, Glucose: %.0f mg/dL",
                sensorData[0], sensorData[1], sensorData[2]));

            return sensorData;
        } catch (Exception e) {
            Log.e(TAG, "Error parsing health data: " + e.getMessage());
        }

        return null;
    }

    /**
     * NFC Reader Callback — called automatically when an NFC tag is detected.
     * This is the core method for NHS 3152 sensor detection.
     */
    @Override
    public void onTagDiscovered(Tag tag) {
        currentTag = tag;
        String[] techList = tag.getTechList();
        Log.i(TAG, "NFC tag discovered! Tech: " + Arrays.toString(techList));

        // Store tag UID in native layer
        byte[] uid = tag.getId();
        if (uid != null) {
            nativeSetNFCData(uid);
            Log.i(TAG, "Tag UID: " + bytesToHex(uid));
        }

        // Strategy 1: Try NDEF first (most NHS 3152 configs use NDEF)
        if (tryReadNdef(tag)) {
            return;
        }

        // Strategy 2: Try IsoDep (ISO 14443-4) for NHS 3152 APDU communication
        if (tryReadIsoDep(tag)) {
            return;
        }

        // Strategy 3: Try raw NFC-A (ISO 14443-3A) memory read
        if (tryReadNfcA(tag)) {
            return;
        }

        Log.w(TAG, "Could not read sensor data from tag via any method");
    }

    /**
     * Try reading NDEF message from the tag.
     */
    private boolean tryReadNdef(Tag tag) {
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

                    // Check for custom Health record type ('H')
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

                    // Also try parsing any payload >= 6 bytes as sensor data
                    if (payload != null && payload.length >= 6) {
                        float[] data = parseHealthData(payload);
                        if (data != null && isDataPlausible(data)) {
                            Log.i(TAG, "Parsed sensor data from generic NDEF record");
                            ndef.close();
                            return true;
                        }
                    }
                }
            }
            ndef.close();
        } catch (Exception e) {
            Log.e(TAG, "Error reading NDEF: " + e.getMessage());
        }

        return false;
    }

    /**
     * Try reading via IsoDep (ISO 14443-4 / ISO-DEP) for NHS 3152.
     * NHS 3152 supports APDU commands for reading sensor memory.
     */
    private boolean tryReadIsoDep(Tag tag) {
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
        } catch (Exception e) {
            Log.e(TAG, "Error reading IsoDep: " + e.getMessage());
        }

        return false;
    }

    /**
     * Try reading via NFC-A (ISO 14443-3A) — direct memory read for NHS 3152.
     * NHS 3152 stores data in EEPROM accessible via NFC READ commands.
     */
    private boolean tryReadNfcA(Tag tag) {
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
        } catch (Exception e) {
            Log.e(TAG, "Error reading NFC-A: " + e.getMessage());
        }

        return false;
    }

    /**
     * Sanity-check parsed sensor data to avoid interpreting garbage bytes.
     */
    private boolean isDataPlausible(float[] data) {
        if (data == null || data.length < 3) return false;
        float temp = data[0];
        float ph = data[1];
        float glucose = data[2];
        // Accepted sensor ranges: temp 0-60 °C, pH 0-14, glucose 30-250 mg/dL
        return (temp >= 0.0f && temp <= 60.0f) &&
               (ph >= 0.0f && ph <= 14.0f) &&
               (glucose >= 30.0f && glucose <= 250.0f);
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
}
