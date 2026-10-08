"""Windows global hotkey + explicit plain-text selection capture. No keystroke logging."""
import ctypes
from ctypes import wintypes
import os
import threading
import time
import queue


def parse_shortcut(value):
    parts = [p.strip().upper() for p in value.split('+')]
    modifiers = {'CTRL': (2, 0x11, 'Ctrl'), 'ALT': (1, 0x12, 'Alt'), 'SHIFT': (4, 0x10, 'Shift')}
    if len(parts) < 2 or len(set(parts)) != len(parts) or any(p not in modifiers for p in parts[:-1]):
        raise ValueError('快捷键格式：Ctrl+Alt+G；支持 Ctrl / Alt / Shift 加字母、数字或 F1–F24。')
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
        key = f'F{int(key[1:])}'
    else:
        raise ValueError('主键仅支持 A–Z、0–9 或 F1–F24。')
    if not any(p in parts[:-1] for p in ('CTRL', 'ALT')):
        raise ValueError('请至少包含 Ctrl 或 Alt，避免影响正常打字。')
    ordered = [p for p in modifiers if p in parts[:-1]]
    mask = sum(modifiers[p][0] for p in ordered)
    return '+'.join([modifiers[p][2] for p in ordered] + [key]), mask, vk, tuple(modifiers[p][1] for p in ordered) + (vk,)


class Hotkey:
    def __init__(self, callback, shortcut='Ctrl+Alt+G'):
        self.callback = callback
        self.shortcut, self.modifiers, self.vk, self.release_keys = parse_shortcut(shortcut)
        self.commands = queue.Queue()
        self.thread_id = None
        self.ready = threading.Event()
        self.error = None
        self.allow_clipboard_overwrite = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.ready.wait(2)

    def _loop(self):
        if os.name != 'nt':
            self.error = '全局快捷键仅支持 Windows。'
            self.ready.set()
            return
        user = ctypes.WinDLL('user32', use_last_error=True)
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # Create this thread's message queue.
        active_id = 1
        registered = bool(user.RegisterHotKey(None, active_id, 0x4000 | self.modifiers, self.vk))
        if not registered:
            self.error = f'{self.shortcut} 已被其他程序占用。仍可粘贴检查或在设置中修改快捷键。'
        self.ready.set()
        try:
            while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x8001:
                    while not self.commands.empty():
                        command = self.commands.get_nowait()
                        with command['lock']:
                            if command['cancelled']:
                                continue
                            name, modifiers, vk, keys = command['shortcut']
                            new_id = 2 if active_id == 1 else 1
                            if registered and name == self.shortcut:
                                command['error'] = None
                            elif user.RegisterHotKey(None, new_id, 0x4000 | modifiers, vk):
                                if registered:
                                    user.UnregisterHotKey(None, active_id)
                                active_id, registered = new_id, True
                                self.shortcut, self.modifiers, self.vk, self.release_keys = name, modifiers, vk, keys
                                self.error = None
                                command['error'] = None
                            else:
                                command['error'] = f'{name} 已被其他程序占用或系统不允许；原快捷键未改变。'
                            command['done'].set()
                elif msg.message == 0x0312 and registered and msg.wParam == active_id:
                    try:
                        target = foreground_window()
                        text = capture_selection(select_all=True, target=target, allow_overwrite=self.allow_clipboard_overwrite, release_keys=self.release_keys)
                        self.callback({'text': text, 'target': target}, None)
                    except Exception as exc:
                        self.callback(None, str(exc))
        finally:
            if registered:
                user.UnregisterHotKey(None, active_id)

    def change(self, shortcut):
        parsed = parse_shortcut(shortcut)
        if not self.thread.is_alive() or not self.thread_id:
            raise RuntimeError('快捷键线程不可用，请重新启动软件。')
        command = {'shortcut': parsed, 'done': threading.Event(), 'lock': threading.Lock(), 'cancelled': False}
        self.commands.put(command)
        if not ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x8001, 0, 0):
            with command['lock']:
                command['cancelled'] = True
            raise RuntimeError('无法更新快捷键；原设置未改变。')
        if not command['done'].wait(4):
            with command['lock']:
                if not command['done'].is_set():
                    command['cancelled'] = True
                    raise RuntimeError('快捷键捕获仍在进行，请稍后保存；原设置未改变。')
        if command['error']:
            raise ValueError(command['error'])
        return parsed[0]

    def close(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)


