# -*- coding: utf-8 -*-
"""写入路径硬闸单测：C:\\Users\\l\\ai_config.json 被拒，AppData 与 D:\\ 放行。

单独执行：python tools/test_write_guard.py
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

from write_guard import UnsafeWritePath, resolve_write_path, user_home  # noqa: E402


class WriteGuardTests(unittest.TestCase):
    def test_user_home_root_rejected(self):
        with self.assertRaises(UnsafeWritePath):
            resolve_write_path(user_home())

    def test_direct_child_of_user_home_rejected(self):
        """现场事故路径：C:\\Users\\l\\ai_config.json。"""
        target = user_home() / "ai_config.json"
        with self.assertRaises(UnsafeWritePath) as ctx:
            resolve_write_path(str(target))
        self.assertIn("直属一层", str(ctx.exception))

    def test_another_direct_child_rejected(self):
        with self.assertRaises(UnsafeWritePath):
            resolve_write_path(str(user_home() / "notes.txt"))

    def test_appdata_local_allowed(self):
        target = user_home() / "AppData" / "Local" / "GUGA" / "ai_config.json"
        resolved = resolve_write_path(str(target))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(resolved, Path(os.path.abspath(str(target))).resolve())

    def test_d_drive_allowed(self):
        target = Path(r"D:\rengongzhineng\guga-competition\dist\out.zip")
        resolved = resolve_write_path(str(target))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(str(resolved), os.path.abspath(str(target)))

    def test_tilde_and_home_variables_rejected(self):
        for raw in ("~/ai_config.json", "$HOME/ai_config.json",
                    "$home/ai_config.json", "%USERPROFILE%\\ai_config.json"):
            with self.assertRaises(UnsafeWritePath, msg=raw):
                resolve_write_path(raw)

    def test_empty_path_rejected(self):
        with self.assertRaises(UnsafeWritePath):
            resolve_write_path("   ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
