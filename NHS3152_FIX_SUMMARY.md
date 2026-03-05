# NHS 3152 Sensor Recognition - Fix Summary

## Root Causes Identified

The app was failing to recognize the NHS 3152 sensor due to multiple interconnected issues:

1. **Activity Reference Issue**: `sensor_bridge.py` was using `org.kivy.android.PythonActivity` directly, which may not be available or correct in all Buildozer configurations
2. **Missing NFC Hardware Feature**: The buildozer.spec had the NFC hardware feature commented out
3. **No Lifecycle Management**: Reader mode was enabled but never properly managed through Android lifecycle events (onResume/onPause)
4. **Poor Error Handling**: No detailed logging to identify where the initialization was failing
5. **Early Activity Reference**: Attempting to access Activity before Kivy app was fully initialized

## Solutions Implemented

### 1. Fixed Activity Reference in `sensor_bridge.py`
**File**: `android_jni/sensor_bridge.py`

- Changed from single-source Activity lookup to multi-method fallback:
  - Method 1: Try `org.kivy.android.PythonActivity.mActivity`
  - Method 2: Try getting from Kivy app instance
  - Method 3: Try `android.app.PythonService`
- Added better error messages and debugging
- Gracefully handles case where Activity is not yet available

### 2. Enhanced SensorBridge.java Lifecycle Management
**File**: `android_jni/SensorBridge.java`

- Added `setActivity(Activity act)` method for late Activity binding
- Improved `connect()` method to handle null Activity gracefully
- Added status check methods: `isNfcAvailable()`, `isConnected()`, `isReaderModeActive()`
- Enhanced error logging in `onTagDiscovered()` with step-by-step feedback (→, ✓, ✗ symbols)
- Added detailed error messages for failed tag reads

### 3. Enabled NFC Hardware Feature
**File**: `buildozer.spec`

- Uncommented `android.features = android.hardware.nfc`
- This ensures Google Play knows the app requires NFC hardware
- Prevents installation on devices without NFC

### 4. Created NFCHandler Helper Class
**File**: `android_jni/nfc_handler.py` (NEW)

- Robust helper for managing NFC lifecycle
- Proper onResume/onPause integration
- Multi-source Activity retrieval
- Status reporting methods for debugging
- Centralized NFC initialization logic

### 5. Updated App Lifecycle in main.py
**File**: `main.py`

- Integrated NFCHandler into SensorMonitorApp
- Two-stage NFC initialization:
  - Early setup at 0.5s (if Activity available)
  - Main setup at 2s (guaranteed Activity available)
- Proper `on_pause()` and `on_resume()` handlers
- Better error handling and logging

### 6. Improved Sensor Interface Error Reporting
**File**: `android_jni/sensor_interface.py`

- Enhanced `connect()` with detailed NFC availability checks
- Added debug logging for reader mode status
- Better exception handling with stack traces

## How It Works Now

### Initialization Flow
1. App creates `SensorInterface` → creates `SensorBridge` (Python wrapper)
2. Early attempt in `build()` to get Activity if available
3. Main `_initial_connect()` at 2s tries to initialize NFC
4. `NFCHandler` coordinates with `SensorBridge` to set Activity 
5. Java `SensorBridge.connect()` enables reader mode once Activity is available
6. Continuous polling starts looking for NHS 3152 NFC tags

### Tag Detection Flow (when tag is within range)
1. Android NFC detects tag → `onTagDiscovered(Tag tag)` callback
2. Log shows "✓ NFC tag DISCOVERED!"
3. Try NDEF read (Strategy 1) - most common
4. If fails, try IsoDep APDU (Strategy 2)
5. If fails, try raw NFC-A memory (Strategy 3)
6. If any succeeds, parse sensor data [6 bytes]:
   - Bytes 0-1: Temperature (signed int16, 0.1°C units)
   - Bytes 2-3: pH (uint16, 0.01 pH units)
   - Bytes 4-5: Glucose (uint16, mg/dL)
7. Data is returned to Python and displayed in Dashboard

## Testing the Fixes

### What to Check
1. **Logcat Output**: Monitor with `adb logcat | grep -E "SensorBridge|NHS3152"`
2. **Permission Prompt**: App should request NFC permission on Android 6+
3. **Settings Check**: Ensure NFC is enabled in device settings
4. **Physical Test**: Place NHS 3152 tag near device

### Expected Log Output When Working
```
I SensorBridge: Activity set in Java SensorBridge
I SensorBridge: NFC reader mode enabled — scanning for NHS 3152 tags
I SensorBridge: ✓ NFC tag DISCOVERED! Technologies: [...]
I SensorBridge: Tag UID: [hex code]
I SensorBridge: → Trying NDEF read...
I SensorBridge: ✓ Successfully read NDEF data
I SensorBridge: Parsed sensor data — Temp: 37.5°C, pH: 7.20, Glucose: 95 mg/dL
```

## Compatibility
- **Android Versions**: API 21 to 33+ (buildozer.spec configured for API 33 with minapi 21)
- **NFC Requirement**: Mandatory (hardware feature declaration)
- **Architecture**: ARM64-v8a (for better performance and future-proofing)

## Files Modified
1. `android_jni/sensor_bridge.py` - Multi-source Activity lookup and improved error handling
2. `android_jni/SensorBridge.java` - Lifecycle management and detailed logging
3. `android_jni/sensor_interface.py` - Better error reporting
4. `buildozer.spec` - Enabled NFC hardware feature
5. `main.py` - Integrated NFCHandler and lifecycle management
6. `android_jni/nfc_handler.py` - NEW: Robust NFC lifecycle handler

## Next Steps
1. Rebuild APK with Buildozer: `buildozer android debug`
2. Test on actual Android device with NFC capability
3. Monitor logs while bringing NHS 3152 tag near phone
4. If still not detecting, check:
   - NFC is enabled in device settings
   - TAG is compatible with NHS 3152 format
   - Logcat shows what strategy failed and why
