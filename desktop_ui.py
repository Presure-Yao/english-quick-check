"""Lightweight Tkinter presentation; no additional runtime dependencies."""
import tkinter as tk
from tkinter import ttk

BG = '#f6f5f0'
INK = '#233b35'
MUTED = '#77847c'
BLUE = '#246854'


def label(parent, text='', **kwargs):
    return tk.Label(parent, text=text, bg=kwargs.pop('bg', parent.cget('bg')), fg=kwargs.pop('fg', INK),
                    font=kwargs.pop('font', ('Microsoft YaHei UI', 10)), **kwargs)


class SoftButton(tk.Canvas):
    """Rounded, keyboard-accessible button preserving configure(state/text) API."""
    def __init__(self, parent, text, command, primary=False, state='normal'):
        self.caption, self.command, self.primary, self.state = text, command, primary, state
        self.hover = False
        super().__init__(parent, bg=parent.cget('bg'), height=36, highlightthickness=0, bd=0, takefocus=1)
        self.bind('<Configure>', lambda _: self.paint())
        self.bind('<Enter>', lambda _: self.highlight(True))
        self.bind('<Leave>', lambda _: self.highlight(False))
        self.bind('<ButtonRelease-1>', self.activate)
        self.bind('<Return>', self.activate)
        self.bind('<space>', self.activate)
        self.bind('<FocusIn>', lambda _: self.paint())
        self.bind('<FocusOut>', lambda _: self.paint())
        self.paint()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        for key in ('text', 'state'):
            if key in kwargs:
                setattr(self, 'caption' if key == 'text' else 'state', kwargs.pop(key))
        super().configure(**kwargs)
        self.paint()

    config = configure

    def __getitem__(self, key):
        return self.state if key == 'state' else super().__getitem__(key)

    def highlight(self, value):
        self.hover = value
        self.paint()

    def activate(self, event=None):
        if self.state != 'disabled':
            self.command()

    def paint(self):
        from tkinter import font
        f = font.Font(family='Microsoft YaHei UI', size=9)
        width = f.measure(self.caption) + 32
        super().configure(width=width, cursor='arrow' if self.state == 'disabled' else 'hand2')
        self.delete('all')
        fill = (BLUE if not self.hover else '#1b5141') if self.primary else ('#ffffff' if not self.hover else '#e7eee8')
        fg = 'white' if self.primary else INK
        if self.state == 'disabled':
            fill, fg = '#e7ebe5', '#9ca69d'
        border = BLUE if self.focus_get() == self else fill
        self.create_polygon(10, 1, width-10, 1, width-1, 10, width-1, 26, width-10, 35,
                            10, 35, 1, 26, 1, 10, smooth=True, splinesteps=24, fill=fill, outline=border)
        self.create_text(width/2, 18, text=self.caption, fill=fg, font=('Microsoft YaHei UI', 9))


def button(parent, text, command, primary=False, **kwargs):
    return SoftButton(parent, text, command, primary, **kwargs)


class SlimScroll(tk.Canvas):
    """Arrowless scroll thumb; overlays a reserved margin only on overflow."""
    def __init__(self, parent, text):
        super().__init__(parent, width=9, bg=text.cget('bg'), bd=0, highlightthickness=0, cursor='hand2')
        self.text = text
        self.first, self.last = 0.0, 1.0
        self.anchor = None
        text.configure(yscrollcommand=self.set)
        self.bind('<Configure>', lambda _: self.paint())
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.drag)
        self.bind('<MouseWheel>', lambda e: text.yview_scroll(-int(e.delta / 120), 'units'))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        if self.first <= 0.0001 and self.last >= 0.9999:
            self.place_forget()
        else:
            self.place(relx=1, x=-10, y=3, relheight=1, height=-6, width=9)
        self.paint()

    def thumb(self):
        height = max(1, self.winfo_height())
        size = min(height, max(22, (self.last - self.first) * height))
        top = self.first / max(0.0001, 1 - (self.last - self.first)) * (height - size)
        return height, size, top

    def paint(self):
        self.delete('all')
        _, size, top = self.thumb()
        self.create_line(4, top + 3, 4, top + size - 3, fill='#b8c8bc', width=5, capstyle='round')

    def press(self, event):
        height, size, top = self.thumb()
        if not top <= event.y <= top + size:
            fraction = max(0, min(1, (event.y - size / 2) / max(1, height - size)))
            self.text.yview_moveto(fraction * (1 - (self.last - self.first)))
        self.anchor = (event.y_root, self.first)

    def drag(self, event):
        if self.anchor is None:
            return
        height, size, _ = self.thumb()
        y, first = self.anchor
        self.text.yview_moveto(first + (event.y_root - y) / max(1, height - size) * (1 - (self.last - self.first)))


