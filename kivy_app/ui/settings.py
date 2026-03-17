"""
Settings screen for app configuration with NFC support and troubleshooting.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock


class SettingsScreen(BoxLayout):
    """Settings screen with NFC configuration and troubleshooting controls."""

    def __init__(self, sensor_interface, permission_manager=None,
                 csv_handler=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        self.sensor_interface = sensor_interface
        self.permission_manager = permission_manager
        self.csv_handler = csv_handler

        # ── Title ─────────────────────────────────────────────────────────
        title = Label(
            text='Settings & Troubleshooting',
            size_hint_y=None, height=40, bold=True, font_size='18sp')
        self.add_widget(title)

        # ── Status bar (visible feedback) ─────────────────────────────────
        self.status_label = Label(
            text='Status: Ready',
            size_hint_y=None, height=35,
            color=(0.5, 1, 0.5, 1), font_size='14sp')
        self.add_widget(self.status_label)

        # ── Scrollable settings area ──────────────────────────────────────
        scroll = ScrollView(size_hint_y=1)
        inner = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8, padding=5)
        inner.bind(minimum_height=inner.setter('height'))

        # -- NFC Configuration Section --
        inner.add_widget(Label(
            text='── NFC Configuration ──',
            size_hint_y=None, height=30, bold=True, color=(0.8, 0.8, 1, 1)))

        settings_grid = GridLayout(cols=2, spacing=8, size_hint_y=None, row_default_height=40)
        settings_grid.bind(minimum_height=settings_grid.setter('height'))

        # NFC Mode
        settings_grid.add_widget(Label(text='NFC Mode:', size_hint_y=None, height=40))
        nfc_layout = BoxLayout(size_hint_y=None, height=40)
        self.nfc_enabled = CheckBox(active=True)
        nfc_layout.add_widget(self.nfc_enabled)
        nfc_layout.add_widget(Label(text='Enabled'))
        settings_grid.add_widget(nfc_layout)

        # Reader Presence Check Delay
        settings_grid.add_widget(Label(text='Reader Check (ms):', size_hint_y=None, height=40))
        self.reader_delay_input = TextInput(
            text='250', multiline=False, input_filter='int',
            size_hint_y=None, height=40)
        settings_grid.add_widget(self.reader_delay_input)

        # NFC Timeout
        settings_grid.add_widget(Label(text='NFC Timeout (ms):', size_hint_y=None, height=40))
        self.nfc_timeout_input = TextInput(
            text='3000', multiline=False, input_filter='int',
            size_hint_y=None, height=40)
        settings_grid.add_widget(self.nfc_timeout_input)

        # Auto-detect
        settings_grid.add_widget(Label(text='Auto-detect Tags:', size_hint_y=None, height=40))
        auto_layout = BoxLayout(size_hint_y=None, height=40)
        self.auto_detect = CheckBox(active=True)
        auto_layout.add_widget(self.auto_detect)
        auto_layout.add_widget(Label(text='Enabled'))
        settings_grid.add_widget(auto_layout)

        inner.add_widget(settings_grid)

        # -- Calibration Section --
        inner.add_widget(Label(
            text='── Calibration ──',
            size_hint_y=None, height=30, bold=True, color=(0.8, 0.8, 1, 1)))

        cal_grid = GridLayout(cols=2, spacing=8, size_hint_y=None, row_default_height=40)
        cal_grid.bind(minimum_height=cal_grid.setter('height'))

        cal_grid.add_widget(Label(text='Temp Offset (°C):', size_hint_y=None, height=40))
        self.temp_offset_input = TextInput(
            text='0.0', multiline=False, size_hint_y=None, height=40)
        cal_grid.add_widget(self.temp_offset_input)

        cal_grid.add_widget(Label(text='pH Calibration:', size_hint_y=None, height=40))
        self.ph_calibration_input = TextInput(
            text='7.0', multiline=False, size_hint_y=None, height=40)
        cal_grid.add_widget(self.ph_calibration_input)

        cal_grid.add_widget(Label(text='Temp Unit:', size_hint_y=None, height=40))
        self.temp_spinner = Spinner(
            text='Celsius', values=('Celsius', 'Fahrenheit'),
            size_hint_y=None, height=40)
        cal_grid.add_widget(self.temp_spinner)

        cal_grid.add_widget(Label(text='Storage Path:', size_hint_y=None, height=40))
        self.path_input = TextInput(
            text='', multiline=False,
            size_hint_y=None, height=40)
        cal_grid.add_widget(self.path_input)

        inner.add_widget(cal_grid)

        # -- Troubleshooting Section --
        inner.add_widget(Label(
            text='── Troubleshooting ──',
            size_hint_y=None, height=30, bold=True, color=(1, 0.8, 0.5, 1)))

        inner.add_widget(Label(
            text='If the sensor is not detected, try these steps:',
            size_hint_y=None, height=25, font_size='13sp',
            color=(0.9, 0.9, 0.9, 1)))

        troubleshoot_text = (
            '1. Ensure NFC is enabled in phone Settings\n'
            '2. Remove phone case (may block NFC)\n'
            '3. Hold NHS 3152 tag flat against phone back\n'
            '4. Tap "Reconnect NFC" below\n'
            '5. Tap "Test NFC" to verify connection\n'
            '6. If still failing, tap "Reset All" and retry')
        inner.add_widget(Label(
            text=troubleshoot_text,
            size_hint_y=None, height=120, font_size='12sp',
            color=(0.8, 0.8, 0.8, 1), halign='left', valign='top',
            text_size=(None, None)))

        # -- Permissions Section --
        inner.add_widget(Label(
            text='── App Permissions ──',
            size_hint_y=None, height=30, bold=True, color=(1, 0.85, 0.4, 1)))

        self._perm_status_grid = GridLayout(
            cols=2, spacing=6, size_hint_y=None, row_default_height=36)
        self._perm_status_grid.bind(
            minimum_height=self._perm_status_grid.setter('height'))
        inner.add_widget(self._perm_status_grid)

        # Populated in _refresh_permission_rows() called below
        self._perm_rows = {}

        request_perm_btn = Button(
            text='Request / Refresh Permissions',
            size_hint_y=None, height=44,
            background_color=(0.2, 0.5, 0.85, 1),
            font_size='13sp')
        request_perm_btn.bind(on_press=self._on_request_permissions)
        inner.add_widget(request_perm_btn)

        scroll.add_widget(inner)
        self.add_widget(scroll)

        # ── Action Buttons (2 rows) ──────────────────────────────────────
        btn_row1 = BoxLayout(size_hint_y=None, height=50, spacing=5)

        save_btn = Button(text='Save Settings', background_color=(0.2, 0.6, 0.2, 1))
        save_btn.bind(on_press=self.save_settings)
        btn_row1.add_widget(save_btn)

        calibrate_btn = Button(text='Calibrate NFC', background_color=(0.2, 0.4, 0.8, 1))
        calibrate_btn.bind(on_press=self.calibrate_sensors)
        btn_row1.add_widget(calibrate_btn)

        self.add_widget(btn_row1)

        btn_row2 = BoxLayout(size_hint_y=None, height=50, spacing=5)

        reconnect_btn = Button(text='Reconnect NFC', background_color=(0.8, 0.5, 0.1, 1))
        reconnect_btn.bind(on_press=self.reconnect_nfc)
        btn_row2.add_widget(reconnect_btn)

        test_btn = Button(text='Test NFC', background_color=(0.5, 0.5, 0.8, 1))
        test_btn.bind(on_press=self.test_connection)
        btn_row2.add_widget(test_btn)

        reset_btn = Button(text='Reset All', background_color=(0.8, 0.2, 0.2, 1))
        reset_btn.bind(on_press=self.reset_all)
        btn_row2.add_widget(reset_btn)

        self.add_widget(btn_row2)

        # Populate storage path from the actual csv_handler path (scoped storage)
        if self.csv_handler:
            self.path_input.text = self.csv_handler.get_storage_path()

    # ── Status helpers ────────────────────────────────────────────────────
    def _set_status(self, text, colour=(0.5, 1, 0.5, 1)):
        self.status_label.text = text
        self.status_label.color = colour

    def _set_status_ok(self, text):
        self._set_status(f'OK: {text}', (0.3, 1, 0.3, 1))

    def _set_status_err(self, text):
        self._set_status(f'ERR: {text}', (1, 0.3, 0.3, 1))

    def _set_status_warn(self, text):
        self._set_status(f'WARN: {text}', (1, 0.8, 0.2, 1))

    # ── Actions ───────────────────────────────────────────────────────────
    def save_settings(self, instance):
        """Save settings to sensor interface config."""
        try:
            settings = {
                'nfc_mode': self.nfc_enabled.active,
                'nfc_reader_presence_check': int(self.reader_delay_input.text or '250'),
                'nfc_timeout': int(self.nfc_timeout_input.text or '3000'),
                'auto_detect': self.auto_detect.active,
                'temp_unit': self.temp_spinner.text,
                'storage_path': self.path_input.text,
                'temp_offset': float(self.temp_offset_input.text or '0.0'),
                'ph_calibration': float(self.ph_calibration_input.text or '7.0'),
            }
            self.sensor_interface.update_configuration(settings)
            # Apply storage path to CSVHandler so new readings go to the
            # chosen directory, not just to sensor_interface.config.
            if self.csv_handler and self.path_input.text.strip():
                from pathlib import Path
                new_path = Path(self.path_input.text.strip())
                try:
                    new_path.mkdir(parents=True, exist_ok=True)
                    self.csv_handler.storage_path = new_path
                    self.csv_handler.csv_file = new_path / f"sensor_data_{self.csv_handler.current_date}.csv"
                    self.csv_handler._initialize_csv_file()
                except Exception as path_err:
                    self._set_status_warn(f'Path not updated: {path_err}')
                    return
            self._set_status_ok('Settings saved successfully')
        except ValueError as e:
            self._set_status_err(f'Invalid input: {e}')
        except Exception as e:
            self._set_status_err(f'Save failed: {e}')

    def calibrate_sensors(self, instance):
        """Calibrate sensors via NFC tag."""
        self._set_status('Calibrating... hold tag near device', (1, 1, 0.5, 1))
        try:
            result = self.sensor_interface.calibrate_sensors()
            if result:
                self._set_status_ok('Calibration completed')
            else:
                self._set_status_err('Calibration failed — is tag in range?')
        except Exception as e:
            self._set_status_err(f'Calibration error: {e}')

    def reconnect_nfc(self, instance):
        """Disconnect and reconnect NFC."""
        self._set_status('Reconnecting NFC...', (1, 1, 0.5, 1))
        try:
            self.sensor_interface.disconnect()
            result = self.sensor_interface.connect()
            if result:
                self._set_status_ok('NFC reconnected successfully')
            else:
                self._set_status_warn('NFC not connected — no tag found yet (will keep scanning)')
        except Exception as e:
            self._set_status_err(f'Reconnect failed: {e}')

    def test_connection(self, instance):
        """Test NFC connection and show full status."""
        self._set_status('Testing NFC...', (1, 1, 0.5, 1))
        try:
            status = self.sensor_interface.get_status()
            nfc_status = status.get('nfc_status', 'Unknown')
            connected = status.get('connected', False)
            mode = status.get('platform', 'Unknown')

            if connected:
                self._set_status_ok(f'Connected | {nfc_status} | {mode}')
            else:
                # Try to connect
                if self.sensor_interface.connect():
                    self._set_status_ok(f'Connected after retry | {mode}')
                else:
                    self._set_status_warn(f'Not connected | {nfc_status} | {mode}')
        except Exception as e:
            self._set_status_err(f'Test failed: {e}')

    def reset_all(self, instance):
        """Reset all settings to defaults and reconnect."""
        try:
            self.sensor_interface.disconnect()

            # Reset UI fields
            self.nfc_enabled.active = True
            self.reader_delay_input.text = '250'
            self.nfc_timeout_input.text = '3000'
            self.auto_detect.active = True
            self.temp_offset_input.text = '0.0'
            self.ph_calibration_input.text = '7.0'
            self.temp_spinner.text = 'Celsius'
            self.path_input.text = (
                self.csv_handler.get_storage_path() if self.csv_handler else '')

            # Reset config
            self.sensor_interface.config = {
                'nfc_mode': True,
                'nfc_reader_presence_check': 250,
                'nfc_timeout': 3000,
                'temp_offset': 0.0,
                'ph_calibration': 7.0,
                'glucose_calibration': 100.0,
                'auto_detect': True,
            }

            # Push defaults to Java/native layer so calibration offsets are cleared
            self.sensor_interface.update_configuration(self.sensor_interface.config)

            self._set_status_ok('All settings reset to defaults')
        except Exception as e:
            self._set_status_err(f'Reset failed: {e}')

    # ── Permission helpers ────────────────────────────────────────────────

    def _refresh_permission_rows(self) -> None:
        """Populate / update the permissions status grid."""
        if self.permission_manager is None:
            return

        self._perm_status_grid.clear_widgets()
        self._perm_rows.clear()

        summary = self.permission_manager.get_status_summary()
        for label_text, status in summary.items():
            lbl = Label(
                text=label_text, font_size='12sp',
                size_hint_y=None, height=36,
                halign='left', valign='middle')
            lbl.bind(size=lbl.setter('text_size'))
            self._perm_status_grid.add_widget(lbl)

            if status == 'Granted':
                colour = (0.3, 1.0, 0.3, 1)
            elif status == 'Denied':
                colour = (1.0, 0.35, 0.35, 1)
            else:
                colour = (0.6, 0.6, 0.6, 1)

            status_lbl = Label(
                text=status, font_size='12sp',
                size_hint_y=None, height=36,
                color=colour, halign='center', valign='middle')
            status_lbl.bind(size=status_lbl.setter('text_size'))
            self._perm_status_grid.add_widget(status_lbl)
            self._perm_rows[label_text] = status_lbl

    def on_parent(self, widget, parent) -> None:
        """Refresh permission rows whenever this tab is added to a parent."""
        super().on_parent(widget, parent) if hasattr(super(), 'on_parent') else None
        Clock.schedule_once(lambda _dt: self._refresh_permission_rows(), 0.1)

    def _on_request_permissions(self, _instance) -> None:
        """Re-request all permissions from within Settings."""
        if self.permission_manager is None:
            self._set_status_warn('Permission manager not available')
            return

        self._set_status('Requesting permissions…', (1, 0.85, 0.3, 1))

        def _done(granted, results):
            self._refresh_permission_rows()
            if granted:
                self._set_status_ok('All required permissions granted')
            else:
                self._set_status_warn(
                    'Some permissions denied — check the list above')

        self.permission_manager.request_all(on_complete=_done)

