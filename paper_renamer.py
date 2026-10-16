#!/usr/bin/env python3
"""Paper PDF Renamer 1.0 — local preview and reversible filesystem changes."""
import hashlib
import html
import json
import os
import queue
import re
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

DOI = re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', re.I)


def clean(value):
    value = html.unescape(re.sub(r'<[^>]*>', '', str(value)))
    value = unicodedata.normalize('NFC', value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    # Stay below common filesystem component limits, including UTF-8 names.
    while len(value.encode('utf-8')) > 180 or len(value) > 160:
        value = value[:-1]
    value = value.rstrip(' .')
    if value.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        value = '_' + value
    return value


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def move_no_replace(source, target):
    """Same-folder hard link + unlink: never overwrite an existing path."""
    os.link(source, target)
    try:
        source.unlink()
    except Exception:
        target.unlink()
        raise


def unique_target(path, stem):
    target = path.with_name(stem + '.pdf')
    i = 2
    while target.exists():
        if target == path:
            return target
        target = path.with_name(f'{stem} ({i}).pdf')
        i += 1
    return target


def fetch(doi):
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
    req = urllib.request.Request(url, headers={'User-Agent': 'PaperPDFRenamer/1.0', 'Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=18) as response:
        m = json.load(response)['message']
    title = html.unescape(re.sub(r'<[^>]*>', '', (m.get('title') or [''])[0]))
    if not title.strip():
        raise ValueError('题录无标题')
    year = ''
    for key in ('published', 'published-print', 'published-online', 'issued'):
        parts = m.get(key, {}).get('date-parts', [[]])
        if parts and parts[0]:
            year = str(parts[0][0]); break
    author = (m.get('author') or [{}])[0].get('family', '')
    return {'title':title, 'year':year, 'author':author}


def identify(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('加密 PDF，无法读取')
    first = reader.pages[0].extract_text() or ''
    # Only first page: reduces accidental recognition of a reference-list DOI.
    metadata = str(reader.metadata or '')
    candidates = list(dict.fromkeys(x.rstrip('.,;:') for x in DOI.findall(first + '\n' + metadata)))
    if len(candidates) > 1:
        raise ValueError('找到多个 DOI，请人工核对；未自动命名')
    if candidates:
        doi = candidates[0]
        try:
            info = fetch(doi)
        except Exception:
            # DOI may end at a typesetting punctuation mark.
            trimmed = doi.rstrip(')')
            if trimmed == doi:
                raise
            info = fetch(trimmed)
            doi = trimmed
        return info, 'DOI：' + doi + '（请核对标题）'
    title = str((reader.metadata or {}).get('/Title', '')).strip()
    if len(title) > 12 and title.lower() not in ('untitled', 'microsoft word') and not re.search(r'\.(docx?|tex)$', title, re.I):
        return {'title':title, 'year':'', 'author':''}, 'PDF 内嵌标题，需核对'
    raise ValueError('未识别 DOI 或有效标题；扫描版/部分 arXiv 需手动填写')


def proposed(info, style):
    keys = {'仅标题':('title',), '年份 - 标题':('year','title'), '作者 - 年份 - 标题':('author','year','title')}[style]
    return clean(' - '.join(info[k] for k in keys if info.get(k)))


from tkinter import ttk
from tkinter.font import Font


class WrappingTreeview(ttk.Treeview):
    """Three-line display, retaining original values for editing and details."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.original_values = {}
        self.text_font = Font(self, font=ttk.Style(self).lookup('Treeview', 'font'))
        self._reflow_job = None
        self.bind('<Configure>', self.schedule_reflow, add='+')
        self.bind('<ButtonRelease-1>', self.schedule_reflow, add='+')

    def wrap_cell(self, value, width):
        text = ' '.join(str(value).split())
        lines = []
        width = max(30, width - 24)
        while text and len(lines) < 3:
            if self.text_font.measure(text) <= width:
                lines.append(text)
                break
            low, high = 1, len(text)
            limit = width - (self.text_font.measure('…') if len(lines) == 2 else 0)
            while low < high:
                mid = (low + high + 1) // 2
                if self.text_font.measure(text[:mid]) <= limit:
                    low = mid
                else:
                    high = mid - 1
            cut = low
            if len(lines) == 2:
                lines.append(text[:cut].rstrip() + '…')
                break
            space = text.rfind(' ', 0, cut + 1)
            if space > cut // 2:
                cut = space
            lines.append(text[:cut].rstrip())
            text = text[cut:].lstrip()
        return '\n'.join(lines)

    def render_values(self, values):
        return tuple(self.wrap_cell(value, int(self.column(key, 'width')))
                     for key, value in zip(self['columns'], values))

    def insert(self, parent, index, iid=None, **kwargs):
        values = tuple(kwargs.get('values', ()))
        kwargs['values'] = self.render_values(values)
        kwargs['text'] = str(len(self.get_children(parent)) + 1)
        result = super().insert(parent, index, iid=iid, **kwargs)
        self.original_values[result] = values
        return result

    def item(self, item, option=None, **kwargs):
        if 'values' in kwargs:
            self.original_values[item] = tuple(kwargs['values'])
            kwargs['values'] = self.render_values(kwargs['values'])
        result = super().item(item, option, **kwargs)
        if not kwargs and item in self.original_values:
            if option == 'values':
                return self.original_values[item]
            if option is None:
                result['values'] = self.original_values[item]
        return result

    def delete(self, *items):
        super().delete(*items)
        for item in items:
            self.original_values.pop(item, None)

    def schedule_reflow(self, event=None):
        if self._reflow_job is not None:
            self.after_cancel(self._reflow_job)
        self._reflow_job = self.after(80, self.reflow)

    def reflow(self):
        self._reflow_job = None
        for iid, values in self.original_values.items():
            super().item(iid, values=self.render_values(values))


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.rows, self.events, self.busy = root, {}, queue.Queue(), False
        self.logs = Path.home() / 'PaperPDFRenamer_Logs'
        root.title('论文重命名')
        root.geometry('1180x760')
        root.minsize(940, 620)
        bg, white, ink, muted, line, accent = '#F5F6F8', '#FFFFFF', '#253044', '#6C7789', '#E3E7ED', '#385F87'
        root.configure(background=bg)
        family = 'Microsoft YaHei UI' if sys.platform == 'win32' else 'PingFang SC'
        theme = ttk.Style(root)
        theme.theme_use('clam')
        theme.configure('.', font=(family, 10), background=bg, foreground=ink)
        theme.configure('TFrame', background=bg)
        theme.configure('Card.TFrame', background=white)
        theme.configure('TLabel', background=bg, foreground=ink)
        theme.configure('Muted.TLabel', foreground=muted)
        theme.configure('Title.TLabel', font=(family, 23, 'bold'))
        theme.configure('Card.TLabel', background=white)
        theme.configure('CardMuted.TLabel', background=white, foreground=muted)
        theme.configure('TButton', background=white, foreground=ink, padding=(15, 9),
                        borderwidth=1, bordercolor=line, lightcolor=white, darkcolor=white)
        theme.map('TButton', background=[('active', '#EDF1F5')],
                  bordercolor=[('active', '#B9C6D5')])
        theme.configure('Primary.TButton', background=accent, foreground=white,
                        bordercolor=accent, lightcolor=accent, darkcolor=accent)
        theme.map('Primary.TButton', background=[('active', '#2D5074')],
                  foreground=[('disabled', '#BCC9D6')])
        theme.configure('Quiet.TButton', background=bg, bordercolor=bg,
                        lightcolor=bg, darkcolor=bg, foreground=muted)
        theme.configure('TCombobox', padding=(9, 7), bordercolor=line,
                        arrowsize=14, fieldbackground=white)
        theme.map('TCombobox', fieldbackground=[('readonly', white)],
                  selectbackground=[('readonly', white)], selectforeground=[('readonly', ink)])
        theme.configure('Treeview', background=white, fieldbackground=white,
                        foreground=ink, rowheight=Font(root, font=(family, 10)).metrics('linespace') * 3 + 22, borderwidth=0, font=(family, 10))
        theme.configure('Treeview.Heading', background='#F0F3F7', foreground=muted,
                        font=(family, 10), padding=(12, 12), relief='flat', borderwidth=0)
        theme.map('Treeview', background=[('selected', '#E5EDF6')], foreground=[('selected', '#244D75')])
        theme.map('Treeview.Heading', background=[('active', '#E8EDF3')])
        for orientation in ('Vertical', 'Horizontal'):
            name = orientation + '.TScrollbar'
            theme.layout(name, [(orientation + '.Scrollbar.trough', {
                'sticky': 'ns' if orientation == 'Vertical' else 'ew',
                'children': [(orientation + '.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]
            })])
            theme.configure(name, background='#BCC8D6', troughcolor='#F1F4F8',
                            bordercolor='#F1F4F8', lightcolor='#BCC8D6', darkcolor='#BCC8D6',
                            borderwidth=0, width=16, arrowsize=16, gripcount=0)
            theme.map(name, background=[('active', '#8FA4BC'), ('pressed', '#708BA9')])

        shell = ttk.Frame(root, padding=(28, 24, 28, 18))
        shell.pack(fill='both', expand=True)
        header = ttk.Frame(shell)
        header.pack(fill='x', pady=(0, 22))
        ttk.Label(header, text='论文重命名', style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='整理文件名，让文献更好找。', style='Muted.TLabel').pack(anchor='w', pady=(7, 0))

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill='x', pady=(0, 18))
        ttk.Button(toolbar, text='添加 PDF', command=self.add_files).pack(side='left')
        ttk.Button(toolbar, text='添加文件夹', command=self.add_folder).pack(side='left', padx=(8, 0))
        ttk.Button(toolbar, text='撤销一次操作', style='Quiet.TButton', command=self.undo).pack(side='left', padx=(8, 0))
        ttk.Button(toolbar, text='清空列表', style='Quiet.TButton', command=self.clear).pack(side='left', padx=(8, 0))
        ttk.Button(toolbar, text='执行重命名', style='Primary.TButton', command=self.apply).pack(side='right')
        ttk.Button(toolbar, text='识别 / 刷新预览', command=self.scan).pack(side='right', padx=(0, 8))

        opts = ttk.Frame(shell)
        opts.pack(fill='x', pady=(0, 16))
        self.style = tk.StringVar(value='年份 - 标题')
        ttk.Label(opts, text='命名格式', style='Muted.TLabel').pack(side='left', padx=(0, 12))
        ttk.Combobox(opts, textvariable=self.style, values=['仅标题','年份 - 标题','作者 - 年份 - 标题'], state='readonly', width=23).pack(side='left')
        self.count = tk.StringVar(value='0 个文件')
        ttk.Label(opts, textvariable=self.count, style='Muted.TLabel').pack(side='right')

        card = tk.Frame(shell, bg=white, highlightbackground=line, highlightthickness=1)
        card.pack(fill='both', expand=True)
        pane = ttk.Frame(card, style='Card.TFrame')
        pane.pack(fill='both', expand=True)
        pane.rowconfigure(0, weight=1)
        pane.columnconfigure(0, weight=1)
        self.tree = WrappingTreeview(pane, columns=('old','new','status'), show='tree headings', selectmode='browse', height=1)
        self.tree.heading('#0', text='编号', anchor='center')
        self.tree.column('#0', width=60, minwidth=60, stretch=False, anchor='center')
        for key, label, width in [('old','原文件名',340),('new','新文件名 · 预览',440),('status','识别结果',260)]:
            self.tree.heading(key, text=label, anchor='w')
            self.tree.column(key, width=width, minwidth=180, anchor='w')
        scroll = ttk.Scrollbar(pane, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(pane, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.bind('<Double-1>', self.edit)
        self.tree.bind('<<TreeviewSelect>>', self.show_details)
        self.empty = ttk.Frame(pane, style='Card.TFrame', padding=24)
        ttk.Label(self.empty, text='将 PDF 拖到这里', style='Card.TLabel', font=(family, 17)).pack()
        ttk.Label(self.empty, text='支持多个文件或文件夹，也可以点击上方按钮添加', style='CardMuted.TLabel').pack(pady=(10, 0))
        self.empty.place(relx=.5, rely=.48, anchor='center')

        detail = ttk.Frame(card, style='Card.TFrame', padding=(16, 12))
        detail.pack(fill='x')
        self.detail_text = tk.StringVar(value='双击列表中的文件可修改新名称；留空则跳过。')
        self.detail_label = ttk.Label(detail, textvariable=self.detail_text, style='CardMuted.TLabel', justify='left', wraplength=1000)
        self.detail_label.pack(fill='x')
        detail.bind('<Configure>', lambda e: self.detail_label.configure(wraplength=max(200, e.width-32)))

        footer = ttk.Frame(shell)
        footer.pack(fill='x', pady=(14, 0))
        self.status = tk.StringVar(value='就绪 · 拖入文件后，点击“识别 / 刷新预览”。')
        status_label = ttk.Label(footer, textvariable=self.status, style='Muted.TLabel', wraplength=780, justify='left')
        status_label.pack(side='left', fill='x', expand=True)
        footer.bind('<Configure>', lambda e: status_label.configure(wraplength=max(200, e.width-180)))
        self.enable_drop()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100,self.poll)
        for arg in sys.argv[1:]: self.add_path(Path(arg))

    def show_details(self, event=None):
        selected = self.tree.selection()
        if not selected:
            self.detail_text.set('双击列表中的文件可修改新名称；留空则跳过。')
            return
        values = self.tree.item(selected[0], 'values')
        self.detail_text.set(f'原名：{values[0]}\n新名：{values[1] or "—"}\n结果：{values[2]}')

    def refresh_list_state(self):
        total = len(self.rows)
        self.count.set(f'{total} 个文件')
        if total:
            self.empty.place_forget()
        else:
            self.empty.place(relx=.5, rely=.48, anchor='center')
        self.show_details()

    def enable_drop(self):
        if not getattr(self.root, '_file_drop_enabled', False):
            self.status.set('拖放不可用：请重新运行 Setup 安装拖放组件；仍可使用添加按钮。')
            return
        from tkinterdnd2 import DND_FILES
        # Register children too, so the list and toolbar both accept files.
        def register(widget):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self.drop_files)
            for child in widget.winfo_children():
                register(child)
        register(self.root)

    def drop_files(self, event):
        from tkinterdnd2 import COPY, REFUSE_DROP
        if not self.available():
            return REFUSE_DROP
        before = len(self.rows)
        errors = []
        try:
            # Tk supplies a Tcl list, not whitespace-separated paths.
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            self.status.set('无法读取拖入的文件路径，请使用添加按钮。')
            return REFUSE_DROP
        for value in paths:
            try:
                self.add_path(Path(value))
            except OSError as exc:
                errors.append(str(exc))
        added = len(self.rows) - before
        message = (f'已添加 {added} 个 PDF，点击“识别 / 刷新预览”继续。' if added
                   else '没有新增 PDF：重复文件和非 PDF 会跳过；文件夹只处理第一层。')
        if errors:
            message += f' 部分路径无法读取：{errors[0][:120]}'
        self.status.set(message)
        # COPY describes the drop action; adding never moves source files.
        return COPY if added else REFUSE_DROP

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo('正在处理','请等当前操作完成后关闭。');return
        self.root.destroy()

    def available(self):
        if self.busy:
            self.status.set('正在处理，请稍候。');return False
        return True

    def add_path(self,path):
        paths=sorted(path.iterdir()) if path.is_dir() else [path]
        for p in paths:
            if p.is_file() and p.suffix.lower()=='.pdf' and not p.is_symlink():
                p=p.resolve()
                if any(r['path']==p for r in self.rows.values()):continue
                iid=self.tree.insert('', 'end',values=(p.name,'','等待识别'))
                self.rows[iid]={'path':p,'name':'','hash':None}
        self.refresh_list_state()

    def add_files(self):
        from tkinter import filedialog
        if self.available():
            for p in filedialog.askopenfilenames(filetypes=[('PDF','*.pdf'),('所有文件','*')]):self.add_path(Path(p))

    def add_folder(self):
        from tkinter import filedialog
        if self.available():
            p=filedialog.askdirectory()
            if p:self.add_path(Path(p))

    def clear(self):
        if self.available():
            for iid in self.rows:self.tree.delete(iid)
            self.rows.clear()
            self.refresh_list_state()

    def edit(self,event):
        if not self.available():return
        iid=self.tree.identify_row(event.y)
        if iid:self.edit_name(iid)

    def edit_name(self, iid):
        import tkinter as tk
        from tkinter import ttk
        r = self.rows[iid]
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title('修改名称')
        dialog.transient(self.root)
        dialog.configure(background='#F5F6F8')
        width = min(820, self.root.winfo_screenwidth() - 80)
        height = min(470, self.root.winfo_screenheight() - 100)
        x = max(0, min(self.root.winfo_rootx() + (self.root.winfo_width()-width)//2,
                       self.root.winfo_screenwidth()-width))
        y = max(0, min(self.root.winfo_rooty() + (self.root.winfo_height()-height)//2,
                       self.root.winfo_screenheight()-height-40))
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        dialog.minsize(min(600, width), min(380, height))
        shell = ttk.Frame(dialog, padding=24)
        shell.pack(fill='both', expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)
        ttk.Label(shell, text='原文件名', style='Muted.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 8))
        original = tk.Text(shell, height=3, wrap='word', relief='flat', borderwidth=0,
                           background='#EDF1F6', foreground='#526277', padx=12, pady=10,
                           font=ttk.Style(dialog).lookup('.', 'font'))
        original.insert('1.0', r['path'].name)
        original.configure(state='disabled')
        original.grid(row=1, column=0, sticky='ew', pady=(0, 18))
        ttk.Label(shell, text='新文件名', style='Muted.TLabel').grid(row=2, column=0, sticky='w', pady=(0, 8))
        input_frame = ttk.Frame(shell)
        input_frame.grid(row=3, column=0, sticky='nsew')
        input_frame.rowconfigure(0, weight=1)
        input_frame.columnconfigure(0, weight=1)
        editor = tk.Text(input_frame, height=4, wrap='word', undo=True, relief='flat',
                         highlightthickness=1, highlightbackground='#D5DEE9',
                         highlightcolor='#385F87', background='white', foreground='#253044',
                         insertbackground='#253044', selectbackground='#DCE8F5',
                         padx=12, pady=12, font=ttk.Style(dialog).lookup('.', 'font'))
        editor.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(input_frame, orient='vertical', command=editor.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        editor.configure(yscrollcommand=scroll.set)
        editor.insert('1.0', r['name'])
        ttk.Label(shell, text='无需填写 .pdf；留空则跳过。换行会自动合并为空格。',
                  style='Muted.TLabel').grid(row=4, column=0, sticky='w', pady=(10, 16))
        buttons = ttk.Frame(shell)
        buttons.grid(row=5, column=0, sticky='ew')
        ttk.Label(buttons, text='Ctrl + Enter 保存 · Esc 取消', style='Muted.TLabel').pack(side='left')

        def cancel(event=None):
            dialog.destroy()
            return 'break'

        def save(event=None):
            value = editor.get('1.0', 'end-1c').strip()
            r['name'] = clean(value[:-4] if value.lower().endswith('.pdf') else value)
            self.tree.item(iid, values=(r['path'].name,
                r['name']+'.pdf' if r['name'] else '', '手动填写' if r['name'] else '跳过'))
            self.show_details()
            return cancel()

        ttk.Button(buttons, text='保存名称', style='Primary.TButton', command=save).pack(side='right')
        ttk.Button(buttons, text='取消', command=cancel).pack(side='right', padx=(0, 8))
        dialog.protocol('WM_DELETE_WINDOW', cancel)
        dialog.bind('<Escape>', cancel)
        dialog.bind('<Control-Return>', save)
        dialog.deiconify()
        dialog.wait_visibility()
        dialog.grab_set()
        editor.focus_set()
        editor.tag_add('sel', '1.0', 'end-1c')
        self.root.wait_window(dialog)

    def scan(self):
        if not self.available():return
        if not self.rows:return
        self.busy=True; style=self.style.get(); items=[(i,dict(r)) for i,r in self.rows.items()]
        self.status.set('正在读取 PDF 并联网查询题录，请稍候……')
        def work():
            for iid,r in items:
                name=''; fingerprint=None
                try:
                    before=digest(r['path'])
                    info,status=identify(r['path']);name=proposed(info,style)
                    fingerprint=digest(r['path'])
                    if fingerprint!=before:raise ValueError('文件处理期间发生变化，请重试')
                except Exception as e:
                    name='';status='跳过：'+str(e)[:150]
                self.events.put(('row',iid,name,status,fingerprint))
            self.events.put(('done','识别完成。请核对预览，再点“执行重命名”。'))
        threading.Thread(target=work,daemon=True).start()

    def apply(self):
        from tkinter import messagebox
        if not self.available():return
        items=[(i,dict(r)) for i,r in self.rows.items() if r['name']]
        if not items:return
        if not messagebox.askyesno('确认预览',f'按预览重命名 {len(items)} 个文件？同名时自动加编号。'):return
        self.busy=True;self.status.set('正在重命名……')
        def work():
            try:
                self.logs.mkdir(parents=True,exist_ok=True)
                log=self.logs/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.jsonl')
                with log.open('x',encoding='utf-8') as out:
                    for iid,r in items:
                        try:
                            src=r['path']; fingerprint=digest(src)
                            if r['hash'] and fingerprint!=r['hash']:raise ValueError('文件已变化，请重新识别')
                            target=unique_target(src,r['name'])
                            if target==src:
                                self.events.put(('applied',iid,str(src),'名称已符合'));continue
                            # Persist intent before modifying filenames, for crash recovery.
                            out.write(json.dumps({'old':str(src),'new':str(target),'sha256':fingerprint},ensure_ascii=False)+'\n')
                            out.flush();os.fsync(out.fileno())
                            move_no_replace(src,target)
                            self.events.put(('applied',iid,str(target),'已重命名'))
                        except Exception as e:self.events.put(('applied',iid,str(r['path']),'失败：'+str(e)[:120]))
                self.events.put(('done','处理完成。日志：'+str(log)))
            except Exception as e:self.events.put(('done','操作失败：'+str(e)))
        threading.Thread(target=work,daemon=True).start()

    def undo(self):
        from tkinter import filedialog, messagebox
        if not self.available():return
        path=filedialog.askopenfilename(title='选择要撤销的日志',initialdir=str(self.logs),filetypes=[('重命名日志','*.jsonl')])
        if not path:return
        try:
            entries=[json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]
        except Exception as e:messagebox.showerror('日志错误',str(e));return
        if not messagebox.askyesno('撤销','恢复该日志记录的文件名？原名已被占用或文件已变化时跳过。'):return
        self.busy=True
        def work():
            ok=0;fail=0
            for e in reversed(entries):
                try:
                    src,target=Path(e['new']),Path(e['old'])
                    if target.exists() or not src.is_file() or src.is_symlink() or digest(src)!=e['sha256']:
                        fail+=1;continue
                    move_no_replace(src,target);ok+=1
                except Exception:fail+=1
            self.events.put(('undo_done',f'撤销完成：恢复 {ok} 个，跳过 {fail} 个。请重新添加文件。'))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event[0]
                if kind=='row':
                    _,iid,name,status,fingerprint=event;r=self.rows[iid];r.update(name=name,hash=fingerprint)
                    self.tree.item(iid,values=(r['path'].name,name+'.pdf' if name else '',status))
                elif kind=='applied':
                    _,iid,path,status=event;r=self.rows[iid];r['path']=Path(path);r['name']=''
                    self.tree.item(iid,values=(r['path'].name,'',status))
                else:
                    self.busy=False;self.status.set(event[1])
                    if kind=='undo_done':self.clear()
        except queue.Empty:pass
        self.show_details()
        self.root.after(100,self.poll)


def create_root():
    import tkinter as tk
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        return tk.Tk()
    # Initialize on an existing root so a failed native load cannot leave
    # an extra, empty window behind.
    class DropRoot(tk.Tk, TkinterDnD.DnDWrapper):
        pass
    root = DropRoot()
    try:
        root.TkdndVersion = TkinterDnD.require(root)
        root._file_drop_enabled = True
    except (RuntimeError, tk.TclError):
        root._file_drop_enabled = False
    return root


if __name__=='__main__':
    root=create_root();App(root);root.mainloop()