def card(parent, title, subtitle, height=4, editable=False):
    frame = tk.Frame(parent, bg='white', highlightbackground='#e4e7df', highlightthickness=1)
    header = tk.Frame(frame, bg='white')
    header.pack(fill='x', padx=16, pady=(12, 2))
    label(header, title, font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
    label(header, subtitle, fg=MUTED, font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(3, 0))
    holder = tk.Frame(frame, bg='white')
    holder.pack(fill='both', expand=True, padx=12, pady=(4, 12))
    widget = tk.Text(holder, width=1, height=height, bg='white', fg=INK, insertbackground=BLUE,
                     relief='flat', wrap='word', font=('Microsoft YaHei UI', 11),
                     padx=4, pady=4, undo=editable, spacing1=3, spacing3=3,
                     state='normal' if editable else 'disabled')
    widget.pack(side='left', fill='both', expand=True, padx=(0, 12))
    SlimScroll(holder, widget)
    return frame, widget


def build_ui(app, sample):
    root = app.root
    root.title('English Quick Check · 英文写作助手')
    root.geometry('1060x850')
    root.minsize(880, 720)
    root.resizable(True, True)
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TButton', background='white', foreground=INK, borderwidth=1,
                    font=('Microsoft YaHei UI', 10), padding=(12, 8))
    style.map('TButton', background=[('active', '#e7eee8')], foreground=[('disabled', '#a5b1c1')])
    style.configure('Primary.TButton', background=BLUE, foreground='white', borderwidth=0)
    style.map('Primary.TButton', background=[('active', '#1b5141'), ('disabled', '#b8c9bf')],
              foreground=[('disabled', '#f1f5fb')])
    style.configure('TCheckbutton', background=BG, foreground=MUTED, font=('Microsoft YaHei UI', 9))
    style.configure('Vertical.TScrollbar', background='#dce4d8', troughcolor='#f7f8f3', borderwidth=0, arrowsize=10)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=INK, font=('Microsoft YaHei UI', 10))
    main = tk.Frame(root, bg=BG)
    main.pack(fill='both', expand=True, padx=24, pady=16)
    head = tk.Frame(main, bg=BG)
    head.pack(fill='x', pady=(0, 12))
    mark = tk.Label(head, text='Aa.', bg=BG, fg=BLUE, font=('Georgia', 28, 'bold'), padx=2, pady=6)
    mark.pack(side='left', padx=(0, 12))
    titles = tk.Frame(head, bg=BG)
    titles.pack(side='left')
    label(titles, 'English Quick Check', font=('Georgia', 22)).pack(anchor='w')
    label(titles, '写得更准确，也学会为什么。', fg=MUTED).pack(anchor='w', pady=(2, 0))
    button(head, '退出软件', app.close).pack(side='right', padx=(8, 0))
    button(head, '设置', app.open_settings).pack(side='right')
    app.float_toggle = button(head, '悬浮建议', app.toggle_floating)
    app.float_toggle.pack(side='right', padx=8)
    intro = tk.Frame(main, bg='#edf1e8')
    intro.pack(fill='x', pady=(0, 12))
    label(intro, '', textvariable=app.shortcut_label, bg='#edf1e8', fg=BLUE, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=12, pady=10)
    label(intro, '在聊天输入框触发 · 自动读取整框 · 不替换、不发送', bg='#edf1e8', fg='#637869').pack(side='left')
    frame, app.input = card(main, '待检查的文字', '支持英文 / 中英混合；中文转英文需要 AI。', 3, True)
    frame.pack(fill='x')
    app.input.bind('<<Modified>>', app.on_modified)
    actions = tk.Frame(main, bg=BG)
    actions.pack(fill='x', pady=10)
    app.ai_button = button(actions, 'AI 语法检查', lambda: app.run_ai('grammar'), True)
    app.ai_button.pack(side='left')
    button(actions, '本地基础检查', app.run_rules).pack(side='left', padx=8)
    app.polish_button = button(actions, '自然表达', lambda: app.run_ai('polish'))
    app.polish_button.pack(side='left')
    button(actions, '填入示例', lambda: app.set_input(sample)).pack(side='right')
    ttk.Checkbutton(main, text='快捷键捕获后调用 AI（将原文发送至所选服务商）', variable=app.auto_ai, command=app.save_capture_options).pack(anchor='w')
    ttk.Checkbutton(main, text='允许覆盖富文本 / 图片剪贴板（这些原格式将丢失）', variable=app.allow_overwrite,
                    command=app.save_capture_options).pack(anchor='w', pady=(3, 10))
    grid = tk.Frame(main, bg=BG)
    grid.pack(fill='both', expand=True)
    grid.columnconfigure(0, weight=1, uniform='col')
    grid.columnconfigure(1, weight=1, uniform='col')
    grid.rowconfigure(0, weight=1)
    grid.rowconfigure(1, weight=1)
    frame, app.rules_view = card(grid, '基础检查', '离线 · 零 token · 不代表完整语法检测', 3)
    frame.grid(row=0, column=0, sticky='nsew', padx=(0, 6), pady=(0, 10))
    frame, app.result_view = card(grid, '参考修正版', '先理解解释，再尝试自己修改。', 3)
    frame.grid(row=0, column=1, sticky='nsew', padx=(6, 0), pady=(0, 10))
    frame, app.notes_view = card(grid, '理解修改 · 学会表达', '简短语法解释 + 最多一条可选的用词建议。', 4)
    frame.grid(row=1, column=0, columnspan=2, sticky='nsew')
    footer = tk.Frame(main, bg=BG)
    footer.pack(fill='x', pady=(10, 0))
    app.copy_button = button(footer, '复制建议', app.copy_result, state='disabled')
    app.copy_button.pack(side='right')
    button(footer, '后台运行', app.float_only).pack(side='right', padx=8)
    button(footer, '退出', app.close).pack(side='right')
    app.usage_label = label(footer, 'API 用量：尚未调用', fg=MUTED, font=('Microsoft YaHei UI', 9))
    app.usage_label.pack(anchor='w')
    app.monthly_label = label(footer, '月度用量：演示模式不读取真实统计', fg=MUTED, font=('Microsoft YaHei UI', 9))
    app.monthly_label.pack(anchor='w', pady=(4, 0))
    app.status_label = label(main, textvariable=app.status, fg=MUTED, font=('Microsoft YaHei UI', 9), anchor='w', justify='left', wraplength=1000)
    app.status_label.pack(fill='x', pady=(10, 0))
    root.bind('<Configure>', lambda event: app.status_label.configure(wraplength=max(400, root.winfo_width() - 55)) if event.widget is root else None)


