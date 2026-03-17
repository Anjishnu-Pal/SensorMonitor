"""
CSV data handler for persistent storage
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List
from data_management.sensor_data import SensorReading

# CSV + JSON fieldnames
_FIELDS = ['timestamp', 'temperature', 'ph', 'glucose', 'tag_id']


def _safe_float(val, default=0.0):
    """Return float(val) or default when val is empty/None/unconvertible."""
    try:
        return float(val) if val != "" else default
    except (ValueError, TypeError):
        return default


def _resolve_android_storage() -> str:
    """Return app-private external storage path on Android.

    Uses ``context.getExternalFilesDir(null)`` — the app's own
    external-storage sandbox (e.g. /sdcard/Android/data/<pkg>/files/).
    No WRITE_EXTERNAL_STORAGE permission is required on API 29+ (scoped
    storage).  Returns '' on non-Android platforms or if resolution fails.
    """
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        ctx = PythonActivity.mActivity.getApplicationContext()
        ext_dir = ctx.getExternalFilesDir(None)
        if ext_dir is not None:
            return str(ext_dir.getAbsolutePath())
    except Exception:
        pass
    return ''


class CSVHandler:
    """Handles reading and writing sensor data to CSV files.

    On Android the data is stored in the app-private external directory
    (``getExternalFilesDir(null)``) so it is accessible via USB/file-
    manager without requiring the deprecated WRITE_EXTERNAL_STORAGE
    permission (API 29+).
    On desktop it falls back to a local ``./sensor_data/`` folder.
    """

    def __init__(self, storage_path: str = ''):
        """Initialize CSV handler.

        Parameters
        ----------
        storage_path :
            Override the storage directory.  Leave empty (default) to use
            the Android external-files dir on Android, or ``./sensor_data``
            on desktop.
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            android_path = _resolve_android_storage()
            self.storage_path = (
                Path(android_path) if android_path else Path('./sensor_data')
            )
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Create daily CSV file names
        self.current_date = datetime.now().date()
        self.csv_file = self.storage_path / f"sensor_data_{self.current_date}.csv"
        
        # Initialize CSV file if it doesn't exist
        self._initialize_csv_file()
    
    def _initialize_csv_file(self):
        """Create CSV file with headers if it doesn't exist"""
        if not self.csv_file.exists():
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=_FIELDS)
                writer.writeheader()
    
    def save_sensor_reading(self, data: dict) -> bool:
        """Save a single sensor reading to CSV"""
        try:
            # Check if we need to create a new daily file
            today = datetime.now().date()
            if today != self.current_date:
                self.current_date = today
                self.csv_file = self.storage_path / f"sensor_data_{self.current_date}.csv"
                self._initialize_csv_file()

            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=_FIELDS)
                writer.writerow({
                    'timestamp': data.get('timestamp', datetime.now().isoformat()),
                    'temperature': data.get('temperature', 0),
                    'ph': data.get('ph', 7.0),
                    'glucose': data.get('glucose', 0),
                    'tag_id': data.get('tag_id', ''),
                })
            return True
        except Exception as e:
            print(f"Error saving sensor reading: {e}")
            return False

    def save_tap_event(self, data: dict) -> bool:
        """Persist a single NFC-tap event to a JSON history file.

        Each tap appends one entry to ``tap_history.json`` in the storage
        directory.  This acts as a lightweight alternative to SharedPreferences
        for storing structured tap records with timestamps.
        """
        tap_file = self.storage_path / 'tap_history.json'
        try:
            history: list = []
            if tap_file.exists():
                with open(tap_file, 'r') as f:
                    history = json.load(f)
            history.append({
                'timestamp': data.get('timestamp', datetime.now().isoformat()),
                'temperature': round(float(data.get('temperature', 0)), 2),
                'ph': round(float(data.get('ph', 7.0)), 3),
                'glucose': round(float(data.get('glucose', 0)), 1),
                'tag_id': str(data.get('tag_id', '')),
            })
            with open(tap_file, 'w') as f:
                json.dump(history, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving tap event to JSON: {e}")
            return False

    def load_tap_history(self) -> List[dict]:
        """Load all tap events from the JSON history file."""
        tap_file = self.storage_path / 'tap_history.json'
        try:
            if tap_file.exists():
                with open(tap_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading tap history: {e}")
        return []
    
    def load_sensor_readings(self, date=None) -> List[dict]:
        """Load sensor readings from CSV"""
        try:
            if date is None:
                date = datetime.now().date()
            
            csv_file = self.storage_path / f"sensor_data_{date}.csv"
            
            if not csv_file.exists():
                return []
            
            readings = []
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    readings.append({
                        'timestamp': datetime.fromisoformat(row['timestamp']),
                        'temperature': _safe_float(row.get('temperature'), 0.0),
                        'ph': _safe_float(row.get('ph'), 7.0),
                        'glucose': _safe_float(row.get('glucose'), 0.0),
                        'tag_id': row.get('tag_id', ''),
                    })
            return readings
        except Exception as e:
            print(f"Error loading sensor readings: {e}")
            return []
    
    def load_all_readings(self) -> List[dict]:
        """Load all sensor readings from all CSV files"""
        all_readings = []
        try:
            for csv_file in sorted(self.storage_path.glob('sensor_data_*.csv')):
                with open(csv_file, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        all_readings.append({
                            'timestamp': datetime.fromisoformat(row['timestamp']),
                            'temperature': _safe_float(row.get('temperature'), 0.0),
                            'ph': _safe_float(row.get('ph'), 7.0),
                            'glucose': _safe_float(row.get('glucose'), 0.0),
                            'tag_id': row.get('tag_id', ''),
                        })
        except Exception as e:
            print(f"Error loading all readings: {e}")
        
        return all_readings
    
    def export_all_data(self, readings: List[SensorReading], filename: str = None) -> str:
        """Export all readings to a named CSV file"""
        try:
            if filename is None:
                filename = f"sensor_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            export_path = self.storage_path / filename
            
            with open(export_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=_FIELDS)
                writer.writeheader()

                for reading in readings:
                    writer.writerow({
                        'timestamp': reading.timestamp.isoformat(),
                        'temperature': reading.temperature,
                        'ph': reading.ph,
                        'glucose': reading.glucose,
                        'tag_id': reading.tag_id,
                    })
            
            return str(export_path)
        except Exception as e:
            print(f"Error exporting data: {e}")
            return ""
    
    def get_storage_path(self) -> str:
        """Get the storage directory path"""
        return str(self.storage_path)
    
    def get_available_dates(self) -> List[str]:
        """Get list of dates with available data"""
        dates = []
        try:
            for csv_file in sorted(self.storage_path.glob('sensor_data_*.csv')):
                # Extract date from filename
                date_str = csv_file.stem.replace('sensor_data_', '')
                dates.append(date_str)
        except Exception as e:
            print(f"Error getting available dates: {e}")
        
        return dates
