"""
Permission Request Screen
=========================
Full-screen overlay shown on first launch (and any time a critical
permission is missing).  Lists every permission with its icon, label
and rationale, then requests them in one go when the user taps
"Grant Permissions".

On desktop (no Android) it immediately passes through.
"""

import logging
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.clock import Clock

logger = logging.getLogger(__name__)


class _PermissionRow(BoxLayout):
    """Single permission row: icon + name + rationale + status badge."""

    def __init__(self, icon: str, label: str, reason: str,
                 critical: bool, **kwargs):
        super().__init__(orientation='horizontal',
                         size_hint_y=None, height=72,
                         spacing=8, padding=[4, 6, 4, 6],
                         **kwargs)

        # Left: icon
        icon_lbl = Label(
            text=icon, font_size='26sp',
            size_hint_x=None, width=40,
            halign='center', valign='middle')
        icon_lbl.bind(size=icon_lbl.setter('text_size'))
        self.add_widget(icon_lbl)

        # Centre: label + reason
        text_col = BoxLayout(orientation='vertical', spacing=2)
        name_lbl = Label(
            text=('[b]' + label + '[/b]' +
                  (' [color=ff6666](Required)[/color]' if critical else '')),
            markup=True, font_size='14sp',
            halign='left', valign='middle',
            size_hint_y=None, height=28)
        name_lbl.bind(size=name_lbl.setter('text_size'))

        reason_lbl = Label(
            text=reason, font_size='11sp',
            color=(0.75, 0.75, 0.75, 1),
            halign='left', valign='top',
            size_hint_y=None, height=36,
            text_size=(None, None))
        reason_lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))

        text_col.add_widget(name_lbl)
        text_col.add_widget(reason_lbl)
        self.add_widget(text_col)

        # Right: status badge (updated after user responds)
        self.badge = Label(
            text='Pending', font_size='11sp',
            color=(1, 0.75, 0.2, 1),
            size_hint_x=None, width=58,
            halign='center', valign='middle')
        self.badge.bind(size=self.badge.setter('text_size'))
        self.add_widget(self.badge)

    def set_granted(self) -> None:
        self.badge.text = 'Granted'
        self.badge.color = (0.4, 1.0, 0.4, 1)

    def set_denied(self) -> None:
        self.badge.text = 'Denied'
        self.badge.color = (1.0, 0.4, 0.4, 1)

    def set_not_required(self) -> None:
        self.badge.text = 'N/A'
        self.badge.color = (0.6, 0.6, 0.6, 1)


