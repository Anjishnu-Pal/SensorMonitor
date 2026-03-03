"""
Configuration module for SensorMonitor app
Manages app settings and configuration
"""

import json
import os
from pathlib import Path
from typing import Dict, Any


class AppConfig:
    """Application configuration management"""
    
    DEFAULT_CONFIG = {
        'app_name': 'SensorMonitor',
        'version': '1.0.0',
        'sensor': {
            'communication_mode': 'NFC',
            'nfc_reader_presence_check': 250,  # milliseconds
            'nfc_timeout': 3000,  # milliseconds
            'auto_detect': True,
            'update_interval': 5,  # seconds between polls
        },
        'data_storage': {
            'path': './sensor_data',
            'format': 'csv',
            'rotation': 'daily',
        },
        'calibration': {
            'temperature_offset': 0.0,
            'ph_calibration': 7.0,
            'glucose_calibration': 100.0,
        },
        'ui': {
            'theme': 'light',
            'graph_update_interval': 10,
            'chart_type': 'line',
        },
        'logging': {
            'level': 'INFO',
            'file': 'sensormonitor.log',
            'max_size': 10485760,  # 10MB
        }
    }
    
    def __init__(self, config_file: str = './config.json'):
        """Initialize configuration"""
        self.config_file = Path(config_file)
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
    
    def load_config(self) -> bool:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    self._deep_update(self.config, loaded)
                return True
            except Exception as e:
                print(f"Error loading config: {e}")
                return False
        return False
    
    def save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _deep_update(self, base: Dict, update: Dict) -> None:
        """Recursively update nested dictionaries"""
        for key, value in update.items():
            if isinstance(value, dict) and key in base:
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports nested keys with dot notation)"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> bool:
        """Set configuration value by key (supports nested keys with dot notation)"""
        keys = key.split('.')
        config = self.config
        
        try:
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            
            config[keys[-1]] = value
            return True
        except (TypeError, IndexError):
            return False
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self.config = self.DEFAULT_CONFIG.copy()
    
    def __repr__(self) -> str:
        """String representation"""
        return f"AppConfig(file={self.config_file})"


# Global configuration instance
_config = None


def get_config() -> AppConfig:
    """Get or create global configuration instance"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
