# Testing Instructions for NHS 3152 Sensor Fix

## Prerequisites
- Android device with NFC capability
- NHS 3152 sensor tag or compatible NFC tag with Sensor data
- Computer with Buildozer installed
- USB cable for adb debugging

## Step 1: Rebuild the APK
```bash
cd /workspaces/SensorMonitor
buildozer android debug
```

This will generate `bin/sensormonitor-1.02-debug.apk`

## Step 2: Install on Device
```bash
adb uninstall com.sensormonitor.sensormonitor
adb install -r bin/sensormonitor-1.02-debug.apk
```

## Step 3: Enable ADB Debugging
1. On Android device: Settings → About → Build number (tap 7 times)
2. Settings → Developer Options → USB Debugging (enable)
3. Plug in USB cable and approve ADB access prompt

## Step 4: Monitor Logcat
Open terminal and watch logs:
```bash
adb logcat | grep -E "SensorBridge|NHS3152|SensorMonitor"
```

## Step 5: Check Prerequisites
Open the SensorMonitor app and:
1. Go to Settings tab
2. You should see "✓ NFC ready - waiting for sensor" (if NFC is enabled)
3. If you see "NFC disabled in Settings", enable NFC on device

## Step 6: Test with NHS 3152 Tag
1. Keep app running in Dashboard tab
2. Bring NHS 3152 sensor tag near the NFC antenna (usually top of device)
3. Watch the Dashboard - should show sensor readings when detected
4. Check logcat for "✓ NFC tag DISCOVERED!" message

## Expected Log Output

### Good Case (Tag Detected):
```
I SensorBridge: Activity set in Java SensorBridge
I SensorBridge: NFC reader mode enabled — scanning for NHS 3152 tags
I SensorBridge: ✓ NFC tag DISCOVERED! Technologies: [android.nfc.tech.NfcA, android.nfc.tech.Ndef]
I SensorBridge: Tag UID: 04A1B2C3D4E5
I SensorBridge: → Trying NDEF read...
I SensorBridge: NDEF message has 1 record(s)
I SensorBridge: ✓ Successfully read NDEF data
I SensorBridge: Parsed sensor data — Temp: 37.5°C, pH: 7.20, Glucose: 95 mg/dL
```

### Fallback Strategies:
If NDEF fails, logs show:
```
I SensorBridge: → Trying IsoDep (APDU) read...
```
Then if that fails:
```
I SensorBridge: → Trying NFC-A (raw) read...
```

### Failed Case:
```
I SensorBridge: ✗ Could not read sensor data from tag via ANY method
I SensorBridge: This may indicate the tag is not an NHS 3152 or data is corrupted
```

## Troubleshooting

### Issue: "Activity reference is null"
**Solution**: This happens during early initialization. The app will retry and should succeed.
Check logs after 2-3 seconds.

### Issue: "NFC is disabled in device settings"
**Solution**: 
1. Go to device Settings
2. Search for "NFC" 
3. Enable NFC toggle
4. Restart the app

### Issue: "Device does not have NFC hardware"
**Solution**: Your device doesn't have NFC. Try with a different phone.

### Issue: Tag detected but no sensor data read
**Possible causes:**
1. Tag is not NHS 3152 format
2. Tag data is corrupted
3. Tag has different memory format than expected

**Next steps:**
- Check if tag works with other NFC apps
- Verify tag contains 6+ bytes of sensor data
- Use Android Studio to read raw tag memory
- Check if data matches expected format (see NHS3152_FIX_SUMMARY.md)

### Issue: Reader mode not enabled
**Log shows**: "Activity reference is null — reader mode could not be enabled"
**Solution**: Make sure `on_resume()` is being called properly. Try:
1. Stop the app
2. Press home button
3. Reopen the app
4. Check logs again - should show "*Reader mode enabled*"

## Debug Commands

Get all NFC-related logs:
```bash
adb logcat | grep -i nfc
```

Get only errors:
```bash
adb logcat | grep -E "ERROR|Error|error"
```

Get full logcat dump:
```bash
adb logcat > logcat_dump_$(date +%s).txt
```

Check NFC status on device:
```bash
adb shell dumpsys nfc | head -100
```

## Performance Notes
- NFC reader mode runs continuously when app is active
- Updates are polled every 2 seconds
- CPU impact is minimal (reader mode is hardware-accelerated)
- Battery impact is ~1-2% per hour of active scanning

## Next Testing Phase
Once basic detection works:
1. Test multiple tag reads
2. Test CSV data logging
3. Test graphs and dashboard updates
4. Test calibration feature
5. Test app backgrounding/resuming with active tag

## Reporting Issues
If the fix doesn't work, collect:
```bash
adb logcat > full_logs.txt
# Then reproduce the issue for ~30 seconds
# Stop with Ctrl+C
```
Include the full_logs.txt when reporting the issue.
