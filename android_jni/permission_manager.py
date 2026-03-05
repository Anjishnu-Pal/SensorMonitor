"""
Permission Manager for SensorMonitor
=====================================
Handles Android runtime permission requests (API 23+).
On desktop / non-Android, all permissions are treated as granted.

Permissions managed:
  - NFC                     (no runtime prompt; checked via NfcAdapter)
  - WRITE_EXTERNAL_STORAGE  (runtime on API 21-28; scoped storage on API 29+)
  - READ_EXTERNAL_STORAGE   (runtime on API 21-32)
  - ACCESS_FINE_LOCATION    (runtime; required for NFC on some Android builds)
  - ACCESS_MEDIA_LOCATION   (runtime on API 29+; for media-aware storage)
"""

import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Platform detection ───────────────────────────────────────────────────────
_ANDROID = False
try:
    from jnius import autoclass
    _ANDROID = True
except ImportError:
    pass

# ── Permission constants ─────────────────────────────────────────────────────
PERMISSION_NFC              = "android.permission.NFC"
PERMISSION_WRITE_STORAGE    = "android.permission.WRITE_EXTERNAL_STORAGE"
PERMISSION_READ_STORAGE     = "android.permission.READ_EXTERNAL_STORAGE"
PERMISSION_FINE_LOCATION    = "android.permission.ACCESS_FINE_LOCATION"
PERMISSION_MEDIA_LOCATION   = "android.permission.ACCESS_MEDIA_LOCATION"

# All permissions the app may need (NFC is a normal permission — no runtime
# dialog is shown for it, but we track it for completeness).
ALL_PERMISSIONS: List[str] = [
    PERMISSION_NFC,
    PERMISSION_WRITE_STORAGE,
    PERMISSION_READ_STORAGE,
    PERMISSION_FINE_LOCATION,
    PERMISSION_MEDIA_LOCATION,
]

# Permissions with custom human-readable descriptions shown in the UI
PERMISSION_INFO: Dict[str, Dict[str, str]] = {
    PERMISSION_NFC: {
        "label":  "NFC",
        "reason": "Required to communicate with the NHS 3152 health sensor tag.",
        "icon":   "📡",
        "critical": True,   # App cannot work without this
    },
    PERMISSION_WRITE_STORAGE: {
        "label":  "Storage (Write)",
        "reason": "Required to save sensor readings to CSV files on your device.",
        "icon":   "💾",
        "critical": False,
    },
    PERMISSION_READ_STORAGE: {
        "label":  "Storage (Read)",
        "reason": "Required to load previously saved sensor readings.",
        "icon":   "📂",
        "critical": False,
    },
    PERMISSION_FINE_LOCATION: {
        "label":  "Location",
        "reason": "Required by Android for apps that use NFC/Bluetooth scanning.",
        "icon":   "📍",
        "critical": True,
    },
    PERMISSION_MEDIA_LOCATION: {
        "label":  "Media Location",
        "reason": "Required on Android 10+ for location-aware file storage.",
        "icon":   "🗂️",
        "critical": False,
    },
}


