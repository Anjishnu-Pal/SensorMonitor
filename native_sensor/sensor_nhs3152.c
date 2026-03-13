/*
 * sensor_nhs3152.c - Native C code for NHS 3152 sensor communication
 * This implements the JNI bridge for NFC communication.
 * NHS 3152 uses ISO14443-A NFC protocol for wireless data transmission.
 *
 * The actual NFC tag detection and NDEF parsing happens in Java (SensorBridge.java).
 * This native layer stores parsed sensor data and configuration, and provides
 * utility functions for data processing.
 */

#include <jni.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <android/log.h>

#define LOG_TAG "NHS3152_Native"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

/* ── Global state ────────────────────────────────────────────────────────── */

static int nfc_connected = 0;
static float temp_offset  = 0.0f;

/* NFC tag UID (up to 10 bytes for double-size UID) */
static unsigned char nfc_tag_uid[10];
static int nfc_tag_uid_len = 0;

/* Last parsed sensor data (set by Java after NFC read) */
static float last_temperature = 0.0f;
static float last_ph          = 0.0f;
static float last_glucose     = 0.0f;
static int   sensor_data_valid = 0;

/* ── Constants ───────────────────────────────────────────────────────────── */

#define NFC_FRAME_SIZE      256
#define NFC_TIMEOUT_MS     1000
#define NHS3152_POLL_TIMEOUT 3000  /* milliseconds */

/* ── Helper: parse 6-byte sensor payload ─────────────────────────────────── */

/**
 * Parse sensor data from a 6-byte payload.
 *   Bytes 0-1: Temperature (signed int16, 0.1 °C units)
 *   Bytes 2-3: pH          (uint16, 0.01 pH units)
 *   Bytes 4-5: Glucose     (uint16, mg/dL)
 *
 * Returns 1 on success, 0 on failure.
 */
static int parse_sensor_payload(const unsigned char *data, int data_len,
                                float *temp, float *ph, float *glucose) {
    if (data == NULL || data_len < 6) {
        return 0;
    }

    /* Temperature (signed 16-bit, 0.1 °C) */
    int16_t temp_raw = (int16_t)(((unsigned)data[0] << 8) | data[1]);
    *temp = (temp_raw / 10.0f) + temp_offset;

    /* pH (unsigned 16-bit, 0.01 pH) */
    unsigned int ph_raw = ((unsigned)data[2] << 8) | data[3];
    *ph = ph_raw / 100.0f;

    /* Glucose (unsigned 16-bit, mg/dL) */
    unsigned int glu_raw = ((unsigned)data[4] << 8) | data[5];
    *glucose = (float)glu_raw;

    return 1;
}

/* ── JNI: Connect ────────────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeConnect(
        JNIEnv *env, jobject obj, jstring device_name, jint unused) {

    nfc_connected = 1;
    sensor_data_valid = 0;
    memset(nfc_tag_uid, 0, sizeof(nfc_tag_uid));
    nfc_tag_uid_len = 0;

    LOGI("Native NFC layer connected");
    return JNI_TRUE;
}

/* ── JNI: Disconnect ─────────────────────────────────────────────────────── */

JNIEXPORT void JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeDisconnect(
        JNIEnv *env, jobject obj) {

    nfc_connected = 0;
    nfc_tag_uid_len = 0;
    sensor_data_valid = 0;
    LOGI("Native NFC layer disconnected");
}

/* ── JNI: Read Data ──────────────────────────────────────────────────────── */

/**
 * Return the last sensor reading as a 6-byte array (same format as the tag
 * payload). If no valid data is available, returns NULL.
 */
JNIEXPORT jbyteArray JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeReadData(
        JNIEnv *env, jobject obj) {

    if (!nfc_connected || !sensor_data_valid) {
        return NULL;
    }

    /* Re-encode the stored floats back into the 6-byte wire format */
    unsigned char buf[6];
    int16_t t = (int16_t)((last_temperature - temp_offset) * 10.0f);
    buf[0] = (unsigned char)((t >> 8) & 0xFF);
    buf[1] = (unsigned char)( t       & 0xFF);

    unsigned int p = (unsigned int)(last_ph * 100.0f);
    buf[2] = (unsigned char)((p >> 8) & 0xFF);
    buf[3] = (unsigned char)( p       & 0xFF);

    unsigned int g = (unsigned int)(last_glucose);
    buf[4] = (unsigned char)((g >> 8) & 0xFF);
    buf[5] = (unsigned char)( g       & 0xFF);

    jbyteArray result = (*env)->NewByteArray(env, 6);
    if (result != NULL) {
        (*env)->SetByteArrayRegion(env, result, 0, 6, (const jbyte *)buf);
    }
    return result;
}

