import tempfile
import unittest
from pathlib import Path

from actions.file_controller import create_folders


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


if __name__ == "__main__":
    unittest.main()
