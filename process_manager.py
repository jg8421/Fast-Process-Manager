"""极速进程管家：Windows 进程查看、结束及重启工具。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

# 在创建 Tk 窗口前启用高 DPI 感知，避免 4K 屏由系统放大造成模糊。
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # Per-monitor DPI aware v2
except (AttributeError, OSError):
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except OSError:
        user32.SetProcessDPIAware()
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.DestroyIcon.argtypes = [ctypes.c_void_p]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
DI_NORMAL = 3


class PMCX(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak", ctypes.c_size_t),
                ("working", ctypes.c_size_t), ("qpeak", ctypes.c_size_t), ("q", ctypes.c_size_t),
                ("npeak", ctypes.c_size_t), ("n", ctypes.c_size_t), ("page", ctypes.c_size_t),
                ("pagepeak", ctypes.c_size_t), ("private", ctypes.c_size_t)]


class BMIH(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("width", ctypes.c_long), ("height", ctypes.c_long),
                ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                ("image", wintypes.DWORD), ("x", ctypes.c_long), ("y", ctypes.c_long),
                ("used", wintypes.DWORD), ("important", wintypes.DWORD)]


class BMI(ctypes.Structure):
    _fields_ = [("header", BMIH), ("colors", wintypes.DWORD * 3)]


class MEMSTAT(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD), ("total", ctypes.c_ulonglong),
                ("available", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]


class IFROW(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar * 256), ("index", wintypes.DWORD), ("type", wintypes.DWORD),
                ("mtu", wintypes.DWORD), ("speed", wintypes.DWORD), ("address_len", wintypes.DWORD),
                ("address", ctypes.c_ubyte * 8), ("admin", wintypes.DWORD), ("oper", wintypes.DWORD),
                ("last_change", wintypes.DWORD), ("in_octets", wintypes.DWORD), ("in_ucast", wintypes.DWORD),
                ("in_nucast", wintypes.DWORD), ("in_discards", wintypes.DWORD), ("in_errors", wintypes.DWORD),
                ("in_unknown", wintypes.DWORD), ("out_octets", wintypes.DWORD), ("out_ucast", wintypes.DWORD),
                ("out_nucast", wintypes.DWORD), ("out_discards", wintypes.DWORD), ("out_errors", wintypes.DWORD),
                ("out_queue", wintypes.DWORD), ("description_len", wintypes.DWORD), ("description", ctypes.c_ubyte * 256)]


def ft_int(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def cpu_time(handle):
    a = wintypes.FILETIME(); b = wintypes.FILETIME(); c = wintypes.FILETIME(); d = wintypes.FILETIME()
    return ft_int(c) + ft_int(d) if kernel32.GetProcessTimes(handle, ctypes.byref(a), ctypes.byref(b), ctypes.byref(c), ctypes.byref(d)) else None


def hung_pids():
    found = set()
    CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.IsHungAppWindow(hwnd):
            pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)); found.add(pid.value)
        return True
    user32.EnumWindows(CALLBACK(visit), 0)
    return found


def pretty_size(value):
    return f"{value / 1024**3:.2f} GB" if value >= 1024**3 else f"{value / 1024**2:.0f} MB"


def system_times():
    idle = wintypes.FILETIME(); kernel = wintypes.FILETIME(); user = wintypes.FILETIME()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)): return None
    return ft_int(idle), ft_int(kernel), ft_int(user)


def network_bytes():
    size = wintypes.DWORD(0)
    if iphlpapi.GetIfTable(None, ctypes.byref(size), False) not in (0, 122) or not size.value: return 0, 0
    data = (ctypes.c_byte * size.value)()
    if iphlpapi.GetIfTable(ctypes.byref(data), ctypes.byref(size), False): return 0, 0
    count = ctypes.cast(ctypes.byref(data), ctypes.POINTER(wintypes.DWORD)).contents.value
    rows = ctypes.cast(ctypes.byref(data, ctypes.sizeof(wintypes.DWORD)), ctypes.POINTER(IFROW))
    # 6 = Ethernet, 71 = Wi-Fi. Legacy API uses 5 for an operational interface.
    # Windows may expose several Wi-Fi aliases carrying identical byte totals, so de-duplicate them.
    active = [rows[i] for i in range(count) if rows[i].oper in (4, 5) and rows[i].type in (6, 71)]
    unique = {(x.in_octets, x.out_octets) for x in active}
    return sum(x[0] for x in unique), sum(x[1] for x in unique)


def fallback_icon(name, size=24):
    colors = [(38, 108, 191), (0, 139, 123), (122, 78, 180), (211, 93, 28)]
    r, g, b = colors[sum(map(ord, name)) % len(colors)]
    data = bytearray(f"P6\n{size} {size}\n255\n".encode())
    for y in range(size):
        for x in range(size):
            data.extend((r, g, b) if (x - 12)**2 + (y - 12)**2 < 110 else (244, 246, 248))
    return tk.PhotoImage(data=bytes(data), format="PPM")


def program_icon(path, name):
    icon = wintypes.HICON()
    if not path or not shell32.ExtractIconExW(path, 0, None, ctypes.byref(icon), 1) or not icon.value:
        return fallback_icon(name)
    size = 24; bits = ctypes.c_void_p(); bmi = BMI()
    bmi.header.size = ctypes.sizeof(BMIH); bmi.header.width = size; bmi.header.height = -size; bmi.header.planes = 1; bmi.header.bits = 32
    bitmap = gdi32.CreateDIBSection(None, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    dc = gdi32.CreateCompatibleDC(None)
    if not bitmap or not dc:
        if bitmap: gdi32.DeleteObject(bitmap)
        if dc: gdi32.DeleteDC(dc)
        user32.DestroyIcon(icon)
        return fallback_icon(name)
    old = gdi32.SelectObject(dc, bitmap); user32.DrawIconEx(dc, 0, 0, icon, size, size, 0, None, DI_NORMAL)
    raw = (ctypes.c_ubyte * (size * size * 4)).from_address(bits.value)
    ppm = bytearray(f"P6\n{size} {size}\n255\n".encode())
    for i in range(0, len(raw), 4): ppm.extend((raw[i + 2], raw[i + 1], raw[i]))
    gdi32.SelectObject(dc, old); gdi32.DeleteObject(bitmap); gdi32.DeleteDC(dc); user32.DestroyIcon(icon)
    return tk.PhotoImage(data=bytes(ppm), format="PPM")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("极速进程管家")
        self.dpi_scale = max(1.0, self.winfo_fpixels("1i") / 96)
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(int(1280 * self.dpi_scale), screen_w - int(80 * self.dpi_scale))
        height = min(int(760 * self.dpi_scale), screen_h - int(100 * self.dpi_scale))
        self.geometry(f"{width}x{height}")
        self.minsize(int(900 * self.dpi_scale), int(560 * self.dpi_scale)); self.configure(bg="#f4f6f8")
        self.samples, self.icons, self.keys = {}, {}, {}
        # 默认：死机/未响应进程置顶，其余按 CPU 从高到低。
        self.auto, self.job, self.sort, self.desc = False, None, "priority", True
        self.sys_sample = None
        self.net_sample = None
        self.gpu, self.npu = None, None
        self.no_restart = {"svchost.exe", "sihost.exe", "explorer.exe", "shellhost.exe", "searchhost.exe", "startmenuexperiencehost.exe", "runtimebroker.exe", "textinputhost.exe", "lockapp.exe", "unsecapp.exe", "dllhost.exe", "conhost.exe", "splwow64.exe"}
        self.build()
        self.after(120, self.refresh)  # 启动时刷新一次
        self.after(200, self.update_metrics)
        threading.Thread(target=self.poll_accelerators, daemon=True).start()

    def build(self):
        px = lambda value: int(value * self.dpi_scale)
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Treeview", rowheight=px(32), font=("Microsoft YaHei UI", 11), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 11, "bold"), background="#e8edf3")
        style.map("Treeview", background=[("selected", "#d9eaff")])
        top = tk.Frame(self, bg="#f4f6f8", padx=16, pady=13); top.pack(fill="x")
        self.network = tk.Label(top, text="↑ --  ↓ --", font=("Microsoft YaHei UI", 10, "bold"), bg="#f4f6f8", fg="#0078d4")
        self.network.pack(side="left", padx=(0, 18))
        tk.Label(top, text="极速进程管家", font=("Microsoft YaHei UI", 17, "bold"), bg="#f4f6f8", fg="#172b4d").pack(side="left")
        self.summary = tk.Label(top, text="正在读取…", font=("Microsoft YaHei UI", 10), bg="#f4f6f8", fg="#536171"); self.summary.pack(side="left", padx=18)
        self.metrics = tk.Label(top, text="CPU --  内存 --  GPU --  NPU --  磁盘 --", font=("Microsoft YaHei UI", 10, "bold"), bg="#f4f6f8", fg="#27364a")
        self.metrics.pack(side="right", padx=(0, 15))
        ttk.Button(top, text="↻ 立即刷新", command=self.refresh).pack(side="right")
        ttk.Button(top, text="结束选中进程", command=self.kill_selected).pack(side="right", padx=(0, 10))
        body = tk.Frame(self, bg="#f4f6f8", padx=16); body.pack(fill="both", expand=True)
        cols = ("status", "name", "count", "cpu", "memory")
        self.tree = ttk.Treeview(body, columns=cols, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text=""); self.tree.column("#0", width=px(42), minwidth=px(42), stretch=False)
        for key, label, width in [("status", "状态", 110), ("name", "软件", 520), ("count", "进程数", 115), ("cpu", "CPU", 140), ("memory", "内存", 160)]:
            self.tree.heading(key, text=label, command=lambda c=key: self.change_sort(c)); self.tree.column(key, width=px(width), anchor="e" if key in ("count", "cpu", "memory") else "w", stretch=key == "name")
        self.tree.tag_configure("hung", foreground="#c62828"); self.tree.tag_configure("hot", foreground="#d35400")
        bar = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True); bar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _: self.kill_selected()); self.tree.bind("<Delete>", lambda _: self.kill_selected()); self.tree.bind("<Button-3>", self.menu_open)
        self.menu = tk.Menu(self, tearoff=False, font=("Microsoft YaHei UI", 10)); self.menu.add_command(label="结束进程", command=self.kill_selected); self.menu.add_command(label="重启", command=self.restart_selected)
        bottom = tk.Frame(self, bg="#f4f6f8", padx=16, pady=11); bottom.pack(fill="x")
        tk.Label(bottom, text="右键可结束或重启；Delete 直接结束。", bg="#f4f6f8", fg="#687687", font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.auto_text = tk.StringVar(value="自动刷新：已关闭"); ttk.Button(bottom, textvariable=self.auto_text, command=self.toggle_auto).pack(side="right")

    def menu_open(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row); self.menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def change_sort(self, key):
        self.desc = not self.desc if self.sort == key else key in ("cpu", "memory"); self.sort = key; self.refresh()

    def toggle_auto(self):
        self.auto = not self.auto; self.auto_text.set("自动刷新：开启" if self.auto else "自动刷新：已关闭")
        if self.auto: self.refresh()
        elif self.job: self.after_cancel(self.job); self.job = None

    def auto_refresh(self): self.job = None; self.refresh()

    def poll_accelerators(self):
        """GPU/NPU counters are optional Windows performance counters; keep their polling off the UI thread."""
        command = """$g=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; $n=(Get-Counter '\\NPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; $gs=if($g){($g|Measure-Object CookedValue -Sum).Sum}else{-1}; $ns=if($n){($n|Measure-Object CookedValue -Sum).Sum}else{-1}; Write-Output ([string]::Format('{0:F1}|{1:F1}',$gs,$ns))"""
        while True:
            try:
                result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8, creationflags=0x08000000)
                parts = result.stdout.strip().split("|")
                if len(parts) == 2:
                    self.gpu = max(0.0, min(100.0, float(parts[0]))) if float(parts[0]) >= 0 else None
                    self.npu = max(0.0, min(100.0, float(parts[1]))) if float(parts[1]) >= 0 else None
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            time.sleep(4)

    def update_metrics(self):
        now = time.perf_counter(); current = system_times(); cpu_text = "--"
        if current and self.sys_sample:
            idle = current[0] - self.sys_sample[0]; total = (current[1] + current[2]) - (self.sys_sample[1] + self.sys_sample[2])
            if total > 0: cpu_text = f"{max(0, min(100, (total - idle) / total * 100)):.0f}%"
        if current: self.sys_sample = current
        memory = MEMSTAT(); memory.length = ctypes.sizeof(memory)
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            memory_text = f"{memory.load}%"
        else: memory_text = "--"
        incoming, outgoing = network_bytes()
        if self.net_sample:
            elapsed = now - self.net_sample[2]
            down = max(0, incoming - self.net_sample[0]) * 8 / max(elapsed, 0.001) / 1_000_000
            up = max(0, outgoing - self.net_sample[1]) * 8 / max(elapsed, 0.001) / 1_000_000
            self.network.config(text=f"↑ {up:.2f} Mbps  ↓ {down:.2f} Mbps")
        self.net_sample = (incoming, outgoing, now)
        try:
            drive = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
            disk_text = f"{drive.used / drive.total * 100:.0f}%"
        except OSError: disk_text = "--"
        gpu_text = f"{self.gpu:.0f}%" if self.gpu is not None else "--"
        npu_text = f"{self.npu:.0f}%" if self.npu is not None else "--"
        self.metrics.config(text=f"CPU {cpu_text}  内存 {memory_text}  GPU {gpu_text}  NPU {npu_text}  磁盘 {disk_text}")
        self.after(1000, self.update_metrics)

    def collect(self):
        buf = (wintypes.DWORD * 4096)(); used = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(buf), ctypes.sizeof(buf), ctypes.byref(used)): return []
        now, hung, rows, alive = time.perf_counter(), hung_pids(), [], set()
        for value in buf[:used.value // 4]:
            pid = int(value)
            if not pid or pid in alive: continue
            alive.add(pid); handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
            if not handle: continue
            try:
                pathbuf = ctypes.create_unicode_buffer(1024); length = wintypes.DWORD(len(pathbuf))
                path = pathbuf.value if kernel32.QueryFullProcessImageNameW(handle, 0, pathbuf, ctypes.byref(length)) else ""
                name = os.path.basename(path) or f"PID {pid}"
                mem = PMCX(); mem.cb = ctypes.sizeof(mem); memory = int(mem.working) if psapi.GetProcessMemoryInfo(handle, ctypes.byref(mem), mem.cb) else 0
                total, cpu = cpu_time(handle), 0.0; old = self.samples.get(pid)
                if total is not None and old and now > old[1]: cpu = max(0.0, min(100.0, (total - old[0]) / 10_000_000 / (now - old[1]) / (os.cpu_count() or 1) * 100))
                if total is not None: self.samples[pid] = (total, now)
                rows.append({"pid": pid, "name": name, "path": path, "memory": memory, "cpu": cpu, "hung": pid in hung})
            finally: kernel32.CloseHandle(handle)
        self.samples = {p: x for p, x in self.samples.items() if p in alive}
        return rows

    def refresh(self):
        if self.job: self.after_cancel(self.job); self.job = None
        selected = {self.keys.get(x) for x in self.tree.selection()}; groups = {}
        for row in self.collect():
            key = row["name"].lower(); group = groups.setdefault(key, {"name": row["name"], "path": row["path"], "pids": [], "cpu": 0.0, "memory": 0, "hung": False})
            group["pids"].append(row["pid"]); group["cpu"] += row["cpu"]; group["memory"] += row["memory"]; group["hung"] |= row["hung"]
        rows = list(groups.values())
        if self.sort == "priority":
            sorter = lambda x: (int(x["hung"]), x["cpu"])
        elif self.sort == "status":
            sorter = lambda x: int(x["hung"])
        elif self.sort == "name":
            sorter = lambda x: x["name"].lower()
        else:
            sorter = lambda x: x[self.sort]
        rows.sort(key=sorter, reverse=self.desc)
        old = self.tree.get_children()
        if old: self.tree.delete(*old)
        self.keys = {}
        for row in rows:
            key = row["name"].lower()
            if key not in self.icons: self.icons[key] = program_icon(row["path"], row["name"])
            tag = "hung" if row["hung"] else "hot" if row["cpu"] >= 25 else ""
            iid = self.tree.insert("", "end", text="", image=self.icons[key], values=("未响应" if row["hung"] else "正常", row["name"], len(row["pids"]), f"{row['cpu']:.1f}%", pretty_size(row["memory"])), tags=(tag,) if tag else ())
            self.keys[iid] = key
            if key in selected: self.tree.selection_add(iid)
        self.summary.config(text=f"{len(rows)} 个软件 · 未响应 {sum(x['hung'] for x in rows)} 个 · {'自动刷新中' if self.auto else '仅手动刷新'}")
        if self.auto: self.job = self.after(1200, self.auto_refresh)

    def targets(self):
        result = []
        for item in self.tree.selection():
            values = self.tree.item(item, "values")
            if values and values[1].lower() != os.path.basename(sys.executable).lower(): result.append((values[1], self.keys.get(item, values[1].lower())))
        return result

    def end(self, targets):
        mapping = {}
        for row in self.collect(): mapping.setdefault(row["name"].lower(), []).append(row["pid"])
        for _, key in targets:
            for pid in mapping.get(key, []): subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=0x08000000)

    def kill_selected(self):
        targets = self.targets()
        if targets: self.end(targets); self.refresh()

    def restart_selected(self):
        targets = self.targets(); rows = self.collect(); paths = {x["name"].lower(): x["path"] for x in rows}
        targets = [(name, key) for name, key in targets if name.lower() not in self.no_restart]
        if not targets: return
        self.end(targets)
        for _, key in targets:
            path = paths.get(key)
            if path and os.path.isfile(path):
                try: subprocess.Popen([path], creationflags=0x08000000)
                except OSError: pass
        self.refresh()


if __name__ == "__main__":
    if sys.platform != "win32": raise SystemExit("Windows only")
    shell32.SetCurrentProcessExplicitAppUserModelID("jg.FastProcessManager")
    App().mainloop()
