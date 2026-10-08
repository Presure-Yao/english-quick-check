"""English Quick Check: run with Python 3.10+ on Windows. No external packages."""
import argparse
import queue
import sys
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from grammar_core import AIClient, MAX_CHARS, PROVIDERS, SettingsStore, UsageStore, request_limit, apply_rules, check_rules, contains_chinese
from windows_hotkey import Hotkey, parse_shortcut
from windows_tray import TrayIcon
from desktop_ui import build_ui, SuggestionWindow

SAMPLE = 'I am agree with you, but i have some question about this plan.'


class App:
    def __init__(self, root, demo=False):
        self.root = root
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'app.ico'
        if icon.is_file():
            root.iconbitmap(default=str(icon))
        self.demo = demo
        self.store = SettingsStore()
        self.settings = {'provider': 'DeepSeek', 'base_url': PROVIDERS['DeepSeek'][0],
                         'model': PROVIDERS['DeepSeek'][1], 'api_key': '', 'request_limit': 1000,
                         'close_behavior': 'tray', 'chinese_mode': 'translate',
                         'start_in_tray': False, 'auto_ai': False, 'allow_overwrite': False, 'shortcut': 'Ctrl+Alt+G'}
        startup_error = None
        if not demo:
            try:
                self.settings.update(self.store.load())
            except Exception:
                startup_error = '无法读取已保存设置；请重新配置 Key（可能来自另一 Windows 账号）。'
        try:
            self.settings['request_limit'] = request_limit(self.settings.get('request_limit', 1000))
        except ValueError:
            self.settings['request_limit'] = 1000
            startup_error = '保存的调用上限无效，已恢复为 1000。'
        try:
            self.settings['shortcut'] = parse_shortcut(self.settings['shortcut'])[0]
        except (ValueError, AttributeError, TypeError):
            self.settings['shortcut'] = 'Ctrl+Alt+G'
            startup_error = '保存的快捷键无效，已恢复为 Ctrl+Alt+G。'
        self.shortcut_label = tk.StringVar(value=f"快捷键 {self.settings['shortcut']} 捕获当前输入框 · 可在设置中修改")
        self.usage_store = None if demo else UsageStore()
        self.client = AIClient(self.usage_store)
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        self.revision = 0
        self.result_revision = None
        self.result = ''
        for key in ('close_behavior', 'chinese_mode'):
            choices = ('tray', 'exit') if key == 'close_behavior' else ('translate', 'preserve')
            if self.settings.get(key) not in choices:
                self.settings[key] = choices[0]
        self.auto_ai = tk.BooleanVar(value=self.settings.get('auto_ai') is True)
        self.allow_overwrite = tk.BooleanVar(value=self.settings.get('allow_overwrite') is True)
        self.status = tk.StringVar(value='仅在点击 AI 或明确开启快捷键 AI 后上传选区；不读取聊天历史。')
        build_ui(self, SAMPLE)
        self.suggestion = SuggestionWindow(self)
        self.refresh_monthly()
        root.after(60000, self.monthly_tick)
        self.hotkey = None if demo else Hotkey(lambda text, err: self.events.put(('capture', text, err)), self.settings['shortcut'])
        self.tray = None if demo else TrayIcon(icon, lambda action: self.events.put(('tray', action)))
        root.protocol('WM_DELETE_WINDOW', self.window_close)
        root.after(100, self.poll)
        if startup_error:
            self.status.set(startup_error)
        elif self.hotkey and self.hotkey.error:
            self.status.set(self.hotkey.error)
        self.set_input(SAMPLE)
        self.run_rules()
        self.update_capture_policy()
        if self.tray and self.tray.error:
            self.status.set(self.tray.error)
        if not demo and self.settings.get('start_in_tray') is True:
            root.after(150, self.float_only)
        if demo:
            self.set_result('I agree with you, but I have some questions about this plan.')
            self.display(self.notes_view, '界面演示，未调用 API，以下不是实际模型结果：\n• am agree → agree；i → I；some question → some questions。\n\n表达提升 · 可选（不是语法错误）\na few questions 比 some questions 更突出“几个问题”，适合轻松讨论。')
            self.usage_label.configure(text='演示结果 · 未产生 API 费用')
            self.status.set('这是界面演示。正常运行时由你填入 Key；默认快捷键仅执行本地检查。')

    def update_capture_policy(self):
        if self.hotkey:
            self.hotkey.allow_clipboard_overwrite = self.allow_overwrite.get()

    def save_capture_options(self):
        previous = dict(self.settings)
        self.settings.update(auto_ai=self.auto_ai.get(), allow_overwrite=self.allow_overwrite.get())
        try:
            if not self.demo:
                self.store.save(self.settings)
            self.update_capture_policy()
            self.status.set('捕获设置已保存；开启快捷键 AI 会上传原文，覆盖剪贴板可能丢失旧格式。')
        except Exception:
            self.settings = previous
            self.auto_ai.set(previous['auto_ai'])
            self.allow_overwrite.set(previous['allow_overwrite'])
            self.status.set('设置保存失败，已恢复原设置。')

    def tray_available(self):
        return bool(self.tray and not self.tray.error and self.tray.thread.is_alive())

    def toggle_floating(self):
        if self.suggestion.enabled:
            self.disable_floating()
        else:
            self.suggestion.show()
            self.float_toggle.configure(text='关闭悬浮建议')

    def float_only(self):
        if self.tray_available():
            self.root.withdraw()
            self.status.set('已进入托盘；双击图标打开，右键菜单可退出。')
        else:
            self.root.iconify()

    def show_main(self):
        self.root.deiconify()
        self.root.lift()

    def disable_floating(self):
        self.suggestion.enabled = False
        self.suggestion.window.withdraw()
        self.float_toggle.configure(text='悬浮建议')

    def window_close(self):
        if self.demo:
            self.root.iconify()
        elif self.settings['close_behavior'] == 'exit' or not self.tray_available():
            self.close()
        else:
            self.float_only()

    def display(self, widget, text):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget.configure(state='disabled')

    def on_modified(self, _=None):
        if self.input.edit_modified():
            self.input.edit_modified(False)
            self.revision += 1
            self.result = ''
            self.copy_button.configure(state='disabled')
            self.display(self.result_view, '原文已更改，请重新检查。')
            self.display(self.notes_view, '')
            self.display(self.rules_view, '待重新检查。')
            self.usage_label.configure(text='API 用量：当前原文尚未调用')

    def set_input(self, text):
        self.input.delete('1.0', 'end')
        self.input.insert('1.0', text)
        self.on_modified()

    def text(self):
        return self.input.get('1.0', 'end-1c')

    def validate(self):
        text = self.text()
        if not text.strip() or len(text) > MAX_CHARS:
            self.status.set(f'请输入 1–{MAX_CHARS} 个字符。长段落请分段检查。')
            return None
        return text

    def run_rules(self):
        text = self.validate()
        if text is None:
            return
        issues = check_rules(text)
        details = '\n'.join(f'• 字符 {i.start + 1}–{i.end}：{i.message} 建议：{i.replacement}' for i in issues)
        self.display(self.rules_view, details or '未发现基础规则问题。这不意味着语法完全正确，复杂用法请使用 AI 检查。')
        self.set_result(apply_rules(text, issues))
        self.display(self.notes_view, '当前为本地规则候选结果；重复词可能是有意表达，请核对后再复制。\n不进行完整拼写、时态、复杂主谓一致或上下文检测。')
        if contains_chinese(text):
            self.display(self.notes_view, '检测到中文 / 中英混合。本地规则只做基础英文检查，不会翻译。\n点击 AI 检查后，按设置转成完整英文或保留中文。')
        self.status.set('本地检查完成，未上传文本。AI 仅在你主动触发时调用。')

    def set_result(self, text):
        self.result = text
        self.result_revision = self.revision
        self.display(self.result_view, text)
        self.copy_button.configure(state='normal' if text else 'disabled')

    def run_ai(self, mode):
        if self.busy:
            return
        if self.demo:
            self.status.set('演示模式不会调用 API；请正常启动后配置。')
            return
        text = self.validate()
        if text is None:
            return
        self.run_rules()
        if not self.settings.get('api_key'):
            self.open_settings()
            self.status.set('请先保存 API 设置，然后再点击检查。')
            return
        self.busy = True
        self.ai_button.configure(state='disabled')
        self.polish_button.configure(state='disabled')
        revision = self.revision
        settings = dict(self.settings)
        self.status.set('正在请求 AI；只上传当前原文，不附带聊天记录。最多等待约 35 秒。')
        def worker():
            try:
                self.events.put(('ai', revision, self.client.check(text, settings, mode), mode, None))
            except Exception as exc:
                self.events.put(('ai', revision, None, mode, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def monthly_tick(self):
        if not self.closed:
            self.refresh_monthly()
            self.root.after(60000, self.monthly_tick)

    def refresh_monthly(self):
        if self.usage_store is None:
            return
        month, row, error = self.usage_store.summary()
        text = (f"本月 {month} 累计 token：输入 {row['input']:,} / 输出 {row['output']:,} / 总计 {row['total']:,}")
        if row['unreported']:
            text += f"（{row['unreported']} 次用量未完整返回）"
        self.monthly_label.configure(text=error or text)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'capture':
                    _, text, err = event
                    self.suggestion.show()
                    self.float_toggle.configure(text='关闭悬浮建议')
                    if err:
                        self.status.set(err)
                        # Report in the card; a modal attached to the main window
                        # would bring the background UI back unexpectedly.
                        self.set_result('')
                        self.display(self.notes_view, '未读取到输入框内容：' + err)
                    elif text:
                        self.set_input(text['text'])
                        self.run_rules()
                        if self.auto_ai.get():
                            self.run_ai('grammar')
                elif event[0] == 'tray':
                    if event[1] == 'exit':
                        self.close()
                        if self.closed:
                            return
                    elif event[1] == 'open':
                        self.show_main()
                    elif event[1] == 'error':
                        self.tray.error = '托盘恢复失败；关闭主窗口将退出。'
                        self.show_main()
                        self.status.set(self.tray.error)
                else:
                    _, revision, result, mode, err = event
                    self.refresh_monthly()
                    self.busy = False
                    self.ai_button.configure(state='normal')
                    self.polish_button.configure(state='normal')
                    if revision != self.revision:
                        self.status.set('原文已改变，已丢弃旧 AI 结果；该请求仍可能计费。请重新检查。')
                        continue
                    if err:
                        self.status.set(err)
                        continue
                    self.set_result(result['corrected'])
                    label = ('中文 / 中英混合 → 完整英文（请核对原意）' if result.get('translated') else
                             '可选的自然表达建议' if mode == 'polish' else 'AI 语法检查（可能误判，请核对）')
                    notes = label + '\n' + ('\n'.join('• ' + n for n in result['notes']) or '未发现需要说明的修改。')
                    if result.get('expression_tip'):
                        notes += '\n\n表达提升 · 可选（不是语法错误）\n' + result['expression_tip']
                    self.display(self.notes_view, notes)
                    usage = result['usage']
                    self.usage_label.configure(text=('缓存命中 · 本次不调用 API' if result['cached'] else
                        f"实际 token：输入 {usage.get('prompt_tokens', '未提供')} / 输出 {usage.get('completion_tokens', '未提供')} / 总计 {usage.get('total_tokens', '未提供')}"))
                    self.status.set(f"检查完成。本次已请求 AI {self.client.calls} 次（软件保护上限：{self.settings['request_limit']} 次）；费用以服务商账单为准。")
        except queue.Empty:
            pass
        self.suggestion.refresh()
        self.root.after(100, self.poll)

    def copy_result(self):
        if not self.result or self.result_revision != self.revision:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.result)
        self.status.set('已复制建议，将覆盖当前剪贴板；请自行粘贴，不会自动发送。')

    def apply_settings(self, settings):
        previous = self.settings['shortcut']
        changed = False
        try:
            if self.hotkey:
                self.hotkey.change(settings['shortcut'])
                changed = settings['shortcut'] != previous
            if not self.demo:
                self.store.save(settings)
        except Exception:
            if changed:
                try:
                    self.hotkey.change(previous)
                except Exception as rollback_error:
                    self.status.set(f'设置保存失败，快捷键恢复也失败：{rollback_error}；请重启软件。')
                    raise RuntimeError('设置保存失败，无法恢复旧快捷键；请重启软件。') from rollback_error
            raise
        self.settings = settings
        self.shortcut_label.set(f"快捷键 {settings['shortcut']} 捕获当前输入框 · 可在设置中修改")

    def open_settings(self):
        dialog = tk.Toplevel(self.root)
        self.show_main()
        dialog.title('设置 · English Quick Check')
        dialog.geometry('690x590')
        dialog.minsize(650, 570)
        dialog.transient(self.root)
        dialog.grab_set()
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill='both', expand=True, padx=16, pady=16)
        general = ttk.Frame(notebook, padding=18)
        checking = ttk.Frame(notebook, padding=18)
        frame = ttk.Frame(notebook, padding=18)
        notebook.add(general, text='常规')
        notebook.add(checking, text='检查与捕获')
        notebook.add(frame, text='API 与用量')
        shortcut = tk.StringVar(value=self.settings['shortcut'])
        ttk.Label(general, text='全局捕获快捷键（保存后立即生效）').pack(anchor='w')
        ttk.Entry(general, textvariable=shortcut).pack(fill='x', pady=8)
        ttk.Label(general, text='例如 Ctrl+Alt+G、Ctrl+Shift+E、Alt+F8；至少包含 Ctrl 或 Alt。\n支持字母、数字、F1–F24；占用时保留原快捷键。').pack(anchor='w', pady=(0, 12))
        close_behavior = tk.StringVar(value=self.settings['close_behavior'])
        chinese_mode = tk.StringVar(value=self.settings['chinese_mode'])
        start_in_tray = tk.BooleanVar(value=self.settings.get('start_in_tray') is True)
        auto_ai = tk.BooleanVar(value=self.auto_ai.get())
        overwrite = tk.BooleanVar(value=self.allow_overwrite.get())
        ttk.Label(general, text='关闭主窗口时（也适用于任务栏“关闭窗口”）').pack(anchor='w', pady=(0, 10))
        ttk.Radiobutton(general, text='最小化到系统托盘，继续运行', variable=close_behavior, value='tray').pack(anchor='w', pady=5)
        ttk.Radiobutton(general, text='直接退出软件', variable=close_behavior, value='exit').pack(anchor='w', pady=5)
        ttk.Checkbutton(general, text='下次启动直接进入托盘（不显示主窗口）', variable=start_in_tray).pack(anchor='w', pady=20)
        ttk.Label(general, text='托盘图标可能在任务栏右侧“^”隐藏图标中。\n双击打开主窗口；右键 → 退出始终彻底关闭。\n“后台运行”进入托盘；普通最小化仍保留任务栏入口。\n托盘不可用时，关闭主窗口将直接退出，避免无法关闭。', wraplength=600).pack(anchor='w', pady=10)
        ttk.Label(checking, text='AI 遇到中文 / 中英混合内容时').pack(anchor='w', pady=(0, 10))
        ttk.Radiobutton(checking, text='转为完整英文（保留原意，并提供中文解释）', variable=chinese_mode, value='translate').pack(anchor='w', pady=5)
        ttk.Radiobutton(checking, text='保留中文，只检查英文部分', variable=chinese_mode, value='preserve').pack(anchor='w', pady=5)
        ttk.Checkbutton(checking, text='快捷键捕获后调用 AI（会上传整段原文）', variable=auto_ai).pack(anchor='w', pady=(25, 8))
        ttk.Checkbutton(checking, text='允许覆盖富文本 / 图片剪贴板（原格式会丢失）', variable=overwrite).pack(anchor='w', pady=8)
        ttk.Label(checking, text='默认不上传、不覆盖富文本剪贴板；主动开启后会保存此选择。\n中文转英文只在 AI 请求中生效，本地规则不会翻译。\n快捷键可在“常规”中修改；不自动替换、不发送消息。', wraplength=600).pack(anchor='w', pady=20)
        variables = {key: tk.StringVar(value=self.settings.get(key, '')) for key in ('provider', 'base_url', 'model', 'api_key', 'request_limit')}
        for key, label in [('provider', '服务商'), ('base_url', 'API Base URL（HTTPS）'), ('model', '非推理模型'), ('api_key', 'API Key'), ('request_limit', '每次运行 AI 请求上限（1–100000 次，非 token）')]:
            ttk.Label(frame, text=label).pack(anchor='w', pady=(8, 3))
            if key == 'provider':
                field = ttk.Combobox(frame, values=list(PROVIDERS), textvariable=variables[key], state='readonly')
                def provider_changed(_):
                    base, model = PROVIDERS[variables['provider'].get()]
                    variables['base_url'].set(base)
                    variables['model'].set(model)
                    variables['api_key'].set('')
                field.bind('<<ComboboxSelected>>', provider_changed)
            else:
                field = ttk.Entry(frame, textvariable=variables[key], show='•' if key == 'api_key' else '')
            field.pack(fill='x')
        ttk.Label(frame, text='仅上传主动检查的原文。兼容接口仍可能存在模型差异。\nKey 加密保存，不保存原文；不显示费用估算，避免使用过期报价。', wraplength=580).pack(anchor='w', pady=12)
        def save():
            from grammar_core import endpoint
            settings = {**self.settings, **{k: v.get().strip() for k, v in variables.items()}}
            settings.update(close_behavior=close_behavior.get(), chinese_mode=chinese_mode.get(),
                            start_in_tray=start_in_tray.get(), auto_ai=auto_ai.get(), allow_overwrite=overwrite.get())
            try:
                if settings['api_key'] or settings['base_url']:
                    endpoint(settings['base_url'])
                settings['request_limit'] = request_limit(settings['request_limit'])
                if not settings['model']:
                    raise ValueError('模型不能为空。')
                settings['shortcut'] = parse_shortcut(shortcut.get())[0]
                self.apply_settings(settings)
                self.auto_ai.set(settings['auto_ai'])
                self.allow_overwrite.set(settings['allow_overwrite'])
                self.update_capture_policy()
                with self.client.lock:
                    self.client.cache.clear()
                dialog.destroy()
                self.status.set('设置已保存。AI 仅在点击检查或明确开启快捷键 AI 后调用。')
            except Exception as exc:
                messagebox.showerror('设置未保存', str(exc), parent=dialog)
        ttk.Button(dialog, text='保存全部设置', command=save, style='Primary.TButton').pack(anchor='e', padx=16, pady=(0, 14))

    def close(self):
        if self.busy:
            self.show_main()
            if not messagebox.askyesno('退出', 'API 请求正在进行，退出不保证取消服务商计费。仍要退出吗？', parent=self.root):
                return
        self.closed = True
        if self.hotkey:
            self.hotkey.close()
        if self.tray:
            self.tray.close()
            self.tray.thread.join(timeout=2)
        # Cancel scheduled callbacks before destroying Tcl commands (also important
        # when multiple app instances are created sequentially by GUI tests).
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Preview only: no hotkey, saved settings, or network access')
    parser.add_argument('--smoke-test', metavar='REPORT', help='Offline packaged GUI self-test; write a JSON report and exit')
    args = parser.parse_args()
    root = tk.Tk()
    app = App(root, demo=args.demo or bool(args.smoke_test))
    if args.smoke_test:
        def smoke_test():
            import json
            report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'network_requests': 0}
            try:
                app.set_input('I am agree with you.')
                app.run_rules()
                assert app.result == 'I agree with you.', app.result
                app.suggestion.show()
                root.update_idletasks()
                assert app.suggestion.window.winfo_viewable()
                app.disable_floating()
                app.suggestion.show()
                root.update_idletasks()
                assert app.suggestion.window.winfo_viewable()
                icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'app.ico'
                app.tray = TrayIcon(icon, lambda action: app.events.put(('tray', action)))
                assert not app.tray.error, app.tray.error
                assert app.tray_available()
                app.float_only()
                assert root.state() == 'withdrawn'
                app.events.put(('tray', 'open'))
                app.poll()
                root.update_idletasks()
                assert root.state() == 'normal'
                report['tray'] = True
                report['ok'] = True
            except Exception as exc:
                report['error'] = str(exc)
            finally:
                Path(args.smoke_test).write_text(json.dumps(report, indent=2), encoding='utf-8')
                app.close()
        root.after(500, smoke_test)
    root.mainloop()
