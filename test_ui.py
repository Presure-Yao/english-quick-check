"""Offline GUI/settings/tray regressions; no personal settings or clipboard access."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
from grammar_core import SettingsStore
from windows_tray import TrayIcon


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.app = App(self.root, demo=True)
        self.app.store = SettingsStore(Path(self.temp.name) / 'settings.json')
        self.root.update()

    def tearDown(self):
        if not self.app.closed:
            self.app.close()
        self.temp.cleanup()

    def test_models_loaded_without_changing_selection(self):
        import time
        from tkinter import ttk
        self.app.open_settings()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith('设置'))
        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)
        widgets = list(walk(dialog))
        combos = [w for w in widgets if isinstance(w, ttk.Combobox)]
        model = next(w for w in combos if str(w.cget('state')) == 'normal')
        current = model.get()
        key = next(w for w in widgets if isinstance(w, ttk.Entry) and str(w.cget('show')) == '•')
        key.insert(0, 'fake-test-key')
        button = next(w for w in widgets if 'text' in w.keys() and w.cget('text') == '获取模型列表')
        with patch('app.fetch_models', return_value=['example-a', 'example-b']):
            button.invoke()
            deadline = time.monotonic() + 2
            while tuple(model.cget('values')) != ('example-a', 'example-b') and time.monotonic() < deadline:
                self.root.update()
            self.assertEqual(tuple(model.cget('values')), ('example-a', 'example-b'))
        self.assertEqual(model.get(), current)
        dialog.destroy()

    def test_floating_button_hover(self):
        self.app.suggestion.show()
        self.root.update()
        for control, color in ((self.app.suggestion.close_button, '#f1dada'),
                               (self.app.suggestion.collapse_button, '#dbe7d6')):
            self.assertEqual(control.cget('cursor'), 'hand2')
            control.event_generate('<Enter>')
            self.root.update()
            self.assertEqual(control.cget('bg'), color)
            control.event_generate('<Leave>')
            self.root.update()
            self.assertEqual(control.cget('bg'), '#eef2e9')

    def test_shortcut_save_and_rollback(self):
        from unittest.mock import Mock
        self.app.demo = False
        self.app.hotkey = Mock()
        settings = {**self.app.settings, 'shortcut': 'Ctrl+Shift+E'}
        self.app.apply_settings(settings)
        self.assertEqual(self.app.store.load()['shortcut'], 'Ctrl+Shift+E')
        self.assertIn('Ctrl+Shift+E', self.app.shortcut_label.get())
        with patch.object(self.app.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.app.apply_settings({**settings, 'shortcut': 'Alt+F8'})
        self.assertEqual(self.app.settings['shortcut'], 'Ctrl+Shift+E')
        self.assertEqual(self.app.hotkey.change.call_args.args, ('Ctrl+Shift+E',))
        self.app.hotkey.change.side_effect = ValueError('occupied')
        with self.assertRaises(ValueError):
            self.app.apply_settings({**settings, 'shortcut': 'Alt+F8'})
        self.assertEqual(self.app.store.load()['shortcut'], 'Ctrl+Shift+E')
        self.app.hotkey = None

    def test_native_tray_open_hide_and_exit(self):
        self.app.tray = TrayIcon(Path(__file__).with_name('assets') / 'app.ico',
                                 lambda action: self.app.events.put(('tray', action)))
        self.assertIsNone(self.app.tray.error)
        self.app.demo = False  # Close uses production lifecycle, still no key/network/hotkey.
        self.app.window_close()
        self.assertEqual(self.root.state(), 'withdrawn')
        user = ctypes.WinDLL('user32')
        user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.SendMessageW.restype = ctypes.c_ssize_t
        user.SendMessageW(self.app.tray.hwnd, 0x8001, 0, 0x0203)
        self.app.poll()
        self.root.update()
        self.assertEqual(self.root.state(), 'normal')
        self.app.events.put(('tray', 'exit'))
        self.app.poll()
        self.assertTrue(self.app.closed)
        self.assertFalse(self.app.tray.thread.is_alive())
        self.assertIsNone(self.app.tray.hwnd)

    def test_close_without_tray_exits(self):
        self.app.demo = False
        self.app.window_close()
        self.assertTrue(self.app.closed)

    def test_close_exit_preference(self):
        self.app.demo = False
        self.app.settings['close_behavior'] = 'exit'
        with patch.object(self.app, 'tray_available', return_value=True):
            self.app.window_close()
        self.assertTrue(self.app.closed)

    def test_settings_dialog_persistence(self):
        self.app.demo = False
        self.app.open_settings()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith('设置'))
        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)
        widgets = list(walk(dialog))
        for label in ('直接退出软件', '保留中文，只检查英文部分', '下次启动直接进入托盘（不显示主窗口）', '快捷键捕获后调用 AI（会上传整段原文）'):
            next(w for w in widgets if 'text' in w.keys() and w.cget('text') == label).invoke()
        next(w for w in widgets if 'text' in w.keys() and w.cget('text') == '保存全部设置').invoke()
        saved = self.app.store.load()
        self.assertEqual(saved['close_behavior'], 'exit')
        self.assertEqual(saved['chinese_mode'], 'preserve')
        self.assertTrue(saved['start_in_tray'])
        self.assertTrue(saved['auto_ai'])
        self.assertFalse(saved['allow_overwrite'])
        self.app.auto_ai.set(False)
        self.app.save_capture_options()
        self.assertFalse(self.app.store.load()['auto_ai'])


if __name__ == '__main__':
    unittest.main()
