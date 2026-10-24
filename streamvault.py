"""StreamVault rebuild. Python stdlib only; external media tools stay isolated."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import zipfile
from datetime import datetime, timedelta, timezone
import time
import youtube_monitor
import secure_token

DATA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'StreamVault-Rebuilt'
TOOLS = DATA / 'tools'
ORIGINAL = Path(os.environ.get('APPDATA', '')) / 'com.streamvault.app' / 'tools'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

def run(args, timeout=30):
    return subprocess.run([str(x) for x in args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout, creationflags=FLAGS)

def version(path):
    result = run([path, '--version' if path.name == 'yt-dlp.exe' else '-version'])
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:] or 'Tool failed its version check')
    return result.stdout.splitlines()[0]

def fetch(url, target):
    request = Request(url, headers={'User-Agent': 'StreamVault-Rebuilt/1.0'})
    with urlopen(request, timeout=60) as response, open(target, 'wb') as output:
        shutil.copyfileobj(response, output)

def install_files(files):
    """Validate every candidate, back up the previous set, roll back on failure."""
    for name, source in files.items():
        version(source)
    backups, installed = {}, []
    try:
        for name, source in files.items():
            dest = TOOLS / name
            backup = TOOLS / (name + '.previous')
            if dest.exists():
                shutil.copy2(dest, backup)
                backups[name] = backup
            staged = TOOLS / (name + '.new')
            shutil.copy2(source, staged)
            os.replace(staged, dest)
            installed.append(name)
    except Exception:
        for name in installed:
            if name in backups:
                shutil.copy2(backups[name], TOOLS / name)
            else:
                (TOOLS / name).unlink(missing_ok=True)
        raise
    manifest = {p.name: {'version': version(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in TOOLS.glob('*.exe')}
    staged = DATA / 'dependencies.json.new'
    staged.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    os.replace(staged, DATA / 'dependencies.json')

def update_tool(name, log):
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        folder = Path(temp)
        if name == 'yt-dlp':
            base = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/'
            log('Downloading yt-dlp and release checksums…')
            fetch(base + 'yt-dlp.exe', folder / 'yt-dlp.exe')
            fetch(base + 'SHA2-256SUMS', folder / 'checksums')
            entries = (folder / 'checksums').read_text().splitlines()
            expected = next(line.split()[0] for line in entries if line.split()[-1].lstrip('*') == 'yt-dlp.exe')
            if hashlib.sha256((folder / 'yt-dlp.exe').read_bytes()).hexdigest() != expected:
                raise RuntimeError('yt-dlp checksum mismatch; existing tool preserved')
            install_files({'yt-dlp.exe': folder / 'yt-dlp.exe'})
        else:
            base = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
            log('Downloading FFmpeg essentials (this may take a few minutes)…')
            fetch(base, folder / 'ffmpeg.zip')
            fetch(base + '.sha256', folder / 'checksum')
            expected = re.search(r'\b[0-9a-fA-F]{64}\b', (folder / 'checksum').read_text()).group().lower()
            if hashlib.sha256((folder / 'ffmpeg.zip').read_bytes()).hexdigest() != expected:
                raise RuntimeError('FFmpeg checksum mismatch; existing tools preserved')
            files = {}
            with zipfile.ZipFile(folder / 'ffmpeg.zip') as archive:
                for name in ('ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe'):
                    member = next(n for n in archive.namelist() if n.endswith('/bin/' + name))
                    with archive.open(member) as source, open(folder / name, 'wb') as dest:
                        shutil.copyfileobj(source, dest)
                    files[name] = folder / name
            install_files(files)
        log('Update complete. Previous binaries retained as .previous files.')

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('StreamVault • Rebuilt')
        self.geometry('1020x800')
        self.minsize(800, 680)
        self.configure(bg='#0b1120')
        TOOLS.mkdir(parents=True, exist_ok=True)
        self.events = queue.Queue()
        self.busy = False
        self.process = None
        self.cancelled = threading.Event()
        self.media_url = None
        self.formats = ['bv*+ba/b']
        self.settings = DATA / 'settings.json'
        try:
            settings = json.loads(self.settings.read_text())
        except (OSError, ValueError):
            settings = {}
        self.saved_settings = settings
        self.monitor_stop = threading.Event()
        self.monitor_seen = set(settings.get('monitor_seen', []))
        self.monitor_pending = set()
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#111b30', foreground='#edf3ff', font=('Segoe UI', 10))
        style.configure('TFrame', background='#0b1120')
        style.configure('TLabel', background='#0b1120')
        style.configure('TButton', padding=(12, 9))
        style.configure('TEntry', fieldbackground='#16223a', foreground='#ffffff', padding=8)
        style.configure('TCombobox', fieldbackground='#16223a', foreground='#ffffff', padding=7)
        style.map('TCombobox', fieldbackground=[('readonly', '#16223a')], foreground=[('readonly', '#ffffff')])
        main = ttk.Frame(self, padding=28)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='PRIVATE MEDIA WORKSPACE', foreground='#8cbcff').pack(anchor='w')
        ttk.Label(main, text='StreamVault', font=('Segoe UI', 27, 'bold')).pack(anchor='w', pady=(2, 12))
        ttk.Label(main, text='Save media you are authorized to download.', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(main, text='Analyze a video or livestream, choose a format, and save it locally.').pack(anchor='w', pady=(5, 18))
        row = ttk.Frame(main); row.pack(fill='x')
        self.url = tk.StringVar()
        ttk.Entry(row, textvariable=self.url).pack(side='left', fill='x', expand=True)
        self.buttons = []
        self.button(row, 'Analyze', self.analyze).pack(side='left', padx=(10, 0))
        self.info = tk.StringVar(value='Ready to analyze a link.')
        ttk.Label(main, textvariable=self.info, wraplength=900).pack(anchor='w', pady=12)
        self.format = ttk.Combobox(main, state='readonly', values=['Best video + audio (MP4)'])
        self.format.current(0); self.format.pack(fill='x')
        row = ttk.Frame(main); row.pack(fill='x', pady=12)
        self.output = tk.StringVar(value=settings.get('output', str(Path.home() / 'Downloads')))
        ttk.Entry(row, textvariable=self.output).pack(side='left', fill='x', expand=True)
        self.button(row, 'Choose folder', self.choose_folder).pack(side='left', padx=(10, 0))
        row = ttk.Frame(main); row.pack(fill='x')
        self.button(row, 'Download', self.download).pack(side='left')
        ttk.Button(row, text='Cancel', command=self.cancel).pack(side='left', padx=8)
        ttk.Button(row, text='Open output folder', command=self.open_output).pack(side='left')
        self.progress = ttk.Progressbar(main, maximum=100)
        self.progress.pack(fill='x', pady=(14, 18))
        ttk.Separator(main).pack(fill='x')
        ttk.Label(main, text='Automatic YouTube backups', font=('Segoe UI', 15, 'bold')).pack(anchor='w', pady=(12, 4))
        monitor_message = ('Monitoring finished streams every 5 minutes.' if settings.get('monitor_enabled')
                           else 'YouTube connected. Enable automatic downloads.' if settings.get('refresh_token')
                           else 'Choose a Google OAuth Desktop client file, then connect YouTube.')
        self.monitor_info = tk.StringVar(value=monitor_message)
        ttk.Label(main, textvariable=self.monitor_info, wraplength=920).pack(anchor='w')
        row = ttk.Frame(main); row.pack(fill='x', pady=6)
        self.button(row, 'Choose Google client file', self.choose_client).pack(side='left')
        self.button(row, 'Connect YouTube', self.connect_youtube).pack(side='left', padx=8)
        self.monitor_enabled = tk.BooleanVar(value=bool(settings.get('monitor_enabled', False)))
        ttk.Checkbutton(row, text='Auto-download finished streams', variable=self.monitor_enabled,
                        command=self.toggle_monitor).pack(side='left', padx=8)
        row = ttk.Frame(main); row.pack(fill='x')
        ttk.Label(row, text='Signed-in browser for private videos:').pack(side='left')
        self.cookie_browser = tk.StringVar(value=settings.get('cookie_browser', 'chrome'))
        ttk.Combobox(row, state='readonly', textvariable=self.cookie_browser,
                     values=['chrome', 'edge', 'firefox', 'brave'], width=12).pack(side='left', padx=8)
        ttk.Label(row, text='Keep StreamVault open; checks run every 5 minutes.').pack(side='left')
        self.cookie_browser.trace_add('write', lambda *_: self.save_settings())
        ttk.Separator(main).pack(fill='x')
        ttk.Label(main, text='Local tools', font=('Segoe UI', 15, 'bold')).pack(anchor='w', pady=(16, 4))
        self.tool_status = tk.StringVar(value='Checking dependencies…')
        ttk.Label(main, textvariable=self.tool_status, wraplength=920).pack(anchor='w')
        row = ttk.Frame(main); row.pack(fill='x', pady=10)
        self.button(row, 'Update yt-dlp', lambda: self.start(lambda: update_tool('yt-dlp', self.log)) ).pack(side='left')
        self.button(row, 'Update FFmpeg', lambda: self.start(lambda: update_tool('ffmpeg', self.log)) ).pack(side='left', padx=8)
        self.button(row, 'Replace local tool…', self.replace_local).pack(side='left')
        ttk.Button(row, text='Tools folder', command=lambda: os.startfile(TOOLS)).pack(side='left', padx=8)
        self.logbox = tk.Text(main, height=7, bg='#111b30', fg='#b6c9e8', relief='flat', wrap='word', font=('Consolas', 9))
        self.logbox.pack(fill='both', expand=True)
        self.logbox.configure(state='disabled')
        self.after(100, self.pump)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.start(self.bootstrap)
        threading.Thread(target=self.monitor_loop, daemon=True).start()

    def save_settings(self):
        self.saved_settings.update(output=self.output.get(), monitor_enabled=self.monitor_enabled.get(),
                                   cookie_browser=self.cookie_browser.get(), monitor_seen=sorted(self.monitor_seen)[-500:])
        self.settings.write_text(json.dumps(self.saved_settings, indent=2), encoding='utf-8')

    def choose_client(self):
        path = filedialog.askopenfilename(title='Google OAuth Desktop client JSON', filetypes=[('JSON', '*.json')])
        if path:
            try: youtube_monitor.read_client(path)
            except Exception as error:
                messagebox.showerror('Invalid client file', str(error)); return
            self.saved_settings['client_file'] = path
            self.save_settings()
            self.monitor_info.set('Google client file selected. Connect YouTube next.')

    def connect_youtube(self):
        client = self.saved_settings.get('client_file')
        if not client:
            messagebox.showinfo('Setup needed', 'Choose a Google OAuth Desktop client JSON file first.'); return
        def work():
            token = youtube_monitor.authorize(client)
            self.events.put(('connected', secure_token.protect(token)))
        self.start(work)

    def toggle_monitor(self):
        if self.monitor_enabled.get() and not self.saved_settings.get('refresh_token'):
            self.monitor_enabled.set(False)
            messagebox.showinfo('Connect YouTube', 'Connect your YouTube account first.'); return
        if self.monitor_enabled.get() and not self.saved_settings.get('monitor_since'):
            self.saved_settings['monitor_since'] = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        self.save_settings()
        self.monitor_info.set('Monitoring finished streams every 5 minutes.' if self.monitor_enabled.get() else 'Automatic downloads paused.')

    def monitor_loop(self):
        while not self.monitor_stop.is_set():
            if self.saved_settings.get('monitor_enabled') and self.saved_settings.get('refresh_token'):
                try:
                    token = youtube_monitor.access_token(self.saved_settings['client_file'],
                                                         secure_token.unprotect(self.saved_settings['refresh_token']))
                    since = self.saved_settings.get('monitor_since', '')
                    for item in youtube_monitor.completed_broadcasts(token):
                        video_id = item['id']
                        ended = item.get('snippet', {}).get('actualEndTime', '')
                        if not ended or (since and datetime.fromisoformat(ended.replace('Z', '+00:00')) < datetime.fromisoformat(since)) or video_id in self.monitor_seen or video_id in self.monitor_pending:
                            continue
                        if youtube_monitor.replay_ready(token, video_id):
                            self.monitor_pending.add(video_id)
                            self.events.put(('auto', video_id))
                            break
                except Exception as error:
                    self.events.put(('monitor', 'Monitor check failed: ' + str(error)))
            self.monitor_stop.wait(300)

    def button(self, parent, label, action):
        button = ttk.Button(parent, text=label, command=action)
        self.buttons.append(button)
        return button

    def log(self, text): self.events.put(('log', str(text)))

    def bootstrap(self):
        for name in ('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe'):
            if not (TOOLS / name).exists() and (ORIGINAL / name).exists():
                shutil.copy2(ORIGINAL / name, TOOLS / name)
        self.log('Tools are isolated in ' + str(TOOLS))

    def status(self):
        lines = []
        for name in ('yt-dlp.exe', 'ffmpeg.exe'):
            try: lines.append(version(TOOLS / name)[:100])
            except Exception: lines.append(name + ': missing or unavailable — use Update')
        self.events.put(('tools', '\n'.join(lines)))

    def start(self, task):
        if self.busy: return
        self.busy = True
        for button in self.buttons: button.configure(state='disabled')
        def worker():
            try: task()
            except Exception as error: self.log('ERROR: ' + str(error))
            finally:
                self.status()
                self.events.put(('done', None))
        threading.Thread(target=worker, daemon=True).start()

    def pump(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.logbox.configure(state='normal'); self.logbox.insert('end', value + '\n'); self.logbox.see('end'); self.logbox.configure(state='disabled')
                elif kind == 'tools': self.tool_status.set(value)
                elif kind == 'monitor': self.monitor_info.set(value); self.log(value)
                elif kind == 'connected':
                    self.saved_settings['refresh_token'] = value
                    self.save_settings()
                    self.monitor_info.set('YouTube connected. Enable automatic downloads.')
                elif kind == 'auto_saved':
                    self.monitor_seen.add(value)
                    self.save_settings()
                elif kind == 'auto':
                    if self.busy:
                        self.events.put(('auto', value))
                        break
                    if self.monitor_enabled.get():
                        self.download_url('https://www.youtube.com/watch?v=' + value,
                                          Path(self.output.get()).expanduser(), 'bv*+ba/b', value)
                    else: self.monitor_pending.discard(value)
                elif kind == 'progress': self.progress['value'] = value
                elif kind == 'media':
                    self.info.set(value.get('title', 'Media') + '  •  ' + str(value.get('uploader') or ''))
                    self.formats = ['bv*+ba/b']; labels = ['Best video + audio (MP4)']
                    for fmt in reversed(value.get('formats', [])):
                        if fmt.get('vcodec', 'none') != 'none' and fmt.get('height'):
                            fid = str(fmt['format_id']); self.formats.append(fid + '+ba/b' if fmt.get('acodec') == 'none' else fid)
                            labels.append(f"{fmt['height']}p • {fmt.get('ext', '')} • {fmt.get('format_note', '')} [{fid}]")
                    self.format['values'] = labels; self.format.current(0)
                elif kind == 'done':
                    self.busy = False
                    for button in self.buttons: button.configure(state='normal')
        except queue.Empty: pass
        self.after(100, self.pump)

    def valid_url(self):
        value = self.url.get().strip()
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            messagebox.showerror('Invalid URL', 'Enter an http or https media URL.'); return None
        return value

    def analyze(self):
        url = self.valid_url()
        if not url: return
        self.media_url = None
        def work():
            self.log('Analyzing…')
            result = run([TOOLS / 'yt-dlp.exe', '--ignore-config', '--dump-single-json', '--no-playlist', '--', url], 180)
            if result.returncode: raise RuntimeError(result.stderr[-4000:])
            data = json.loads(result.stdout)
            self.media_url = url
            self.events.put(('media', data)); self.log('Analysis complete.')
        self.start(work)

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output.get())
        if folder: self.output.set(folder)

    def open_output(self):
        path = Path(self.output.get())
        if path.is_dir(): os.startfile(path)

    def download(self):
        url = self.valid_url()
        if not url: return
        if self.media_url != url:
            messagebox.showinfo('Analyze first', 'Analyze this link before choosing a format and downloading.'); return
        folder = Path(self.output.get()).expanduser()
        fmt = self.formats[self.format.current()]
        self.download_url(url, folder, fmt)

    def download_url(self, url, folder, fmt, auto_id=None):
        self.cancelled.clear(); self.progress['value'] = 0
        browser = self.cookie_browser.get()
        self.save_settings()
        def work():
            folder.mkdir(parents=True, exist_ok=True)
            args = [TOOLS / 'yt-dlp.exe', '--ignore-config', '--no-playlist', '--newline', '--format', fmt,
                    '--merge-output-format', 'mp4', '--ffmpeg-location', TOOLS,
                    '--download-archive', folder / '.streamvault-archive.txt', '--output', str(folder / '%(title).180B [%(id)s].%(ext)s'),
                    '--progress-template', 'download:SV_PROGRESS:%(progress._percent_str)s']
            if auto_id:
                args += ['--cookies-from-browser', browser]
            args += ['--', url]
            self.log(('Auto-downloading ' if auto_id else 'Downloading ') + url)
            self.process = subprocess.Popen([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding='utf-8', errors='replace', creationflags=FLAGS)
            try:
                for line in self.process.stdout:
                    if 'SV_PROGRESS:' in line:
                        match = re.search(r'([\d.]+)%', line)
                        if match: self.events.put(('progress', float(match.group(1))))
                    else: self.log(line.strip())
                code = self.process.wait()
                if self.cancelled.is_set(): self.log('Cancelled. Partial files can be resumed.')
                elif code: raise RuntimeError('Download failed. See the log above.')
                else:
                    self.events.put(('progress', 100)); self.log('Saved successfully (or already in archive).')
                    if auto_id:
                        self.events.put(('auto_saved', auto_id))
            finally:
                self.process = None
                if auto_id: self.monitor_pending.discard(auto_id)
        self.start(work)

    def cancel(self):
        self.cancelled.set()
        process = self.process
        if process and process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, creationflags=FLAGS)

    def replace_local(self):
        path = filedialog.askopenfilename(title='Select yt-dlp.exe, ffmpeg.exe or ffprobe.exe', filetypes=[('Executable', '*.exe')])
        if not path: return
        source = Path(path)
        if source.name.lower() not in ('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe'):
            messagebox.showerror('Unsupported tool', 'Choose yt-dlp.exe, ffmpeg.exe or ffprobe.exe.'); return
        self.start(lambda: (install_files({source.name.lower(): source}), self.log('Local tool replaced successfully.')))

    def close(self):
        if self.busy:
            messagebox.showinfo('Work in progress', 'Wait for the current operation to finish. Use Cancel to stop a media download.'); return
        self.monitor_stop.set()
        self.destroy()

if __name__ == '__main__':
    App().mainloop()