class SuggestionWindow:
    """Persistent result-only, borderless topmost card; never captures chat contents itself."""
    def __init__(self, app):
        self.app = app
        self.enabled = False
        self.expanded = True
        self.drag = None
        self.resize_anchor = None
        self.expanded_size = (410, 510)
        win = self.window = tk.Toplevel(app.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        width, height = 410, 510
        x = max(0, win.winfo_screenwidth() - width - 35)
        y = max(0, (win.winfo_screenheight() - height) // 2)
        win.geometry(f'{width}x{height}+{x}+{y}')
        win.configure(bg='#d2dcd1')
        shell = tk.Frame(win, bg='white')
        shell.pack(fill='both', expand=True, padx=1, pady=1)
        head = tk.Frame(shell, bg='#eef2e9', cursor='fleur')
        head.pack(fill='x')
        title = label(head, 'Aa.   写作建议', bg='#eef2e9', fg=INK, font=('Microsoft YaHei UI', 11, 'bold'), cursor='fleur')
        title.pack(side='left', padx=12, pady=12)
        for w in (head, title):
            w.bind('<ButtonPress-1>', self.start_drag)
            w.bind('<B1-Motion>', self.move)
        self.close_button = tk.Button(head, text='×', command=app.disable_floating, bg='#eef2e9', fg=INK,
                                      activebackground='#f1dada', activeforeground=INK, cursor='hand2',
                                      relief='flat', font=('Segoe UI', 13), bd=0, padx=10)
        self.close_button.pack(side='right')
        self.collapse_button = tk.Button(head, text='−', command=self.collapse, bg='#eef2e9', fg=INK,
                                         activebackground='#dbe7d6', activeforeground=INK, cursor='hand2',
                                         relief='flat', font=('Segoe UI', 13), bd=0, padx=10)
        self.collapse_button.pack(side='right')
        for control, hover in ((self.close_button, '#f1dada'), (self.collapse_button, '#dbe7d6')):
            control.bind('<Enter>', lambda event, color=hover: event.widget.configure(bg=color))
            control.bind('<Leave>', lambda event: event.widget.configure(bg='#eef2e9'))
        self.body = tk.Frame(shell, bg='white')
        self.body.pack(fill='both', expand=True, padx=14, pady=12)
        label(self.body, '参考修正版', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w')
        self.result = self.text(self.body, 3, ('Microsoft YaHei UI', 11))
        label(self.body, '语法解释 & 表达提升', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w', pady=(10, 0))
        self.notes = self.text(self.body, 4, ('Microsoft YaHei UI', 10))
        self.status = label(self.body, fg=MUTED, wraplength=375, justify='left', font=('Microsoft YaHei UI', 9))
        self.status.pack(fill='x', pady=8)
        bar = tk.Frame(self.body, bg='white')
        bar.pack(fill='x')
        self.copy = button(bar, '复制建议', app.copy_result, state='disabled')
        self.copy.pack(side='left')
        button(bar, '完整窗口', app.show_main).pack(side='right')
        button(bar, '退出', app.close).pack(side='right', padx=5)
        self.grip = tk.Label(shell, text='◢', bg='white', fg='#9aaa9e', cursor='size_nw_se', font=('Segoe UI', 10))
        self.grip.place(relx=1, rely=1, anchor='se')
        self.grip.bind('<ButtonPress-1>', self.start_resize)
        self.grip.bind('<B1-Motion>', self.resize)
        win.bind('<Configure>', self.on_size)
        self.refresh()

    def on_size(self, event):
        if event.widget is self.window:
            self.status.configure(wraplength=max(200, event.width - 32))
            if self.expanded and event.height >= 400:
                self.expanded_size = (event.width, event.height)

    def start_resize(self, event):
        if self.expanded:
            self.resize_anchor = (event.x_root, event.y_root, self.window.winfo_width(), self.window.winfo_height())

    def resize(self, event):
        if not self.expanded or self.resize_anchor is None:
            return
        x, y, width, height = self.resize_anchor
        width = max(380, width + event.x_root - x)
        height = max(400, height + event.y_root - y)
        self.window.geometry(f'{width}x{height}')

    def text(self, parent, height, font, expand=True):
        holder = tk.Frame(parent, bg='#f7f8f3')
        holder.pack(fill='both', expand=expand, pady=(5, 0))
        text = tk.Text(holder, width=1, wrap='word', height=height, font=font, fg=INK, bg='#f7f8f3', relief='flat',
                       padx=9, pady=7, state='disabled')
        text.pack(fill='both', expand=True, padx=(0, 12))
        SlimScroll(holder, text)
        return text

    def start_drag(self, event):
        self.drag = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())

    def move(self, event):
        if not self.drag:
            return
        sx, sy, x, y = self.drag
        x = max(0, min(self.window.winfo_screenwidth() - 80, x + event.x_root - sx))
        y = max(0, min(self.window.winfo_screenheight() - 40, y + event.y_root - sy))
        self.window.geometry(f'+{x}+{y}')

    def collapse(self):
        if self.expanded:
            self.expanded_size = (self.window.winfo_width(), self.window.winfo_height())
            self.expanded = False
            self.body.pack_forget()
            self.grip.place_forget()
            self.window.geometry(f'{self.expanded_size[0]}x48')
        else:
            self.expanded = True
            self.body.pack(fill='both', expand=True, padx=14, pady=12)
            self.grip.place(relx=1, rely=1, anchor='se')
            width, height = self.expanded_size
            self.window.geometry(f'{width}x{height}')

    def show(self):
        if not self.expanded:
            self.collapse()
        self.enabled = True
        self.window.deiconify()
        self.window.lift()
        self.refresh()

    def refresh(self):
        if not self.enabled:
            return
        for target, source in ((self.result, self.app.result_view), (self.notes, self.app.notes_view)):
            value = source.get('1.0', 'end-1c')
            if target.get('1.0', 'end-1c') != value:
                target.configure(state='normal')
                target.delete('1.0', 'end')
                target.insert('1.0', value)
                target.configure(state='disabled')
        self.copy.configure(state='normal' if self.app.result and self.app.result_revision == self.app.revision else 'disabled')
        self.status.configure(text=self.app.status.get())
