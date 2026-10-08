"""Actual Ctrl+A/C capture on an isolated Tk input; never accesses chat windows.
Refuses rich clipboard rather than destroying the user's clipboard.
"""
import queue
import threading
import tkinter as tk
from windows_hotkey import capture_selection, foreground_window

root = tk.Tk()
root.title('Grammar assistant isolated capture test')
root.geometry('600x180+50+50')
text = tk.Text(root)
text.pack(fill='both', expand=True)
expected = 'This is an isolated capture test. No chat message is sent.'
text.insert('1.0', expected)
text.bind('<Control-a>', lambda event: (text.tag_add('sel', '1.0', 'end-1c'), 'break')[-1])
root.attributes('-topmost', True)
text.focus_force()
results = queue.Queue()

def start():
    target = foreground_window()
    def worker():
        try:
            results.put((capture_selection(select_all=True, target=target), None))
        except Exception as exc:
            results.put((None, str(exc)))
    threading.Thread(target=worker, daemon=True).start()

def poll():
    try:
        value, error = results.get_nowait()
    except queue.Empty:
        root.after(50, poll)
        return
    root.destroy()
    if error:
        print('Capture test blocked:', error)
    else:
        assert value == expected, repr(value)
        print('Actual Ctrl+A/C capture in isolated input: PASS')

root.after(500, start)
root.after(550, poll)
root.mainloop()
