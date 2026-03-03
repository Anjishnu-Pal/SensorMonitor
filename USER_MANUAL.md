
# SensorMonitor — User Manual

## Overview

SensorMonitor is a small Python/Kivy application for reading, visualizing, and saving sensor data. It includes a desktop Kivy UI and Android support (via Buildozer). The app collects sensor data from an NHS 3152 NFC sensor, displays it on a dashboard and graphs, and stores CSV logs.

### Supported Sensor Ranges
| Parameter   | Range         | Unit   |
|-------------|---------------|--------|
| Temperature | 0 – 60        | °C     |
| pH          | 0 – 14        | —      |
| Glucose     | 30 – 250      | mg/dL  |

Values outside these ranges are rejected as implausible by the sensor bridge.

## Requirements

- Python 3.8+ (recommended)
- See `requirements.txt` for Python dependencies.
- For Android builds: `buildozer` and an Android build environment.

## Quick start — Desktop

1. Create and activate a virtual environment (optional but recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python main.py
```

The Kivy app window should open. Use the on-screen controls to start/stop sensor readings and view graphs.

## SensorMonitor — Mobile User Manual

This document explains how to install and use the SensorMonitor app on an Android mobile device and how to operate it with an NHS 3152 NFC sensor tag.

## Scope

These instructions focus exclusively on mobile usage: installing the APK, granting permissions, using NFC to read sensors, viewing data in the UI, exporting CSVs, and mobile-specific troubleshooting.

## Install the App on Android

Option A — From an APK (sideload):

1. Copy the APK to your device or download it to the device directly.
2. On the device, enable installation from unknown sources for your package installer (Settings → Apps & notifications → Special app access → Install unknown apps).
3. Open the APK file and follow the installer prompts.

Option B — Via ADB (developer machine):

```bash
adb install -r path/to/your-app-debug.apk
```

Option C — Play Store / enterprise distribution: follow your distribution method (not covered here).

## Required Permissions

- NFC access (android.permission.NFC) — to read the NHS 3152 tag.
- Storage access (if exporting CSVs to external storage) — `WRITE_EXTERNAL_STORAGE` or scoped storage handling depending on Android version.
- Optional: Location permission may be requested on some Android versions when using NFC APIs; grant if prompted.

When first launched, approve any permission requests shown by the app.

## Enable NFC on the Device

1. Open device Settings → Connected devices or Connections.
2. Turn on NFC (toggle labeled NFC).
3. If available, enable Android Beam or reader/writer mode if the OS exposes it.

## Using the App (Mobile UI)

- Launch the app from your app launcher.
- Dashboard screen:
	- Shows the latest sensor readings (Temperature, pH, Glucose).
	- Use the Start/Stop button to begin or stop active reading sessions.
- NFC read flow:
	1. Tap `Start` (if required by the app) so that the app is listening for NFC tags.
	2. Hold the NHS 3152 tag close to the phone's NFC antenna (commonly near the top or center-back of the device). Start within 1–3 cm of the antenna and move slowly.
	3. The app should detect the tag and display the latest readings. Wait 1–3 seconds after detection for the values to update.
	   - Temperature: 0–60 °C
	   - pH: 0–14
	   - Glucose: 30–250 mg/dL
- Graphs screen:
	- Shows time-series plots of past readings collected during the current session or loaded from storage.
	- Fixed Y-axis scales: Temperature 0–60 °C, pH 0–14, Glucose 30–250 mg/dL.
	- Pinch to zoom and swipe to pan where supported.
- Settings screen:
	- Sampling rate: how often the app polls for readings.
	- Auto-save CSV: enable/disable automatic saving of data.
	- Data retention: configure how many days/sessions to keep.

## Exporting and Accessing Data

- Use the Export or Save button on the Data or Settings screen to write a CSV file of collected readings.
- Export location depends on the app configuration; check `data_management/csv_handler.py` for the configured path.
- To copy files to a computer via ADB:

```bash
adb pull /sdcard/Download/sensordata.csv ./
```

## NFC Best Practices and Tips

- Antenna location varies by phone model — test different spots on the phone's back.
- Keep the tag steady near the antenna until you see confirmation in the app.
- Remove metallic or thick cases that can block NFC; try removing the phone case if detection is unreliable.
- If the tag isn't detected, try re-enabling NFC and relaunching the app.

## Troubleshooting (Mobile-specific)

- NFC not detected:
	- Confirm NFC is enabled in system Settings.
	- Confirm app has NFC permission.
	- Move the tag slowly around the phone back to find the antenna hotspot.
	- Restart the phone and the app.
- No readings after detection:
	- Verify the NHS 3152 tag is powered and correctly configured.
	- Ensure the app supports your tag's data format; check `android_jni/SensorBridge.java` for supported message parsing.
- App cannot export CSV:
	- Ensure storage permission is granted, or check the app's configured export path.
	- For Android 11+ scoped storage, use the app's built-in share/export function if available.
- Background reading stops:
	- Some Android manufacturers restrict background services. Keep the app in foreground or disable battery optimizations for reliable continuous reads.

## Logs and Diagnostics

- For runtime logs, connect the device to a computer and run:

```bash
adb logcat | grep -i "sensor" -i
```

- Check the app log output for NFC and sensor-related errors and share traces when reporting issues.

## Where to Look in the Code (mobile-focused)

- `android_jni/SensorBridge.java` — Java bridge handling NFC/JNI interactions.
- `android_jni/sensor_interface.py` — Python interface exposed to the Kivy app.
- `kivy_app/ui/dashboard.py` — Dashboard screen UI and controls.
- `data_management/csv_handler.py` — CSV export and storage behavior.

## Quick Checklist Before Reporting an Issue

- Is NFC enabled on the phone?
- Did the app request and receive NFC and storage permissions?
- Is the NHS 3152 tag positioned correctly near the phone antenna?
- Can you reproduce the problem and capture a short log with `adb logcat`?

If those checks are done, open an issue and include: device model, Android version, app version (APK build), steps to reproduce, and a log snippet.

---

If you want, I can also shorten these mobile instructions into a one-page quick-start card for users to keep on their device. 

