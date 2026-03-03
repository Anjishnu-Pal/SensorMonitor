"""
Unit tests for SensorData module
"""

import unittest
from datetime import datetime
from data_management.sensor_data import SensorData, SensorReading, _parse_timestamp


class TestParseTimestamp(unittest.TestCase):
    """Test timestamp parsing utility."""

    def test_datetime_passthrough(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        self.assertEqual(_parse_timestamp(dt), dt)

    def test_isoformat_string(self):
        iso = '2025-06-15T14:30:00'
        result = _parse_timestamp(iso)
        self.assertEqual(result, datetime(2025, 6, 15, 14, 30, 0))

    def test_isoformat_with_microseconds(self):
        iso = '2025-06-15T14:30:00.123456'
        result = _parse_timestamp(iso)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2025)

    def test_invalid_string_falls_back_to_now(self):
        result = _parse_timestamp('not-a-date')
        self.assertIsInstance(result, datetime)

    def test_none_falls_back_to_now(self):
        result = _parse_timestamp(None)
        self.assertIsInstance(result, datetime)


class TestSensorData(unittest.TestCase):
    """Test SensorData class"""
    
    def setUp(self):
        self.sensor_data = SensorData()
    
    def test_add_reading_with_datetime(self):
        """Test adding a sensor reading with datetime object"""
        data = {
            'timestamp': datetime.now(),
            'temperature': 36.5,
            'ph': 7.0,
            'glucose': 100
        }
        self.sensor_data.add_reading(data)
        self.assertEqual(len(self.sensor_data.get_all_readings()), 1)

    def test_add_reading_with_iso_string(self):
        """Test adding a sensor reading with ISO timestamp string"""
        data = {
            'timestamp': '2025-06-15T14:30:00',
            'temperature': 37.0,
            'ph': 7.2,
            'glucose': 110
        }
        self.sensor_data.add_reading(data)
        readings = self.sensor_data.get_all_readings()
        self.assertEqual(len(readings), 1)
        self.assertIsInstance(readings[0].timestamp, datetime)
        self.assertEqual(readings[0].timestamp.year, 2025)

    def test_add_reading_without_timestamp(self):
        """Test adding a reading with no timestamp (should default to now)"""
        data = {'temperature': 36.5, 'ph': 7.0, 'glucose': 100}
        self.sensor_data.add_reading(data)
        readings = self.sensor_data.get_all_readings()
        self.assertEqual(len(readings), 1)
        self.assertIsInstance(readings[0].timestamp, datetime)
    
    def test_get_recent_readings(self):
        """Test getting recent readings"""
        for i in range(10):
            self.sensor_data.add_reading({
                'temperature': 36.0 + i,
                'ph': 7.0,
                'glucose': 100
            })
        
        recent = self.sensor_data.get_recent_readings(5)
        self.assertEqual(len(recent), 5)
    
    def test_statistics(self):
        """Test statistics calculation"""
        for i in range(5):
            self.sensor_data.add_reading({
                'temperature': 36.0 + i,
                'ph': 7.0,
                'glucose': 100
            })
        
        stats = self.sensor_data.get_statistics()
        self.assertIn('temperature', stats)
        self.assertEqual(stats['temperature']['min'], 36.0)
        self.assertEqual(stats['temperature']['max'], 40.0)
    
    def test_clear_readings(self):
        """Test clearing readings"""
        self.sensor_data.add_reading({'temperature': 36.5, 'ph': 7.0, 'glucose': 100})
        self.assertEqual(len(self.sensor_data.get_all_readings()), 1)
        
        self.sensor_data.clear_readings()
        self.assertEqual(len(self.sensor_data.get_all_readings()), 0)

    def test_reading_str(self):
        """Test SensorReading string representation"""
        reading = SensorReading(
            timestamp=datetime(2025, 6, 15, 14, 30, 0),
            temperature=36.5,
            ph=7.0,
            glucose=100.0
        )
        s = str(reading)
        self.assertIn('36.5', s)
        self.assertIn('7.0', s)
        self.assertIn('100.0', s)

    def test_memory_limit(self):
        """Test that readings are trimmed after hitting max"""
        self.sensor_data.max_memory_readings = 5
        for i in range(10):
            self.sensor_data.add_reading({
                'temperature': 36.0 + i,
                'ph': 7.0,
                'glucose': 100
            })
        self.assertEqual(len(self.sensor_data.get_all_readings()), 5)


if __name__ == '__main__':
    unittest.main()
