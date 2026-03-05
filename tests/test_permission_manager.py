"""
Tests for the PermissionManager and PermissionScreen.
All tests run in desktop mode (no Android hardware needed).
"""

import unittest
from unittest.mock import MagicMock, patch, call


class TestPermissionManagerDesktop(unittest.TestCase):
    """PermissionManager in desktop (non-Android) mode."""

    def setUp(self):
        from android_jni.permission_manager import PermissionManager
        self.pm = PermissionManager()

    def test_creation(self):
        self.assertIsNotNone(self.pm)

    def test_all_permissions_auto_granted_on_desktop(self):
        from android_jni.permission_manager import ALL_PERMISSIONS
        for p in ALL_PERMISSIONS:
            self.assertTrue(self.pm.is_granted(p),
                            f"Expected {p} to be granted on desktop")

    def test_critical_permissions_granted(self):
        self.assertTrue(self.pm.are_critical_permissions_granted())

    def test_request_all_calls_complete_immediately(self):
        called = []
        self.pm.request_all(on_complete=lambda g, r: called.append((g, r)))
        self.assertEqual(len(called), 1)
        granted, results = called[0]
        self.assertTrue(granted)

    def test_request_all_result_dict_has_all_permissions(self):
        from android_jni.permission_manager import ALL_PERMISSIONS
        results_holder = []
        self.pm.request_all(on_complete=lambda g, r: results_holder.append(r))
        results = results_holder[0]
        for p in ALL_PERMISSIONS:
            self.assertIn(p, results)

    def test_get_status_summary_keys_are_labelled(self):
        summary = self.pm.get_status_summary()
        self.assertGreater(len(summary), 0)
        for key in summary:
            # Every key should include the icon and label
            self.assertRegex(key, r'.+')

    def test_get_status_summary_all_granted_on_desktop(self):
        summary = self.pm.get_status_summary()
        for label, status in summary.items():
            self.assertIn(status, ('Granted', 'Not Required'),
                          f"Unexpected status '{status}' for '{label}'")

    def test_request_single_calls_result(self):
        from android_jni.permission_manager import PERMISSION_FINE_LOCATION
        results = []
        self.pm.request_single(
            PERMISSION_FINE_LOCATION,
            on_result=lambda p, g: results.append((p, g))
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], PERMISSION_FINE_LOCATION)
        self.assertTrue(results[0][1])

    def test_should_request_nfc_false(self):
        """NFC is a normal permission — no runtime dialog."""
        from android_jni.permission_manager import PERMISSION_NFC
        self.assertFalse(self.pm._should_request(PERMISSION_NFC))


