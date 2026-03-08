"""
Sensor data model and management
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Union


@dataclass
class SensorReading:
    """Single sensor reading"""
    timestamp: datetime
    temperature: float  # in Celsius (0-60 °C)
    ph: float  # pH value (0-14)
    glucose: float  # in mg/dL (30-250)
    tag_id: str = ""  # NFC tag UID hex string (e.g. '04A1B2C3')

    def __str__(self):
        ts = self.timestamp
        if isinstance(ts, datetime):
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
        else:
            ts_str = str(ts)
        tag = f", Tag: {self.tag_id}" if self.tag_id else ""
        return (f"{ts_str} - Temp: {self.temperature}°C, "
                f"pH: {self.ph}, Glucose: {self.glucose} mg/dL{tag}")


def _parse_timestamp(value) -> datetime:
    """Convert various timestamp formats to datetime object."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            pass
        try:
            return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
    # Fallback to now
    return datetime.now()


class SensorData:
    """Manages in-memory sensor data with reactive observer support.

    Any object can register a callback via ``add_observer(fn)``.
    The callback ``fn(reading: SensorReading)`` is invoked synchronously
    on the Kivy main thread the instant a new reading is committed, so
    UI widgets are refreshed within the same scheduler tick — satisfying
    the "instant update within the 2-second window" requirement.
    """

    def __init__(self):
        self.readings: List[SensorReading] = []
        self.max_memory_readings = 10000
        self._observers: list = []  # list of callables: fn(SensorReading) -> None

    # ── Observer registration ────────────────────────────────────────────

    def add_observer(self, callback) -> None:
        """Register a callback to be invoked immediately when a new reading arrives.

        Parameters
        ----------
        callback : callable
            fn(reading: SensorReading) -> None.
            Always called on the Kivy main thread (Clock callbacks are
            main-thread), so it is safe to update UI widgets directly.
        """
        if callback not in self._observers:
            self._observers.append(callback)

    def remove_observer(self, callback) -> None:
        """Unregister a previously registered observer."""
        if callback in self._observers:
            self._observers.remove(callback)

    def add_reading(self, data: dict) -> None:
        """Add a new sensor reading and immediately notify all observers."""
        raw_ts = data.get('timestamp', datetime.now())
        reading = SensorReading(
            timestamp=_parse_timestamp(raw_ts),
            temperature=float(data.get('temperature', 0)),
            ph=float(data.get('ph', 7.0)),
            glucose=float(data.get('glucose', 0)),
            tag_id=str(data.get('tag_id', '')),
        )
        self.readings.append(reading)

        # Trim old readings if necessary
        if len(self.readings) > self.max_memory_readings:
            self.readings = self.readings[-self.max_memory_readings:]

        # ── Reactive push: notify all registered observers immediately ────
        for cb in list(self._observers):
            try:
                cb(reading)
            except Exception:
                pass
    
    def get_all_readings(self) -> List[SensorReading]:
        """Get all stored readings"""
        return self.readings.copy()
    
    def get_recent_readings(self, count: int) -> List[SensorReading]:
        """Get the last N readings"""
        return self.readings[-count:]
    
    def get_readings_since(self, timestamp: datetime) -> List[SensorReading]:
        """Get readings since a specific time"""
        return [r for r in self.readings if r.timestamp >= timestamp]
    
    def clear_readings(self) -> None:
        """Clear all readings from memory"""
        self.readings.clear()
    
    def get_statistics(self) -> dict:
        """Get statistics of current readings"""
        if not self.readings:
            return {}
        
        temps = [r.temperature for r in self.readings]
        ph_values = [r.ph for r in self.readings]
        glucose_values = [r.glucose for r in self.readings]
        
        return {
            'temperature': {
                'min': min(temps),
                'max': max(temps),
                'avg': sum(temps) / len(temps)
            },
            'ph': {
                'min': min(ph_values),
                'max': max(ph_values),
                'avg': sum(ph_values) / len(ph_values)
            },
            'glucose': {
                'min': min(glucose_values),
                'max': max(glucose_values),
                'avg': sum(glucose_values) / len(glucose_values)
            }
        }
