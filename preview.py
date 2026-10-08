"""Render an actual desktop preview; exits automatically without any API requests."""
import ctypes
import tkinter as tk
from pathlib import Path
from PIL import ImageGrab
from app import App

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
root = tk.Tk()
root.geometry('1020x790+80+60')
app = App(root, demo=True)
root.geometry('1020x900+30+30')
root.attributes('-topmost', True)
root.lift()
root.focus_force()

def capture():
    root.update_idletasks()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(Path(__file__).with_name('preview.png'))
    app.float_only()
    assert root.state() == 'iconic'
    assert not app.suggestion.enabled
    app.events.put(('capture', {'text': 'I am agree. i like apples.'}, None))
    app.poll()
    assert root.state() == 'iconic'
    assert app.suggestion.enabled
    # Restore demo content for screenshots, without making an API request.
    app.set_result('I agree with you, but I have some questions about this plan.')
    app.display(app.notes_view, '界面演示，未调用 API：\n• am agree → agree；i → I；some question → some questions。\n\n表达提升 · 可选（不是语法错误）\na few questions 更突出“几个问题”，适合轻松讨论。')
    app.suggestion.refresh()
    app.suggestion.window.geometry('410x510+50+50')
    root.after(300, capture_float)


def capture_float():
    win = app.suggestion.window
    win.update_idletasks()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + win.winfo_width(), y + win.winfo_height())).save(Path(__file__).with_name('floating-preview.png'))
    assert app.suggestion.enabled
    assert root.state() == 'iconic'
    assert app.suggestion.result.get('1.0', 'end-1c') == app.result
    from types import SimpleNamespace
    from desktop_ui import SlimScroll
    assert root.resizable() == (1, 1)
    notes = app.suggestion.notes
    scroll = next(w for w in notes.master.winfo_children() if isinstance(w, SlimScroll))
    assert not scroll.winfo_ismapped(), 'Short content should not display a scrollbar'
    app.display(app.notes_view, '\n'.join('Long suggestion line ' + str(i) for i in range(60)))
    app.suggestion.refresh()
    root.update()
    assert scroll.winfo_ismapped(), 'Overflow should display a slim scrollbar'
    scroll.press(SimpleNamespace(y=40, y_root=100))
    scroll.drag(SimpleNamespace(y_root=150))
    root.update()
    assert notes.yview()[0] > 0, 'Thumb dragging must scroll'
    app.suggestion.start_resize(SimpleNamespace(x_root=100, y_root=100))
    app.suggestion.resize(SimpleNamespace(x_root=300, y_root=250))
    root.update()
    assert (win.winfo_width(), win.winfo_height()) == (610, 660)
    assert app.suggestion.expanded_size == (610, 660)
    app.suggestion.collapse()
    root.update()
    assert win.winfo_height() == 48
    app.suggestion.collapse()
    root.update()
    assert (win.winfo_width(), win.winfo_height()) == (610, 660), 'Collapse must preserve size'
    app.suggestion.collapse()
    assert not app.suggestion.expanded
    app.suggestion.collapse()
    assert app.suggestion.expanded
    # Exercise modified-text invalidation and ensure stale copy is impossible.
    app.set_input('I like apples.')
    assert app.result == ''
    assert str(app.copy_button['state']) == 'disabled'
    app.suggestion.refresh()
    assert str(app.suggestion.copy['state']) == 'disabled'
    app.run_rules()
    app.suggestion.refresh()
    assert app.result == 'I like apples.'
    assert app.suggestion.result.get('1.0', 'end-1c') == 'I like apples.'
    app.disable_floating()
    assert not app.suggestion.enabled
    assert root.state() == 'iconic'
    assert app.suggestion.window.state() == 'withdrawn'
    app.events.put(('capture', {'text': 'I like pears.'}, None))
    app.poll()
    assert app.suggestion.enabled
    assert root.state() == 'iconic'
    assert app.suggestion.result.get('1.0', 'end-1c') == 'I like pears.'
    app.events.put(('capture', None, '捕获失败测试'))
    app.poll()
    assert root.state() == 'iconic'
    assert '捕获失败测试' in app.suggestion.notes.get('1.0', 'end-1c')
    app.show_main()
    root.update()
    assert root.state() == 'normal'
    app.window_close()
    assert root.state() == 'iconic'
    app.close()
    print('Desktop preview saved; GUI invalidation smoke test passed.')

root.after(1000, capture)
root.mainloop()