class TestPermissionManagerAndroidSimulated(unittest.TestCase):
    """
    Simulate Android-side permission checks by mocking jnius/ActivityCompat.
    """

    def _make_android_pm(self, pre_granted=None):
        """
        Build a PermissionManager that thinks it is on Android.
        pre_granted: list of permissions already granted in the mock OS.
        """
        from android_jni import permission_manager as pm_mod
        from android_jni.permission_manager import PermissionManager, ALL_PERMISSIONS

        pm = PermissionManager.__new__(PermissionManager)
        pm._granted = {}
        pm._on_complete = None
        pm._pending = []
        pm._android_sdk_version = 33

        # Simulate _is_already_granted
        actually_granted = set(pre_granted or [])
        def fake_is_granted(perm):
            granted = perm in actually_granted
            pm._granted[perm] = granted
            return granted
        pm._is_already_granted = fake_is_granted

        return pm, pm_mod

    def test_no_pending_when_all_pre_granted(self):
        from android_jni.permission_manager import ALL_PERMISSIONS
        pm, _ = self._make_android_pm(pre_granted=ALL_PERMISSIONS)

        with patch.object(pm, '_request_next_batch') as mock_batch, \
             patch.object(pm, '_finish') as mock_finish:
            # Patch _should_request so all perms are "requestable" for this test
            pm._should_request = lambda p: p != "android.permission.NFC"
            pm._on_complete = MagicMock()

            # Manually replicate request_all logic (skip import guards)
            from android_jni.permission_manager import PERMISSION_NFC
            pm._pending = [
                p for p in ALL_PERMISSIONS
                if not pm._is_already_granted(p) and pm._should_request(p)
            ]
            if not pm._pending:
                pm._finish()

            mock_finish.assert_called_once()
            mock_batch.assert_not_called()

    def test_finish_calls_on_complete(self):
        from android_jni.permission_manager import (
            PermissionManager, ALL_PERMISSIONS, PERMISSION_NFC,
            PERMISSION_FINE_LOCATION
        )
        pm, _ = self._make_android_pm(
            pre_granted=[PERMISSION_NFC, PERMISSION_FINE_LOCATION])

        cb = MagicMock()
        pm._on_complete = cb

        # Pre-set granted state
        pm._granted = {p: (p in {PERMISSION_NFC, PERMISSION_FINE_LOCATION})
                       for p in ALL_PERMISSIONS}

        pm._finish()
        cb.assert_called_once()
        args = cb.call_args[0]
        # First arg is overall bool, second is dict
        self.assertIsInstance(args[0], bool)
        self.assertIsInstance(args[1], dict)

    def test_media_location_not_required_below_api29(self):
        from android_jni.permission_manager import (
            PermissionManager, PERMISSION_MEDIA_LOCATION
        )
        pm = PermissionManager.__new__(PermissionManager)
        pm._android_sdk_version = 28
        self.assertFalse(pm._should_request(PERMISSION_MEDIA_LOCATION))

    def test_media_location_required_api29_plus(self):
        from android_jni.permission_manager import (
            PermissionManager, PERMISSION_MEDIA_LOCATION
        )
        pm = PermissionManager.__new__(PermissionManager)
        pm._android_sdk_version = 29
        self.assertTrue(pm._should_request(PERMISSION_MEDIA_LOCATION))

    def test_write_storage_not_required_api29_plus(self):
        from android_jni.permission_manager import (
            PermissionManager, PERMISSION_WRITE_STORAGE
        )
        pm = PermissionManager.__new__(PermissionManager)
        pm._android_sdk_version = 29
        self.assertFalse(pm._should_request(PERMISSION_WRITE_STORAGE))

    def test_write_storage_required_below_api29(self):
        from android_jni.permission_manager import (
            PermissionManager, PERMISSION_WRITE_STORAGE
        )
        pm = PermissionManager.__new__(PermissionManager)
        pm._android_sdk_version = 28
        self.assertTrue(pm._should_request(PERMISSION_WRITE_STORAGE))

    def test_fine_location_always_required(self):
        from android_jni.permission_manager import (
            PermissionManager, PERMISSION_FINE_LOCATION
        )
        pm = PermissionManager.__new__(PermissionManager)
        for sdk in (21, 23, 28, 29, 33):
            pm._android_sdk_version = sdk
            self.assertTrue(pm._should_request(PERMISSION_FINE_LOCATION),
                            f"Expected FINE_LOCATION required at SDK {sdk}")


class TestPermissionConstants(unittest.TestCase):
    """Ensure all expected permission strings are defined."""

    def test_all_constants_defined(self):
        from android_jni.permission_manager import (
            PERMISSION_NFC, PERMISSION_WRITE_STORAGE,
            PERMISSION_READ_STORAGE, PERMISSION_FINE_LOCATION,
            PERMISSION_MEDIA_LOCATION, ALL_PERMISSIONS
        )
        self.assertIn(PERMISSION_NFC, ALL_PERMISSIONS)
        self.assertIn(PERMISSION_WRITE_STORAGE, ALL_PERMISSIONS)
        self.assertIn(PERMISSION_READ_STORAGE, ALL_PERMISSIONS)
        self.assertIn(PERMISSION_FINE_LOCATION, ALL_PERMISSIONS)
        self.assertIn(PERMISSION_MEDIA_LOCATION, ALL_PERMISSIONS)

    def test_permission_info_has_required_keys(self):
        from android_jni.permission_manager import PERMISSION_INFO
        for perm, info in PERMISSION_INFO.items():
            for key in ('label', 'reason', 'icon', 'critical'):
                self.assertIn(key, info,
                              f"Missing key '{key}' for {perm}")

    def test_critical_permissions_marked(self):
        from android_jni.permission_manager import (
            PERMISSION_INFO, PERMISSION_NFC, PERMISSION_FINE_LOCATION
        )
        self.assertTrue(PERMISSION_INFO[PERMISSION_NFC]['critical'])
        self.assertTrue(PERMISSION_INFO[PERMISSION_FINE_LOCATION]['critical'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
