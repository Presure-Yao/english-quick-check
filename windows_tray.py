"""Native Windows notification icon. Callbacks enqueue actions; never touch Tk here."""
import ctypes
from ctypes import wintypes as w
import threading
import uuid


class TrayIcon:
    def __init__(self, icon_path, callback):
        self.icon_path = str(icon_path)
        self.callback = callback
        self.error = None
        self.hwnd = None
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            self.error = '托盘启动超时；主窗口关闭将真正退出。'
            self.close()

    def close(self):
        self.stopping.set()
        if self.hwnd:
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
            user.PostMessageW(self.hwnd, 0x0010, 0, 0)

    def _loop(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', w.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('hInstance', w.HINSTANCE), ('hIcon', w.HICON),
                        ('hCursor', w.HANDLE), ('hbrBackground', w.HBRUSH),
                        ('lpszMenuName', w.LPCWSTR), ('lpszClassName', w.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', w.DWORD), ('Data2', w.WORD), ('Data3', w.WORD), ('Data4', ctypes.c_byte * 8)]

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [('cbSize', w.DWORD), ('hWnd', w.HWND), ('uID', w.UINT), ('uFlags', w.UINT),
                        ('uCallbackMessage', w.UINT), ('hIcon', w.HICON), ('szTip', w.WCHAR * 128),
                        ('dwState', w.DWORD), ('dwStateMask', w.DWORD), ('szInfo', w.WCHAR * 256),
                        ('uVersion', w.UINT), ('szInfoTitle', w.WCHAR * 64), ('dwInfoFlags', w.DWORD),
                        ('guidItem', GUID), ('hBalloonIcon', w.HICON)]

        # Pointer-sized signatures matter on Windows x64.
        signatures = {
            'RegisterClassW': ([ctypes.POINTER(WNDCLASS)], w.WORD),
            'UnregisterClassW': ([w.LPCWSTR, w.HINSTANCE], w.BOOL),
            'CreateWindowExW': ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p], w.HWND),
            'DefWindowProcW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], LRESULT),
            'DestroyWindow': ([w.HWND], w.BOOL),
            'LoadImageW': ([w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT], w.HANDLE),
            'DestroyIcon': ([w.HICON], w.BOOL),
            'CreatePopupMenu': ([], w.HMENU),
            'AppendMenuW': ([w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR], w.BOOL),
            'DestroyMenu': ([w.HMENU], w.BOOL),
            'GetCursorPos': ([ctypes.POINTER(w.POINT)], w.BOOL),
            'SetForegroundWindow': ([w.HWND], w.BOOL),
            'TrackPopupMenu': ([w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, ctypes.c_void_p], w.UINT),
            'PostMessageW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            'RegisterWindowMessageW': ([w.LPCWSTR], w.UINT),
            'GetMessageW': ([ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], ctypes.c_int),
            'TranslateMessage': ([ctypes.POINTER(w.MSG)], w.BOOL),
            'DispatchMessageW': ([ctypes.POINTER(w.MSG)], LRESULT),
        }
        for name, (argtypes, restype) in signatures.items():
            func = getattr(user, name)
            func.argtypes, func.restype = argtypes, restype
        kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        kernel.GetModuleHandleW.restype = w.HINSTANCE
        shell.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATA)]
        shell.Shell_NotifyIconW.restype = w.BOOL
        instance = kernel.GetModuleHandleW(None)
        class_name = 'EnglishQuickCheckTray_' + uuid.uuid4().hex
        taskbar_created = user.RegisterWindowMessageW('TaskbarCreated')
        data = NOTIFYICONDATA()
        data.cbSize = ctypes.sizeof(data)
        data.uID, data.uFlags, data.uCallbackMessage = 1, 0x07, 0x8001
        data.szTip = 'English Quick Check · 双击打开，右键退出'
        icon = None
        registered = False

        def menu(hwnd):
            popup = user.CreatePopupMenu()
            if not popup:
                return
            try:
                user.AppendMenuW(popup, 0, 1, '打开主窗口')
                user.AppendMenuW(popup, 0, 2, '退出')
                point = w.POINT()
                user.GetCursorPos(ctypes.byref(point))
                user.SetForegroundWindow(hwnd)
                command = user.TrackPopupMenu(popup, 0x0102, point.x, point.y, 0, hwnd, None)
                user.PostMessageW(hwnd, 0, 0, 0)
                if command in (1, 2):
                    self.callback('open' if command == 1 else 'exit')
            finally:
                user.DestroyMenu(popup)

        @WNDPROC
        def proc(hwnd, message, wp, lp):
            if message == 0x8001:
                if lp == 0x0203:  # WM_LBUTTONDBLCLK
                    self.callback('open')
                elif lp in (0x0205, 0x007b):  # right button / context menu
                    menu(hwnd)
                return 0
            if message == taskbar_created:
                if not self.stopping.is_set() and not shell.Shell_NotifyIconW(0, ctypes.byref(data)):
                    self.callback('error')
                return 0
            if message == 0x0010:
                user.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:
                shell.Shell_NotifyIconW(2, ctypes.byref(data))
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd, message, wp, lp)

        try:
            wc = WNDCLASS()
            wc.style = 0x0008  # CS_DBLCLKS: receive actual double-click notifications.
            wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = proc, instance, class_name
            if not user.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            registered = True
            # Hidden top-level window receives TaskbarCreated after Explorer restarts.
            self.hwnd = user.CreateWindowExW(0, class_name, '', 0, 0, 0, 0, 0, None, None, instance, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            icon = user.LoadImageW(None, self.icon_path, 1, 0, 0, 0x0010 | 0x0040)
            if not icon:
                raise ctypes.WinError(ctypes.get_last_error())
            data.hWnd, data.hIcon = self.hwnd, icon
            if self.stopping.is_set():
                return
            if not shell.Shell_NotifyIconW(0, ctypes.byref(data)):
                raise RuntimeError('Windows 未能添加托盘图标。')
            self.ready.set()
            msg = w.MSG()
            while not self.stopping.is_set() and user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.error = '托盘不可用；关闭主窗口将退出。' + str(exc)
        finally:
            if self.hwnd:
                shell.Shell_NotifyIconW(2, ctypes.byref(data))
                user.DestroyWindow(self.hwnd)
                self.hwnd = None
            if icon:
                user.DestroyIcon(icon)
            if registered:
                user.UnregisterClassW(class_name, instance)
            self.ready.set()
