"""Non-network Windows GUI/hotkey registration and process memory smoke test."""
import ctypes
from ctypes import wintypes
import tkinter as tk
from app import App

class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]

root = tk.Tk()
app = App(root)
root.withdraw()

def finish():
    app.run_rules()
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi')
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    print(f'Working set: {counters.WorkingSetSize / 1024**2:.2f} MiB')
    print(f'Private committed bytes: {counters.PagefileUsage / 1024**2:.2f} MiB')
    print('Hotkey registration:', app.hotkey.error or 'OK (Ctrl+Alt+G)')
    app.close()
    app.hotkey.thread.join(timeout=2)
    assert not app.hotkey.thread.is_alive(), 'Hotkey did not shut down'
    print('GUI initialization, rules, and hotkey shutdown: OK; no API request sent.')

root.after(3000, finish)
root.mainloop()