class PermissionManager:
    """
    Manages Android runtime permission requests.

    Usage:
        pm = PermissionManager()
        pm.request_all(on_complete=my_callback)
        # my_callback(granted: bool, results: dict) is called when done
    """

    def __init__(self):
        self._granted: Dict[str, bool] = {}
        self._on_complete: Optional[Callable] = None
        self._pending: List[str] = []
        self._android_sdk_version: int = 0

        if _ANDROID:
            self._android_sdk_version = self._get_sdk_version()
            logger.info(f"PermissionManager: Android SDK {self._android_sdk_version}")
        else:
            logger.info("PermissionManager: Desktop mode — all permissions auto-granted")
            # Pre-grant everything on desktop
            for p in ALL_PERMISSIONS:
                self._granted[p] = True

    # ── Public API ───────────────────────────────────────────────────────────

    def request_all(self, on_complete: Optional[Callable] = None) -> None:
        """
        Request every permission the app needs.
        `on_complete(granted: bool, results: dict)` is called when the user
        has responded to all dialogs (or immediately on desktop).
        """
        self._on_complete = on_complete

        if not _ANDROID:
            # Desktop — treat all as granted immediately
            self._finish()
            return

        # Determine which permissions still need to be requested
        self._pending = [
            p for p in ALL_PERMISSIONS
            if not self._is_already_granted(p) and self._should_request(p)
        ]

        logger.info(f"Permissions to request: {self._pending}")

        if not self._pending:
            logger.info("All permissions already granted")
            self._finish()
            return

        self._request_next_batch()

    def is_granted(self, permission: str) -> bool:
        """Return True if the given permission has been granted."""
        if not _ANDROID:
            return True
        return self._granted.get(permission, False)

    def are_critical_permissions_granted(self) -> bool:
        """Return True if all critical permissions are granted."""
        for perm, info in PERMISSION_INFO.items():
            if info.get("critical") and not self.is_granted(perm):
                # NFC is a normal permission — always granted if device has NFC
                if perm == PERMISSION_NFC:
                    continue
                return False
        return True

    def get_status_summary(self) -> Dict[str, str]:
        """
        Return a dict of {permission_label: 'Granted' | 'Denied' | 'Not Required'}.
        Useful for displaying in the Settings screen.
        """
        summary = {}
        for perm, info in PERMISSION_INFO.items():
            label = f"{info['icon']} {info['label']}"
            if not self._should_request(perm):
                summary[label] = "Not Required"
            elif self.is_granted(perm):
                summary[label] = "Granted"
            else:
                summary[label] = "Denied"
        return summary

    def request_single(self, permission: str,
                       on_result: Optional[Callable] = None) -> None:
        """Request a single permission (e.g. from Settings screen)."""
        if not _ANDROID:
            if on_result:
                on_result(permission, True)
            return

        if self._is_already_granted(permission):
            self._granted[permission] = True
            if on_result:
                on_result(permission, True)
            return

        def _on_single_result(perms, grants):
            # Re-check via OS after the dialog closes; avoids relying on
            # the raw grants format (integer vs string differs by p4a version).
            granted = self._is_already_granted(permission)
            self._granted[permission] = granted
            if on_result:
                on_result(permission, granted)

        self._request_runtime([permission], _on_single_result)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _should_request(self, permission: str) -> bool:
        """
        Return True if this permission requires a runtime dialog
        on the current API level.
        """
        sdk = self._android_sdk_version

        # NFC is a normal permission — declared in manifest, no runtime dialog
        if permission == PERMISSION_NFC:
            return False

        # ACCESS_MEDIA_LOCATION only on API 29+
        if permission == PERMISSION_MEDIA_LOCATION:
            return sdk >= 29

        # WRITE_EXTERNAL_STORAGE not needed on API 29+ (scoped storage)
        if permission == PERMISSION_WRITE_STORAGE:
            return sdk < 29

        return True

    def _is_already_granted(self, permission: str) -> bool:
        """Check whether a permission is currently granted by the OS."""
        if not _ANDROID:
            return True
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            PackageManager = autoclass('android.content.pm.PackageManager')
            activity = PythonActivity.mActivity
            result = activity.checkSelfPermission(permission)
            granted = (result == PackageManager.PERMISSION_GRANTED)
            self._granted[permission] = granted
            return granted
        except Exception as e:
            logger.warning(f"Could not check permission {permission}: {e}")
            return False

    def _request_next_batch(self) -> None:
        """Request all pending permissions in one batch call."""
        if not self._pending:
            self._finish()
            return

        self._request_runtime(
            self._pending,
            self._on_batch_result
        )

    def _request_runtime(self, permissions: List[str],
                          callback: Callable) -> None:
        """Call Android ActivityCompat.requestPermissions()."""
        try:
            from jnius import autoclass

            # Use the android.permissions module from p4a if available
            try:
                from android.permissions import request_permissions, Permission
                request_permissions(permissions, callback)
                return
            except ImportError:
                pass

            # Fallback: direct JNI call
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            ActivityCompat = autoclass('androidx.core.app.ActivityCompat')

            perms_array = permissions  # pyjnius converts list → String[]
            ActivityCompat.requestPermissions(activity, perms_array, 1001)
            # Without a proper onRequestPermissionsResult hook we optimistically
            # mark as granted and let _is_already_granted re-check later.
            for p in permissions:
                self._granted[p] = True
            callback(permissions, ["android.content.pm.PackageManager.PERMISSION_GRANTED"] * len(permissions))

        except Exception as e:
            logger.error(f"Error requesting permissions: {e}")
            # Optimistically continue — permissions might have been granted
            # at install time (older Android) or via manifest.
            for p in permissions:
                self._granted[p] = self._is_already_granted(p)
            self._finish()

    def _on_batch_result(self, permissions: List[str],
                          grant_results: List) -> None:
        """Called by the Android permission framework with results."""
        try:
            from android.permissions import check_permission
            for perm in permissions:
                self._granted[perm] = check_permission(perm)
        except Exception:
            # Re-check via JNI
            for perm in permissions:
                self._granted[perm] = self._is_already_granted(perm)

        granted_count = sum(1 for v in self._granted.values() if v)
        logger.info(
            f"Permission results: {granted_count}/{len(ALL_PERMISSIONS)} granted"
        )
        self._finish()

    def _finish(self) -> None:
        """All permissions handled — invoke completion callback."""
        all_grants = {p: self._granted.get(p, False) for p in ALL_PERMISSIONS}
        overall = self.are_critical_permissions_granted()

        logger.info(
            f"Permission check complete — critical permissions granted: {overall}"
        )
        for perm, granted in all_grants.items():
            info = PERMISSION_INFO.get(perm, {})
            label = info.get("label", perm)
            status = "GRANTED" if granted else "DENIED"
            logger.info(f"  {label}: {status}")

        if self._on_complete:
            self._on_complete(overall, all_grants)

    @staticmethod
    def _get_sdk_version() -> int:
        """Return Android SDK integer version, or 0 on error."""
        try:
            from jnius import autoclass
            Build = autoclass('android.os.Build$VERSION')
            return Build.SDK_INT
        except Exception:
            return 0
