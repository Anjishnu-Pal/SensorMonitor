# SensorMonitor — Quick Start (Mobile)

Install
- Sideload APK: open the APK on your device and install, or run:

```bash
adb install -r path/to/app-debug.apk
```

Permissions
- Grant NFC and storage access when the app asks.

Enable NFC
- Settings → Connected devices → NFC → ON

Read a Sensor Tag
1. Open the app.
2. Tap `Start` (if present) to begin listening for tags.
3. Hold the NHS 3152 tag close to the phone's NFC antenna (back/top of phone).
4. Wait 1–3 seconds for the app to show:
   - **Temperature**: 0–60 °C
   - **pH**: 0–14
   - **Glucose**: 30–250 mg/dL

Export Data
- Use the Export/Save button on the Data or Settings screen to write a CSV.
- Pull the CSV to your computer:

```bash
adb pull /sdcard/Download/sensordata.csv ./
```

Quick Troubleshooting
- NFC not working: ensure NFC is enabled and the tag is near the antenna.
- No readings: try another tag or check tag power/configuration.
- Values out of range: Temperature must be 0–60 °C, pH 0–14, Glucose 30–250 mg/dL.
- Background reading stops: disable battery optimizations for the app.

Need more help? See the full mobile manual: [USER_MANUAL.md](USER_MANUAL.md)