/* ── JNI: Set NFC Data (called from Java after tag detection) ────────────── */

/**
 * Store NFC tag UID for identification.
 * Also accept sensor payload data if available (UID + payload concatenated).
 */
JNIEXPORT jboolean JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeSetNFCData(
        JNIEnv *env, jobject obj, jbyteArray nfc_data) {

    if (nfc_data == NULL) {
        return JNI_FALSE;
    }

    jint len = (*env)->GetArrayLength(env, nfc_data);
    jbyte *data = (*env)->GetByteArrayElements(env, nfc_data, NULL);
    if (data == NULL) {
        return JNI_FALSE;
    }

    /* Store UID (first 4-10 bytes) */
    int uid_len = (len < 10) ? len : 10;
    memcpy(nfc_tag_uid, data, uid_len);
    nfc_tag_uid_len = uid_len;

    LOGI("NFC tag UID stored (%d bytes)", uid_len);

    (*env)->ReleaseByteArrayElements(env, nfc_data, data, 0);
    return JNI_TRUE;
}

/* ── JNI: Store parsed sensor data (called from Java after successful parse) */

/**
 * Receive the three parsed sensor values from the Java layer.
 * This keeps the native bookkeeping layer in sync with Java-parsed data so
 * nativeReadData() can re-encode and return current values.
 */
JNIEXPORT void JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeStoreSensorData(
        JNIEnv *env, jobject obj, jfloat temp, jfloat ph, jfloat glucose) {

    last_temperature  = (float)temp - temp_offset;
    last_ph           = (float)ph;
    last_glucose      = (float)glucose;
    sensor_data_valid = 1;

    LOGI("Native layer updated — Temp: %.1f°C, pH: %.2f, Glucose: %.0f mg/dL",
         (float)temp, (float)ph, (float)glucose);
}

/* ── JNI: Update Configuration ───────────────────────────────────────────── */

JNIEXPORT void JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeUpdateConfig(
        JNIEnv *env, jobject obj, jfloat temp_off) {

    temp_offset = temp_off;
    LOGI("Temperature offset updated to %.2f", temp_offset);
}

/* ── JNI: Calibrate ──────────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeCalibrate(
        JNIEnv *env, jobject obj) {

    if (!nfc_connected) {
        return JNI_FALSE;
    }

    /* Calibration is mostly handled in Java (writing to the tag).
       Here we just acknowledge the request. */
    LOGI("Calibration requested");
    return JNI_TRUE;
}

/* ── JNI: Test Connection ────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeTestConnection(
        JNIEnv *env, jobject obj) {

    if (!nfc_connected) {
        return JNI_FALSE;
    }

    return (nfc_tag_uid_len > 0) ? JNI_TRUE : JNI_FALSE;
}

/* ── JNI: Firmware / Status Version ──────────────────────────────────────── */

JNIEXPORT jstring JNICALL
Java_com_sensormonitor_android_SensorBridge_nativeFirmwareVersion(
        JNIEnv *env, jobject obj) {

    if (!nfc_connected) {
        return (*env)->NewStringUTF(env, "NFC Not Connected");
    }

    if (nfc_tag_uid_len == 0) {
        return (*env)->NewStringUTF(env, "NFC Ready - No Tag Detected");
    }

    /* Return NFC tag UID as hex string */
    char version_str[64];
    int off = 0;
    off += snprintf(version_str + off, sizeof(version_str) - off, "NHS3152 Tag: ");
    for (int i = 0; i < nfc_tag_uid_len && off < (int)sizeof(version_str) - 3; i++) {
        off += snprintf(version_str + off, sizeof(version_str) - off, "%02X",
                        nfc_tag_uid[i]);
    }

    return (*env)->NewStringUTF(env, version_str);
}
