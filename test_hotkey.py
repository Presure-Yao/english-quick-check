"""Regression tests: application must not paste into external input boxes."""
import ast
from pathlib import Path
import unittest

class LearningModeTests(unittest.TestCase):
    def test_app_has_no_replacement(self):
        source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        self.assertNotIn('replace_result', [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
        self.assertNotIn('replace_ready', source)
        self.assertNotIn('send_ctrl', source)
        self.assertNotIn('替换原输入框', source)

    def test_capture_sends_only_select_and_copy(self):
        source = Path(__file__).with_name('windows_hotkey.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'send_ctrl']
        self.assertEqual(sorted(n.args[0].value for n in calls), [0x41, 0x43])

class ShortcutTests(unittest.TestCase):
    def test_parse_and_validation(self):
        from windows_hotkey import parse_shortcut
        self.assertEqual(parse_shortcut(' shift + ctrl + e '), ('Ctrl+Shift+E', 6, ord('E'), (0x11, 0x10, ord('E'))))
        self.assertEqual(parse_shortcut('Alt+F8')[2], 0x77)
        for invalid in ('G', 'Shift+G', 'Ctrl+Ctrl+G', 'Ctrl+F25', 'Ctrl+Space', 'Ctrl+中'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_shortcut(invalid)

    def test_live_change_and_conflict(self):
        import ctypes
        from windows_hotkey import Hotkey
        user = ctypes.WinDLL('user32')
        hotkey = Hotkey(lambda *_: None, 'Ctrl+Alt+Shift+F23')
        try:
            self.assertIsNone(hotkey.error)
            self.assertEqual(hotkey.change('Ctrl+Alt+Shift+F22'), 'Ctrl+Alt+Shift+F22')
            self.assertTrue(user.RegisterHotKey(None, 77, 0x4007, 0x86))  # Old F23 was released.
            try:
                with self.assertRaises(ValueError):
                    hotkey.change('Ctrl+Alt+Shift+F23')
                self.assertEqual(hotkey.shortcut, 'Ctrl+Alt+Shift+F22')
                self.assertFalse(user.RegisterHotKey(None, 78, 0x4007, 0x85))  # F22 retained.
            finally:
                user.UnregisterHotKey(None, 77)
        finally:
            hotkey.close()
            hotkey.thread.join(2)
        self.assertFalse(hotkey.thread.is_alive())

if __name__ == '__main__':
    unittest.main()
