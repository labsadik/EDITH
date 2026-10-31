import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions.file_controller import _is_safe_path, _resolve_path, create_folders


class CreateFoldersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edith-folder-test-", dir=str(Path.home()))
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name) / "Downloads"
        self.parent.mkdir()

    def test_creates_multiple_named_child_folders(self):
        names = [str(number) for number in range(1, 11)]
        result = create_folders(str(self.parent), names)

        self.assertIn("10 created, 0 already existed, 0 failed", result)
        for name in names:
            self.assertTrue((self.parent / name).is_dir(), name)

    def test_existing_directory_is_reported_without_failure(self):
        (self.parent / "1").mkdir()
        result = create_folders(str(self.parent), ["1", "2"])

        self.assertIn("1 created, 1 already existed, 0 failed", result)
        self.assertTrue((self.parent / "1").is_dir())
        self.assertTrue((self.parent / "2").is_dir())

    def test_rejects_nested_and_traversal_names(self):
        result = create_folders(str(self.parent), ["../outside", "nested/child", r"nested\\child", "3"])

        self.assertIn("1 created, 0 already existed, 3 failed", result)
        self.assertIn("3 failed", result)
        self.assertTrue((self.parent / "3").is_dir())
        self.assertFalse((self.parent / "nested").exists())
        self.assertFalse((Path(self.temp.name).parent / "outside").exists())

    def test_bare_relative_paths_are_anchored_to_user_home(self):
        with patch("actions.file_controller.Path.home", return_value=self.parent):
            resolved = _resolve_path("EDITH_Demo/Task_01_Research")
        self.assertEqual(
            resolved,
            self.parent / "EDITH_Demo" / "Task_01_Research",
        )
        self.assertTrue(_is_safe_path(resolved))

    def test_relative_path_traversal_remains_outside_safe_root_and_is_denied(self):
        with (
            patch("actions.file_controller.Path.home", return_value=self.parent),
            patch("actions.file_controller._SAFE_ROOTS", [self.parent]),
        ):
            resolved = _resolve_path("../outside")
            self.assertFalse(_is_safe_path(resolved))

    def test_shortcut_relative_paths_use_the_known_user_folder(self):
        with patch("actions.file_controller._get_documents", return_value=self.parent):
            resolved = _resolve_path(r"documents\\EDITH_Demo\\Task_01_Research")
        self.assertEqual(
            resolved,
            self.parent / "EDITH_Demo" / "Task_01_Research",
        )

    def test_dot_path_is_not_silently_redirected_to_home(self):
        resolved = _resolve_path(".")
        self.assertEqual(resolved, Path.cwd())


if __name__ == "__main__":
    unittest.main()