class PermissionScreen(BoxLayout):
    """
    Overlay that blocks the main UI until the user grants (or skips)
    the required permissions.

    Parameters
    ----------
    on_complete : callable(granted: bool, results: dict)
        Called when the user taps a button and the OS has replied.
    permission_manager : PermissionManager
        The app-wide PermissionManager instance.
    """

    def __init__(self, permission_manager, on_complete, **kwargs):
        super().__init__(orientation='vertical',
                         padding=16, spacing=12, **kwargs)
        self.permission_manager = permission_manager
        self.on_complete = on_complete
        self._rows = {}   # permission key → _PermissionRow
        self._completed = False  # guard against double-call

        # Dark background
        with self.canvas.before:
            Color(0.08, 0.08, 0.12, 1)
            self._bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_bg, pos=self._update_bg)

        self._build_ui()

    # ── UI builder ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        from android_jni.permission_manager import PERMISSION_INFO

        # ── App logo / title block ────────────────────────────────────────
        header = BoxLayout(orientation='vertical',
                           size_hint_y=None, height=100, spacing=4)

        Logo = Label(text='📡', font_size='42sp',
                     size_hint_y=None, height=54,
                     halign='center', valign='middle')
        Logo.bind(size=Logo.setter('text_size'))
        header.add_widget(Logo)

        title = Label(
            text='[b]SensorMonitor[/b]', markup=True,
            font_size='20sp', size_hint_y=None, height=34,
            halign='center', valign='middle',
            color=(0.9, 0.9, 1, 1))
        title.bind(size=title.setter('text_size'))
        header.add_widget(title)
        self.add_widget(header)

        # ── Subtitle ──────────────────────────────────────────────────────
        sub = Label(
            text='To use the NHS 3152 health sensor, please grant the\n'
                 'following permissions.',
            font_size='13sp',
            size_hint_y=None, height=44,
            halign='center', valign='middle',
            color=(0.75, 0.75, 0.75, 1))
        sub.bind(size=sub.setter('text_size'))
        self.add_widget(sub)

        # ── Permissions list ──────────────────────────────────────────────
        scroll = ScrollView(size_hint_y=1)
        perm_list = BoxLayout(orientation='vertical',
                              size_hint_y=None, spacing=6)
        perm_list.bind(minimum_height=perm_list.setter('height'))

        for perm_key, info in PERMISSION_INFO.items():
            row = _PermissionRow(
                icon=info['icon'],
                label=info['label'],
                reason=info['reason'],
                critical=info.get('critical', False)
            )
            # Mark those that don't require a dialog upfront
            if not self.permission_manager._should_request(perm_key):
                row.set_not_required()
            self._rows[perm_key] = row
            perm_list.add_widget(row)

        scroll.add_widget(perm_list)
        self.add_widget(scroll)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=52, spacing=10)

        self.skip_btn = Button(
            text='Skip for now',
            background_color=(0.3, 0.3, 0.3, 1),
            font_size='13sp')
        self.skip_btn.bind(on_press=self._on_skip)
        btn_row.add_widget(self.skip_btn)

        self.grant_btn = Button(
            text='Grant Permissions',
            background_color=(0.2, 0.55, 0.9, 1),
            bold=True, font_size='14sp')
        self.grant_btn.bind(on_press=self._on_grant)
        btn_row.add_widget(self.grant_btn)

        self.add_widget(btn_row)

        # ── Status message (shown after request) ─────────────────────────
        self.status_lbl = Label(
            text='', size_hint_y=None, height=28,
            font_size='12sp', halign='center',
            color=(0.8, 0.8, 0.8, 1))
        self.status_lbl.bind(size=self.status_lbl.setter('text_size'))
        self.add_widget(self.status_lbl)

    # ── Button handlers ──────────────────────────────────────────────────────

    def _on_grant(self, _instance) -> None:
        self.grant_btn.disabled = True
        self.skip_btn.disabled = True
        self.status_lbl.text = 'Requesting permissions…'
        self.status_lbl.color = (1, 0.85, 0.3, 1)

        self.permission_manager.request_all(
            on_complete=self._on_permission_result
        )

    def _on_skip(self, _instance) -> None:
        logger.info("User skipped permission request")
        self.status_lbl.text = (
            'Some features may not work without required permissions.')
        self.status_lbl.color = (1, 0.5, 0.2, 1)
        # Short delay so the user can read the warning before dismissal
        Clock.schedule_once(lambda _dt: self._complete(False, {}), 1.5)

    # ── Permission result handler ────────────────────────────────────────────

    def _on_permission_result(self, overall_granted: bool,
                               results: dict) -> None:
        from android_jni.permission_manager import PERMISSION_INFO

        # Update all row badges
        for perm_key, row in self._rows.items():
            if not self.permission_manager._should_request(perm_key):
                row.set_not_required()
            elif results.get(perm_key, False):
                row.set_granted()
            else:
                row.set_denied()

        if overall_granted:
            self.status_lbl.text = '✓ All required permissions granted!'
            self.status_lbl.color = (0.4, 1.0, 0.4, 1)
        else:
            self.status_lbl.text = (
                'Some permissions were denied. '
                'NFC / storage features may be limited.')
            self.status_lbl.color = (1.0, 0.55, 0.2, 1)

        # Add an "Open Settings / Continue" button for denied critical perms
        if not overall_granted:
            self._add_open_settings_button()

        # If all granted: auto-dismiss after a short pause.
        # If denied: do NOT auto-dismiss — user must tap a button so they can
        # choose "Open App Settings" or "Continue Anyway".
        if overall_granted:
            Clock.schedule_once(
                lambda _dt: self._complete(overall_granted, results), 1.8
            )

    def _add_open_settings_button(self) -> None:
        """Show a button to open Android App Settings for manual permission grant."""
        open_btn = Button(
            text='Open App Settings',
            size_hint_y=None, height=44,
            background_color=(0.7, 0.4, 0.1, 1),
            font_size='13sp')
        open_btn.bind(on_press=self._open_android_settings)
        self.add_widget(open_btn)

        cont_btn = Button(
            text='Continue Anyway',
            size_hint_y=None, height=44,
            background_color=(0.25, 0.25, 0.25, 1),
            font_size='13sp')
        cont_btn.bind(on_press=lambda _: self._complete(False, {}))
        self.add_widget(cont_btn)

    def _open_android_settings(self, _instance) -> None:
        """Deep-link into the app's permission settings on Android."""
        try:
            from jnius import autoclass
            Intent   = autoclass('android.content.Intent')
            Settings = autoclass('android.provider.Settings')
            Uri      = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            activity = PythonActivity.mActivity
            intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            intent.setData(Uri.parse(f'package:{activity.getPackageName()}'))
            activity.startActivity(intent)
        except Exception as e:
            logger.warning(f"Could not open Android settings: {e}")

    def _complete(self, granted: bool, results: dict) -> None:
        if self._completed:
            return
        self._completed = True
        if self.on_complete:
            self.on_complete(granted, results)

    # ── Background resize ────────────────────────────────────────────────────

    def _update_bg(self, *_args) -> None:
        self._bg_rect.size = self.size
        self._bg_rect.pos  = self.pos