def foreground_window():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    return user.GetForegroundWindow()


def send_ctrl(key):
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
    class UNION(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]
    class INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD), ('u', UNION)]
    events = (INPUT * 4)()
    for event, code, flags in zip(events, (0x11, key, key, 0x11), (0, 0, 2, 2)):
        event.type = 1
        event.u.ki = KEYBDINPUT(code, 0, flags, 0, 0)
    user = ctypes.WinDLL('user32', use_last_error=True)
    if user.SendInput(4, events, ctypes.sizeof(INPUT)) != 4:
        raise RuntimeError('无法操作目标窗口；请手动复制粘贴。')


def capture_selection(select_all=False, target=None, allow_overwrite=False, release_keys=(0x11, 0x12, 0x47)):
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetClipboardData.argtypes = [wintypes.UINT]
    user.GetClipboardData.restype = wintypes.HANDLE
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.restype = wintypes.HGLOBAL

    def open_clipboard():
        for _ in range(20):
            if user.OpenClipboard(None):
                return
            time.sleep(0.025)
        raise RuntimeError('剪贴板正被其他程序使用，请稍后重试。')

    def read_text():
        handle = user.GetClipboardData(13)
        if not handle:
            return ''
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise RuntimeError('无法读取剪贴板。')
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel.GlobalUnlock(handle)

    # Rich clipboard formats cannot be losslessly reconstructed here: refuse before copying.
    open_clipboard()
    try:
        fmt, formats = 0, []
        while True:
            fmt = user.EnumClipboardFormats(fmt)
            if not fmt:
                break
            formats.append(fmt)
        rich_clipboard = any(f not in (1, 7, 13, 16) for f in formats)
        if rich_clipboard and not allow_overwrite:
            raise RuntimeError('剪贴板含图片、文件或富文本，捕获已停止。请在助手中勾选“允许快捷键覆盖富文本/图片剪贴板”，然后回到输入框重新按快捷键；或手动粘贴。')
        previous = read_text()
        before = user.GetClipboardSequenceNumber()
    finally:
        user.CloseClipboard()
    # Wait until shortcut modifiers are released; otherwise Ctrl+C can become Ctrl+Alt+C.
    deadline = time.monotonic() + 2
    while any(user.GetAsyncKeyState(k) & 0x8000 for k in release_keys):
        if time.monotonic() > deadline:
            raise RuntimeError('请松开快捷键后再试。')
        time.sleep(0.02)

    if target is not None and foreground_window() != target:
        raise RuntimeError('焦点窗口已改变，操作停止。')
    if select_all:
        send_ctrl(0x41)
        time.sleep(0.08)
    if target is not None and foreground_window() != target:
        raise RuntimeError('焦点窗口已改变，操作停止。')
    send_ctrl(0x43)
    deadline = time.monotonic() + 1.2
    while user.GetClipboardSequenceNumber() == before:
        if time.monotonic() > deadline:
            raise RuntimeError('未捕获到选中文字，请先选择文本。密码框和部分编辑器不支持。')
        time.sleep(0.02)
    open_clipboard()
    try:
        copied_sequence = user.GetClipboardSequenceNumber()
        selected = read_text()
    finally:
        user.CloseClipboard()
    # Best-effort restoration only when nobody changed the clipboard in the meantime.
    open_clipboard()
    try:
        if not rich_clipboard and user.GetClipboardSequenceNumber() == copied_sequence:
            data = (previous + '\0').encode('utf-16-le')
            handle = kernel.GlobalAlloc(0x0002, len(data))
            pointer = kernel.GlobalLock(handle) if handle else None
            if pointer:
                ctypes.memmove(pointer, data, len(data))
                kernel.GlobalUnlock(handle)
                user.EmptyClipboard()
                if not user.SetClipboardData(13, handle):
                    kernel.GlobalFree(handle)
            elif handle:
                kernel.GlobalFree(handle)
    finally:
        user.CloseClipboard()
    if not selected.strip():
        raise RuntimeError('选区为空或不是普通文本，请手动粘贴。')
    return selected

