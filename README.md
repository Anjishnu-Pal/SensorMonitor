# SensorMonitor - Health Sensor Mobile Application (NFC Version)

## Overview

A comprehensive Android mobile application for monitoring health sensors (Temperature, pH, and Glucose) using the NHS 3152 sensor chip with **NFC (Near Field Communication)** wireless data exchange. The app provides real-time data visualization, persistent CSV storage, and interactive graphs.

User manual: [USER_MANUAL.md](USER_MANUAL.md)
Quick start (mobile): [QUICK_START_CARD.md](QUICK_START_CARD.md)

## Key Features

- **👁️ Real-time Sensor Monitoring**: Temperature (0–60 °C), pH (0–14), and Glucose (30–250 mg/dL) readings via NFC
- **💾 Data Storage**: Automatic CSV file storage with daily rotation
- **📊 Data Visualization**: Interactive graphs and charts for all sensor parameters
- **📱 Dashboard**: Live display of current sensor readings with progress indicators
- **📤 Data Export**: Export all collected data to CSV format
- **🔧 NFC Calibration**: Built-in calibration utilities via NFC tag
- **⚙️ Configuration**: Customizable NFC settings and sensor parameters

## Architecture

```
Mobile-App/
├── main.py                      # Main Kivy application
├── kivy_app/
│   └── ui/
│       ├── main_screen.py       # Data table view
│       ├── dashboard.py         # Live sensor dashboard
│       ├── graphs.py            # Data visualization
│       └── settings.py          # Configuration screen
├── android_jni/
│   ├── sensor_interface.py      # Python JNI interface
│   └── SensorBridge.java        # Java JNI bridge
├── native_sensor/
│   └── sensor_nhs3152.c         # C/C++ native code for NHS 3152
├── data_management/
│   ├── sensor_data.py           # In-memory data model
│   └── csv_handler.py           # CSV storage management
├── tests/                       # Unit tests
├── docs/                        # Documentation
└── buildozer.spec              # Kivy/Android build configuration
```

## System Requirements

### Development Environment
- Python 3.8+
- Kivy 2.1+
- Android SDK (for building APK)
- Java Development Kit (JDK)
- Buildozer (for Kivy app compilation)

### Hardware Requirements
- **NHS 3152 Sensor Module** with NFC interface (ISO14443-A compatible)
- **Android device** with built-in NFC support (API level 21+)
- NFC antenna (built-in to modern Android devices)

## Installation & Setup

### 1. Install Dependencies
```bash
pip install kivy
pip install matplotlib
pip install garden
garden install matplotlib
```

### 2. Clone/Setup Project
```bash
git clone <repository>
cd Mobile-App
```

### 3. Configure Sensor Connection
Edit `kivy_app/ui/settings.py` to set your sensor's USB port:
- Default: `/dev/ttyUSB0`
- Baud rate: `115200`
- Update interval: `5 seconds`

### 4. Run Development Version
```bash
python main.py
```

## Building for Android

### Requirements
- Ubuntu/Linux environment
- Android SDK and NDK
- Buildozer

### Build Steps
```bash
# Install buildozer
pip install buildozer

# Configure buildozer
buildozer android debug

# Build APK
buildozer android debug
```

The compiled APK will be in `bin/` directory.

## Usage

### Dashboard Tab
- View live sensor readings
- Start/Stop monitoring
- Monitor in real-time

### Data Tab
- View historical sensor readings
- Browse last 20 readings
- Export data to CSV

### Graphs Tab
- Plot individual sensor parameters
- View trends over time
- Analyze all parameters simultaneously

### Settings Tab
- Configure sensor port and baud rate
- Set temperature offset
- Configure data storage path
- Calibrate sensors
- Test sensor connection

## Data Format

### CSV Format
```
timestamp,temperature,ph,glucose
2024-02-10T10:30:45.123456,40.0,7.2,140.0
2024-02-10T10:30:50.234567,41.3,6.8,135.5
```

### Sensor Data Protocol (NHS 3152)
- Temperature: 16-bit signed integer (0.1°C units) — range 0–60 °C
- pH: 16-bit unsigned integer (0.01 pH units) — range 0–14
- Glucose: 16-bit unsigned integer (mg/dL) — range 30–250 mg/dL

## NFC Communication

The app uses NFC to bridge Android with native C/C++ code via JNI for wireless sensor data exchange.

### NFC Protocol Details
```
Standard: ISO/IEC 14443-A
Frequency: 13.56 MHz
Range: 4-10 cm
Data Format: NDEF Messages
```

### Data Exchange Flow
```
NFC Tag (NHS 3152)
        ↓ (NDEF Message)
Android NFC Reader
        ↓
JNI Bridge (Java/C)
        ↓
SensorInterface (Python)
        ↓
[SensorData] ← → [CSVHandler]
        ↓
Kivy UI (Dashboard, Graphs, Tables)
```

## Troubleshooting

### NFC Hardware Not Detected
- Verify device has NFC support: Go to Settings → More → NFC
- Enable NFC if available
- Check device specifications for NFC capability

### NFC Tag Not Recognized
- Position NHS 3152 tag 4-10 cm from NFC antenna
- Move tag around antenna to find best position
- Ensure tag is not damaged or worn out
- Try different orientation (perpendicular to antenna)

### Data Not Reading
- Keep tag in NFC range (4-10 cm from antenna)
- Ensure Android NFC is enabled and app has NFC permission
- Check for NFC interference (remove metallic objects)
- Wait 2-3 seconds for tag detection

### NFC Connection Timeout
- Increase NFC timeout in Settings (default: 3000ms)
- Improve tag positioning near antenna
- Reduce other wireless interference (turn off Bluetooth)
- Try with fresh NFC tag if available

### Data Not Saving
- Verify storage path exists and is writable
- Check device has sufficient disk space
- Review file permissions on storage directory
- Ensure app has WRITE_EXTERNAL_STORAGE permission

## API Reference

### SensorInterface (NFC Version)
```python
interface = SensorInterface()
interface.connect()                    # Enable NFC reader mode
data = interface.read_sensor_data()   # Returns dict with temp, pH, glucose
interface.is_nfc_available()          # Check NFC hardware
interface.is_nfc_enabled()            # Check if NFC is active
interface.get_nfc_status()            # Get NFC reader status
interface.calibrate_sensors()         # Calibrate via NFC
interface.disconnect()
```

### SensorData
```python
sensor_data = SensorData()
sensor_data.add_reading(data_dict)
readings = sensor_data.get_all_readings()
stats = sensor_data.get_statistics()
```

### CSVHandler
```python
csv = CSVHandler('./data')
csv.save_sensor_reading({'temperature': 40.0, 'ph': 7.0, 'glucose': 140})
readings = csv.load_all_readings()
csv.export_all_data(readings, 'export.csv')
```

## License

[Add your license information here]

## Support

For issues and feature requests, please contact the development team.
it is a mobile app which read data from nfc sensor and show the data and plot it.
