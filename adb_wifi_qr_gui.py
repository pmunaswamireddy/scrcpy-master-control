import os
import random
import string
import time
import subprocess
import sys
import asyncio
import threading
import urllib.request
import json
import zipfile
import qrcode
import queue
import shlex
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
from zeroconf import ServiceBrowser, Zeroconf

# --- Core Helpers ---

def get_exe_dir():
    """Returns the base directory of the application, handling both script and PyInstaller modes."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# --- Configuration & Constants ---
ADB = os.path.join(get_exe_dir(), "tools", "adb.exe")
SCRCPY = os.path.join(get_exe_dir(), "tools", "scrcpy.exe")
SETTINGS_FILE = os.path.join(get_exe_dir(), "settings.json")
HISTORY_FILE = os.path.join(get_exe_dir(), "history.json")

SHORTCUTS_TEXT = """Shortcuts (Modifier 'MOD' is usually Left Alt or Left Super/Windows key):

MOD+f                   Switch fullscreen mode
MOD+Left                Rotate display left
MOD+Right               Rotate display right
MOD+Shift+Left/Right    Flip display horizontally
MOD+Shift+Up/Down       Flip display vertically
MOD+z                   Pause or re-pause display
MOD+Shift+z             Unpause display
MOD+Shift+r             Reset video capture/encoding
MOD+g                   Resize window to 1:1 (pixel-perfect)
MOD+w                   Resize window to remove black borders
Double-click black      Resize window to remove black borders
MOD+h / Mid-click       Click on HOME
MOD+b / Right-click     Click on BACK
MOD+s / 4th-click       Click on APP_SWITCH
MOD+m                   Click on MENU
MOD+Up                  Click on VOLUME_UP
MOD+Down                Click on VOLUME_DOWN
MOD+p                   Click on POWER (turn screen on/off)
Right-click (off)       Power on
MOD+o                   Turn device screen off (keep mirroring)
MOD+Shift+o             Turn device screen on
MOD+r                   Rotate device screen
MOD+n / 5th-click       Expand notification panel
MOD+Shift+n             Collapse notification panel
MOD+c                   Copy to clipboard (Android >= 7)
MOD+x                   Cut to clipboard (Android >= 7)
MOD+v                   Copy computer clipboard to device & paste
MOD+Shift+v             Inject computer clipboard text as key events
MOD+k                   Open keyboard settings on the device
MOD+i                   Enable/disable FPS counter
Ctrl+click-and-move     Pinch-to-zoom and rotate
Shift+click-and-move    Tilt vertically
Drag & drop APK         Install APK from computer
Drag & drop file        Push file to device
"""

# --- Core Logic ---

def generate_name():
    charset = string.ascii_letters + string.digits
    part1 = ''.join(random.choice(charset) for _ in range(14))
    part2 = ''.join(random.choice(charset) for _ in range(6))
    return f"{part1}-{part2}"

def generate_password():
    charset = string.ascii_letters + string.digits
    return ''.join(random.choice(charset) for _ in range(21))

class AdbListener:
    def __init__(self, target_ip=None):
        self.device_info = None
        self.target_ip = target_ip

    def remove_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info and info.addresses:
            ip = ".".join(map(str, info.addresses[0]))
            if self.target_ip is None or ip == self.target_ip:
                self.device_info = (ip, info.port)

    def update_service(self, zeroconf, type, name):
        pass

async def scan_port(ip, port, semaphore):
    async with semaphore:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=0.4)
            writer.close()
            await writer.wait_closed()
            return port
        except:
            if writer:
                writer.close()
            return None

async def scan_ports_async(ip):
    semaphore = asyncio.Semaphore(100)
    # Include 5555 as it is common for manual/remote setups, then the standard dynamic range
    target_ports = [5555] + list(range(37000, 42000))
    tasks = [scan_port(ip, port, semaphore) for port in target_ports]
    for f in asyncio.as_completed(tasks):
        port = await f
        if port:
            res = subprocess.run([ADB, "connect", f"{ip}:{port}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if "connected to" in res.stdout.lower() or "already connected" in res.stdout.lower():
                return port
    return None

def pair(ip, port, password, log_callback):
    log_callback(f"Pairing with {ip}:{port}...")
    result = subprocess.run([ADB, "pair", f"{ip}:{port}", password], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.returncode != 0:
        log_callback(f"Pairing Error: {err or out}")
        return False
    log_callback(f"Pairing Success: {out}")
    return True

def get_mdns_port(ip, log_callback=None):
    try:
        res = subprocess.run([ADB, "mdns", "services"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in res.stdout.splitlines():
            if ip in line and "_adb._tcp" in line:
                parts = line.split()
                if parts and ":" in parts[-1]:
                    port = parts[-1].split(":")[-1]
                    if log_callback: log_callback(f"Found port {port} via adb mdns.")
                    return port
    except Exception:
        pass
    return None

def connect(ip, log_callback, force_kill=False, manual_port=None):
    if force_kill:
        subprocess.run([ADB, "kill-server"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    
    # Sanitize IP: Handle cases where the IP string already contains a port
    target_host = ip
    target_port = manual_port
    
    if ":" in ip:
        target_host = ip.split(":")[0]
        if not target_port:
            target_port = ip.split(":")[1]

    log_callback(f"Connecting to {target_host}...")

    if target_port:
        full_target = f"{target_host}:{target_port}"
        log_callback(f"Trying direct connection to {full_target}...")
        
        # Stale disconnect for remote/vpn hosts
        if "." in target_host or ":" in target_host:
            subprocess.run([ADB, "disconnect", full_target], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
        res = subprocess.run([ADB, "connect", full_target], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if "connected to" in res.stdout.lower() or "already connected" in res.stdout.lower():
            log_callback(f"Connected: {res.stdout.strip()}")
            return full_target

    mdns_port = get_mdns_port(ip, log_callback)
    if mdns_port:
        res = subprocess.run([ADB, "connect", f"{ip}:{mdns_port}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_callback(f"Connected: {res.stdout.strip()}")
        return f"{ip}:{mdns_port}"

    zeroconf = Zeroconf()
    listener = AdbListener(target_ip=ip)
    browser = ServiceBrowser(zeroconf, "_adb-tls-connect._tcp.local.", listener)
    
    connect_port = None
    start_time = time.time()
    while time.time() - start_time < 5:
        if listener.device_info:
            connect_port = listener.device_info[1]
            break
        time.sleep(0.5)
    zeroconf.close()
    
    if connect_port:
        log_callback(f"Found port {connect_port} via zeroconf.")
        res = subprocess.run([ADB, "connect", f"{ip}:{connect_port}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_callback(f"Connected: {res.stdout.strip()}")
        return f"{ip}:{connect_port}"

    log_callback("mDNS not found. Executing port scan fallback...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        connect_port = loop.run_until_complete(scan_ports_async(ip))
        loop.close()
    except Exception:
        pass
            
    if connect_port:
        log_callback(f"Connected to {ip}:{connect_port}")
        return f"{ip}:{connect_port}"
            
    res = subprocess.run([ADB, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if ip in res.stdout:
        log_callback("Device already connected!")
        for line in res.stdout.splitlines():
            if line.startswith(ip) and "device" in line:
                return line.split()[0]
        return ip
            
    log_callback("Unable to connect. Check if Wireless Debugging is ON.")
    return False

def load_history():
    path = HISTORY_FILE
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return {
                    "wireless_ips": data.get("wireless_ips", []),
                    "known_devices": data.get("known_devices", {})
                }
        except:
            return {"wireless_ips": [], "known_devices": {}}
    return {"wireless_ips": [], "known_devices": {}}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_to_history(ip=None, serial=None, name=None):
    data = load_history()
    dirty = False
    
    if ip and ip not in data["wireless_ips"]:
        data["wireless_ips"].append(ip)
        dirty = True
        
    if serial and name:
        if data["known_devices"].get(serial) != name:
            data["known_devices"][serial] = name
            dirty = True
            
    if dirty:
        path = os.path.join(get_exe_dir(), "history.json")
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
        except:
            pass



def find_tool(name):
    exe_dir = get_exe_dir()
    target = name + ".exe"
    
    # Priority 1: Direct subfolder 'tools' (standard for bundled distribution)
    tools_dir = os.path.join(exe_dir, "tools")
    if os.path.exists(os.path.join(tools_dir, target)):
        return os.path.join(tools_dir, target)
        
    # Priority 2: Recursive search (fallback for dev environment)
    for root, dirs, files in os.walk(exe_dir):
        if target in files:
            return os.path.join(root, target)
            
    return name

ADB = "adb"
SCRCPY = "scrcpy"

# --- Modern GUI ---

class AdbApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Core State & Paths
        self.config = load_settings()
        global ADB, SCRCPY
        ADB = self.config.get("adb_path", find_tool("adb"))
        SCRCPY = self.config.get("scrcpy_path", find_tool("scrcpy"))
        
        self.title("Scrcpy Master Control Panel")
        
        # Restore window geometry if saved
        saved_geo = self.config.get("window_geometry", "640x950")
        try:
            self.geometry(saved_geo)
        except:
            self.geometry("640x950")
        
        self.resizable(True, True)
        self.minsize(600, 750)
        
        # Core State
        self.config = load_settings()
        hist_data = load_history()
        self.history = hist_data["wireless_ips"]
        
        self.name = ""
        self.password = ""
        self.is_scanning = False
        self.stop_scan = threading.Event()
        self.current_serial = None
        self.terminal_cwd = os.getcwd()
        self.cmd_history = []
        self.history_idx = -1
        self.custom_path = self.config.get("terminal_path", "")
        self.log_queue = queue.Queue()
        self._process_log_queue()

        # Layout Weights (Main Window)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Main Paned Area

        # --- Header (Global Control) ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, pady=(10, 5), sticky="ew")

        self.title_label = ctk.CTkLabel(self.header_frame, text="📱 Scrcpy Master", 
                                       font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left", padx=20, pady=2)
        
        # New Global Selector & Broadcast Toggle
        control_sub = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        control_sub.pack(side="right", padx=20)

        self.c_broadcast = ctk.CTkCheckBox(control_sub, text="📡 Broadcast to All", 
                                            font=ctk.CTkFont(size=11), text_color="#2ECC71")
        self.c_broadcast.pack(side="right", padx=(10, 0))

        self.opt_devices = ctk.CTkOptionMenu(control_sub, values=["Scanning..."], 
                                             width=250, height=36, command=self.on_device_select,
                                             fg_color="#1F1F1F", button_color="#333", button_hover_color="#444")
        self.opt_devices.pack(side="right")
        
        # --- Tab Switcher ---
        self.tab_selector = ctk.CTkSegmentedButton(self, 
                                                 values=["Devices", "Pairing", "Settings", "Advanced", "Shortcuts"],
                                                 font=ctk.CTkFont(size=14, weight="bold"),
                                                 height=45,
                                                 command=self._switch_tab)
        self.tab_selector.grid(row=1, column=0, pady=(5, 10), sticky="ew", padx=20)
        self.tab_selector.set("Devices")

        # --- Paned Splitter Area ---
        self.panes = tk.PanedWindow(self, orient="vertical", bg="#222", bd=0, sashwidth=4, sashpad=0, opaqueresize=True)
        self.panes.grid(row=2, column=0, sticky="nsew", padx=20, pady=5)

        # Content Frame (Top Pane)
        self.content_frame = ctk.CTkFrame(self.panes, fg_color="transparent")
        self.panes.add(self.content_frame, height=520, minsize=350)
        
        # Log tool paths for debugging
        self.after(100, lambda: self.log(f"🔎 ADB: {ADB}"))
        self.after(200, lambda: self.log(f"🔎 Scrcpy: {SCRCPY}"))

        self.tabs = {}
        for name in ["Devices", "Pairing", "Settings", "Advanced", "Shortcuts"]:
            if name in ["Devices", "Pairing", "Settings"]:
                f = ctk.CTkScrollableFrame(self.content_frame, fg_color="transparent")
            else:
                f = ctk.CTkFrame(self.content_frame, fg_color="transparent")
            
            self.tabs[name] = f
            if name == "Devices": self.setup_devices_tab(f)
            elif name == "Pairing": self.setup_pair_tab(f)
            elif name == "Settings": self.setup_settings_tab(f)
            elif name == "Advanced": self.setup_advanced_tab(f)
            elif name == "Shortcuts": self.setup_shortcuts_tab(f)
        
        self._switch_tab("Devices")

        # Console (Bottom Pane) ---
        self.console_container = ctk.CTkFrame(self.panes, fg_color="black", corner_radius=10)
        self.panes.add(self.console_container, height=350, minsize=150, stretch="always")
        
        self.console_container.grid_rowconfigure(1, weight=1)
        self.console_container.grid_columnconfigure(0, weight=1)

        # Console Header
        self.con_head = ctk.CTkFrame(self.console_container, fg_color="transparent")
        self.con_head.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(self.con_head, text="SYSTEM BASH CONSOLE", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#555").pack(side="left", padx=(0, 10))
        
        def add_q(text, cmd):
            btn = ctk.CTkButton(self.con_head, text=text, width=65, height=22, font=ctk.CTkFont(size=10), 
                                fg_color="#222", hover_color="#333", border_width=1, border_color="#444",
                                command=lambda: self.run_shell_cmd(cmd))
            btn.pack(side="left", padx=2)

        add_q("Devices", "adb devices -l")
        add_q("IP List", "adb shell ip -f inet addr show wlan0")
        add_q("Reset", "adb kill-server && adb devices")
        add_q("Pair?", "adb help pair")
        
        ctk.CTkButton(self.con_head, text="📍 Path", width=60, height=22, font=ctk.CTkFont(size=10), fg_color="#333", border_width=1, command=self._set_terminal_path).pack(side="left", padx=2)
        
        ctk.CTkButton(self.con_head, text="🗑️ Clear", width=60, height=22, font=ctk.CTkFont(size=10), fg_color="transparent", border_width=1, command=self.clear_logs).pack(side="right", padx=5)
        ctk.CTkButton(self.con_head, text="📋 Copy", width=60, height=22, font=ctk.CTkFont(size=10), fg_color="transparent", border_width=1, command=self.copy_logs).pack(side="right")

        # Console Text Area
        self.console_log = ctk.CTkTextbox(self.console_container, font=ctk.CTkFont(family="Consolas", size=11), text_color="#2ECC71", fg_color="black")
        self.console_log.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        self.console_log.insert("0.0", "--- ADB MASTER CONSOLE READY (DRAGGABLE) ---\n")
        self.console_log.configure(state="disabled")

        # Console Input
        self.con_in_row = ctk.CTkFrame(self.console_container, fg_color="transparent")
        self.con_in_row.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        
        self.cmd_entry = ctk.CTkEntry(self.con_in_row, placeholder_text="Enter ADB command...", height=32, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#111", border_color="#333")
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.cmd_entry.bind("<Return>", lambda e: self.on_cmd_exec())
        self.cmd_entry.bind("<Up>", self._on_cmd_history_up)
        self.cmd_entry.bind("<Down>", self._on_cmd_history_down)
        
        ctk.CTkButton(self.con_in_row, text="EXECUTE", width=80, height=32, font=ctk.CTkFont(size=11, weight="bold"), command=self.on_cmd_exec).pack(side="right")

        # --- Footer Actions ---
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=3, column=0, pady=(5, 15), sticky="ew")
        self.action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        btn_font = ctk.CTkFont(size=13, weight="bold")
        
        self.btn_scrcpy = ctk.CTkButton(self.action_frame, text="🚀 Launch", fg_color="#2B8C3E", hover_color="#1E612B", 
                                       height=50, font=btn_font, command=self.launch_scrcpy)
        self.btn_scrcpy.grid(row=0, column=0, padx=10, sticky="ew")
        
        self.btn_disconnect = ctk.CTkButton(self.action_frame, text="❌ Disconnect All", fg_color="#C42B1C", hover_color="#8F1F14", 
                                           height=50, font=btn_font, command=self.disconnect_all)
        self.btn_disconnect.grid(row=0, column=1, padx=10, sticky="ew")
        
        self.btn_refresh = ctk.CTkButton(self.action_frame, text="🔄 Refresh", fg_color="#333333", 
                                        height=50, font=btn_font, command=self.refresh_devices)
        self.btn_refresh.grid(row=0, column=2, padx=10, sticky="ew")
        
        self.refresh_devices()

    def _switch_tab(self, name):
        for t_name, frame in self.tabs.items():
            if t_name == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

    def clear_logs(self):
        self.console_log.configure(state="normal")
        self.console_log.delete("1.0", "end")
        self.console_log.configure(state="disabled")

    def copy_logs(self):
        text = self.console_log.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log("📋 Copied!")

    def on_cmd_exec(self):
        cmd = self.cmd_entry.get().strip()
        if cmd:
            if not self.cmd_history or self.cmd_history[-1] != cmd:
                self.cmd_history.append(cmd)
            self.history_idx = -1
            self.cmd_entry.delete(0, 'end')
            self.run_shell_cmd(cmd)

    def _on_cmd_history_up(self, event):
        if not self.cmd_history: return
        if self.history_idx == -1: self.history_idx = len(self.cmd_history) - 1
        elif self.history_idx > 0: self.history_idx -= 1
        self.cmd_entry.delete(0, 'end')
        self.cmd_entry.insert(0, self.cmd_history[self.history_idx])

    def _on_cmd_history_down(self, event):
        if self.history_idx == -1: return
        self.history_idx += 1
        if self.history_idx >= len(self.cmd_history):
            self.history_idx = -1
            self.cmd_entry.delete(0, 'end')
        else:
            self.cmd_entry.delete(0, 'end')
            self.cmd_entry.insert(0, self.cmd_history[self.history_idx])

    def _set_terminal_path(self):
        f = filedialog.askdirectory(title="Select Folder to add to Terminal PATH")
        if f:
            self.custom_path = f
            self.save_all_settings()
            self.log(f"\n📍 Custom terminal path set to: {f}")

    def run_shell_cmd(self, original_cmd):
        cmd = original_cmd.strip()
        if not cmd: return

        # Resolve scrcpy if typed
        if cmd.lower().startswith("scrcpy "):
            cmd = cmd.replace("scrcpy ", f'"{SCRCPY}" ', 1)

        # Handling 'cd' manually (Sync for entire session)
        if cmd.lower().startswith("cd "):
            parts = cmd.split()
            target = " ".join(parts[1:]).replace('"', '')
            if target.lower().startswith("cd "): target = target[3:].strip()
            if os.path.isdir(target):
                self.terminal_cwd = os.path.abspath(target)
                self.log(f"\n📂 Path changed to: {self.terminal_cwd}")
            elif not target:
                self.log(f"\n📂 Current: {self.terminal_cwd}")
            else:
                self.log(f"\n❌ Directory not found: {target}")
            return

        # Determine targets
        if self.current_serial:
            targets = [self.current_serial]
            global_cmds = ["devices", "kill-server", "start-server", "connect", "pair", "mdns", "version", "help"]
            is_global = any(cmd.lower().startswith(f"adb {gc}") for gc in global_cmds)
            if self.c_broadcast.get() and not is_global:
                targets = list(set(self.devices_map.values()))
        else:
            if not self.c_broadcast.get():
                self.log("⚠️ No device selected to run command.")
                return
            targets = list(set(self.devices_map.values()))

        if not targets:
            self.log("⚠️ No active devices found for command.")
            return

        for serial in targets:
            # Re-resolve 'adb' for each serial to inject correct -s flag
            final_cmd = cmd
            if "adb " in original_cmd.lower():
                base_adb = f'"{ADB}"'
                global_cmds = ["devices", "kill-server", "start-server", "connect", "pair", "mdns", "version", "help"]
                is_global = any(original_cmd.lower().startswith(f"adb {gc}") for gc in global_cmds)
                
                if not is_global:
                    final_cmd = original_cmd.replace("adb ", f'{base_adb} -s {serial} ', 1)
                else:
                    final_cmd = original_cmd.replace("adb ", f'{base_adb} ', 1)

            d_name = self._get_display_name(serial)
            self.log(f"\n{self.terminal_cwd} [{d_name}]> {final_cmd}")
            
            def _run(c, s, dn):
                try:
                    env = os.environ.copy()
                    if self.custom_path:
                        env["PATH"] = f"{self.custom_path}{os.pathsep}{env.get('PATH', '')}"

                    res = subprocess.run(c, capture_output=True, text=True, cwd=self.terminal_cwd, 
                                         env=env, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.stdout: self.log(f"[{dn}] {res.stdout.strip()}")
                    if res.stderr: self.log(f"[{dn}] ERR: {res.stderr.strip()}")
                    if res.returncode == 0 and "input keyevent" in c:
                        self.log(f"✅ Shortcut Sent to {dn}")
                except Exception as e: self.log(f"[{dn}] FAIL: {str(e)}")
            
            threading.Thread(target=lambda c=final_cmd, s=serial, dn=d_name: _run(c, s, dn), daemon=True).start()

    def log(self, message):
        self.log_queue.put(message)

    def _get_display_name(self, serial):
        """Returns a user-friendly name for a given device serial, stripping technical noise."""
        if not serial or serial == "No devices found": return "Unknown"
        
        # 1. Try to find the friendly name from our mapping
        for name, s in self.devices_map.items():
            if s == serial:
                # Extract the model part (e.g., "Pixel 7" from "Pixel 7 (Wifi) [serial]")
                return name.split("(")[0].strip() if "(" in name else name

        # 2. Cleanup common wireless service noise
        clean_name = serial
        if "._adb-tls-connect._tcp" in clean_name:
            clean_name = clean_name.split("._adb")[0]
        if ".local" in clean_name:
            clean_name = clean_name.replace(".local", "")
            
        return clean_name

    def _process_log_queue(self):
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.console_log.configure(state="normal")
                
                # Truncate history
                line_count = int(self.console_log.index('end-1c').split('.')[0])
                if line_count > 2000:
                    self.console_log.delete("1.0", "501.0")
                    self.console_log.insert("1.0", "--- Truncated to maintain performance ---\n")
                
                self.console_log.insert("end", f"{message}\n")
                self.console_log.see("end")
                self.console_log.configure(state="disabled")
        except:
            pass
        self.after(100, self._process_log_queue)

    # --- Tab Setups ---

    def setup_devices_tab(self, parent):
        ctk.CTkLabel(parent, text="Connect & Select Device", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 5))
        
        # (Redundant dropdown moved to Global Header)
        
        ctk.CTkButton(parent, text="🔄 Refresh Devices List", width=450, height=45, font=ctk.CTkFont(size=13, weight="bold"), 
                      fg_color="#333", hover_color="#444", border_width=1, border_color="#555",
                      command=self.refresh_devices).pack(pady=10)

        qa_row = ctk.CTkFrame(parent, fg_color="transparent")
        qa_row.pack(fill="x", padx=40, pady=5)
        
        def add_q(text, cmd):
            ctk.CTkButton(qa_row, text=text, width=110, height=28, font=ctk.CTkFont(size=11), fg_color="transparent", border_width=1, command=lambda: self.run_shell_cmd(cmd)).pack(side="left", padx=5)

        add_q("List IPs", "adb shell ip -f inet addr show wlan0")
        add_q("Kill Server", "adb kill-server")
        add_q("Port Forward", "adb tcpip 5555")

        ctk.CTkFrame(parent, height=2, fg_color="gray25").pack(fill="x", padx=40, pady=20)

        ctk.CTkLabel(parent, text="🌍 Remote ADB Connection", font=ctk.CTkFont(weight="bold", size=15)).pack(anchor="w", padx=40)
        
        ip_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ip_frame.pack(fill="x", padx=40, pady=5)
        
        self.c_low_bw = ctk.CTkCheckBox(parent, text="⚡ Low Bandwidth (Tailscale/Remote Mode)", 
                                         font=ctk.CTkFont(size=11), text_color="gray")
        self.c_low_bw.pack(pady=2)
        if self.config.get("low_bw", False): self.c_low_bw.select()

        self.manual_ip_entry = ctk.CTkEntry(ip_frame, placeholder_text="IP (e.g. 192.168.1.5)", height=36, width=200)
        self.manual_ip_entry.pack(side="left", padx=(0, 10))

        self.opt_history = ctk.CTkOptionMenu(ip_frame, values=self.history if self.history else ["History"], width=120, height=36, command=self._on_history_select)
        self.opt_history.pack(side="left", padx=(0, 10))

        self.manual_port_entry = ctk.CTkEntry(ip_frame, placeholder_text="5555", width=70, height=36)
        self.manual_port_entry.insert(0, "5555")
        self.manual_port_entry.pack(side="left")

        ctk.CTkButton(parent, text="🔗 Establish Connection", width=450, height=45, fg_color="#3B8EDB", command=self._manual_connect).pack(pady=10)
        
        self.btn_help = ctk.CTkButton(parent, text="❓ Help with Remote Setup", 
                                     font=ctk.CTkFont(size=11), 
                                     fg_color="#333", hover_color="#444", border_width=1, border_color="#555",
                                     command=self.show_internet_help)
        self.btn_help.pack(pady=5)

    def _on_history_select(self, choice):
        if choice != "History":
            self.manual_ip_entry.delete(0, 'end')
            self.manual_ip_entry.insert(0, choice)

    def _manual_connect(self):
        raw_ip = self.manual_ip_entry.get().strip()
        raw_port = self.manual_port_entry.get().strip() or "5555"
        
        if raw_ip:
            # Handle user pasting host:port into IP box
            target_ip = raw_ip
            target_port = raw_port
            if ":" in raw_ip:
                parts = raw_ip.split(":")
                target_ip = parts[0]
                target_port = parts[1]
                
            self.log(f"🔗 Establishing direct connection to {target_ip}:{target_port}...")
            threading.Thread(target=lambda: connect(target_ip, self.log, manual_port=target_port), daemon=True).start()
            save_to_history(target_ip)
            self.refresh_devices()

    def setup_pair_tab(self, parent):
        ctk.CTkLabel(parent, text="Wireless Pairing (QR Method)", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        self.qr_label = ctk.CTkLabel(parent, text="[QR Code Area]", width=280, height=280, fg_color="#111", corner_radius=10)
        self.qr_label.pack(pady=10)
        ctk.CTkButton(parent, text="✨ Generate Sync QR", width=250, height=45, fg_color="#3B8EDB", font=ctk.CTkFont(size=13, weight="bold"), command=self.generate_and_scan).pack(pady=10)
        ctk.CTkFrame(parent, height=2, fg_color="gray25").pack(fill="x", padx=80, pady=15)
        m_row = ctk.CTkFrame(parent, fg_color="transparent")
        m_row.pack(pady=10)
        self.manual_pair_ip = ctk.CTkEntry(m_row, placeholder_text="IP:Port", width=150)
        self.manual_pair_ip.pack(side="left", padx=5)
        self.manual_pair_code = ctk.CTkEntry(m_row, placeholder_text="Code", width=100)
        self.manual_pair_code.pack(side="left", padx=5)
        ctk.CTkButton(parent, text="Pair with Code", command=self._manual_pair_task, border_width=1, fg_color="transparent").pack()

    def setup_settings_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, height=450)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure((0, 1), weight=1)

        # Load stored settings
        self.config = load_settings()

        # Warning
        ctk.CTkLabel(scroll, text="⚠️ Close Scrcpy window to apply new settings", font=ctk.CTkFont(size=12, slant="italic"), text_color="#FFB900").grid(row=0, column=0, columnspan=2, pady=(10, 0))

        def add_header(p, icon, text, r):
            ctk.CTkLabel(p, text=f"{icon} {text}", font=ctk.CTkFont(weight="bold", size=14), text_color="#3B8EDB").grid(row=r, column=0, columnspan=2, pady=(20, 10), sticky="w", padx=10)

        def add_opt(p, name, text, values, r, c):
            ctk.CTkLabel(p, text=text, font=ctk.CTkFont(weight="bold", size=11), text_color="gray").grid(row=r, column=c, padx=15, pady=(5, 0), sticky="w")
            o = ctk.CTkOptionMenu(p, values=values, height=32, width=180)
            o.grid(row=r+1, column=c, padx=15, pady=(0, 5), sticky="ew")
            # Apply stored value
            stored = self.config.get(name)
            if stored and stored in values: o.set(stored)
            return o

        def add_chk(p, name, text, r, c, default=False):
            cb = ctk.CTkCheckBox(p, text=text)
            cb.grid(row=r, column=c, padx=15, pady=5, sticky="w")
            # Apply stored value
            stored = self.config.get(name, default)
            if stored: cb.select()
            else: cb.deselect()
            return cb

        r = 1
        add_header(scroll, "🎥", "Video Pipeline", r); r += 1
        self.o_v_source = add_opt(scroll, "v_source", "Video Source", ["display (Default)", "camera"], r, 0)
        self.o_v_codec  = add_opt(scroll, "v_codec", "Video Codec", ["h264 (Default)", "h265", "av1"], r, 1); r += 2
        self.o_v_bit    = add_opt(scroll, "v_bit", "Video Bitrate", ["8M (Default)", "16M", "24M", "2M", "Unlimited"], r, 0)
        self.o_v_res    = add_opt(scroll, "v_res", "Max Resolution", ["Original (0)", "1920", "1080", "720", "480"], r, 1); r += 2
        self.o_v_fps    = add_opt(scroll, "v_fps", "Max FPS", ["Unlimited", "120", "60", "30", "15"], r, 0)
        self.o_v_orient = add_opt(scroll, "v_orient", "Display Orientation", ["Auto", "0 (Natural)", "90 (Left)", "180 (Inverted)", "270 (Right)"], r, 1); r += 2

        add_header(scroll, "📷", "Camera Tweaks", r); r += 1
        self.o_cam_face = add_opt(scroll, "cam_face", "Camera Facing", ["Any", "Front", "Back", "External"], r, 0)
        self.o_cam_ar   = add_opt(scroll, "cam_ar", "Camera Aspect Ratio", ["Auto", "4:3", "16:9", "1:1"], r, 1); r += 2

        add_header(scroll, "🎤", "Audio Pipeline", r); r += 1
        self.c_audio   = add_chk(scroll, "audio_en", "Enable Audio", r, 0, True)
        self.o_a_codec = add_opt(scroll, "a_codec", "Audio Codec", ["opus (Default)", "aac", "flac", "raw"], r, 1); r += 2
        self.o_a_src   = add_opt(scroll, "a_src", "Audio Source", ["output (Default)", "mic"], r, 0); r += 2

        add_header(scroll, "⌨️", "Input Spoofing", r); r += 1
        self.o_k_mode = add_opt(scroll, "k_mode", "Keyboard Mode", ["sdk (Default)", "uhid", "aoa"], r, 0)
        self.o_m_mode = add_opt(scroll, "m_mode", "Mouse Mode", ["sdk (Default)", "uhid", "aoa"], r, 1); r += 2
        
        self.c_no_clip = add_chk(scroll, "no_clip", "No Clipboard Autosync", r, 0)
        self.c_legacy  = add_chk(scroll, "legacy_v", "Legacy Paste (Fixes Ctrl+v)", r, 1); r += 1

        add_header(scroll, "🔲", "Window & Device", r); r += 1
        self.c_screenoff = add_chk(scroll, "screen_off", "Turn off screen", r, 0)
        self.c_awake     = add_chk(scroll, "stay_awake", "Stay Awake", r, 1); r += 1
        self.c_full      = add_chk(scroll, "fullscreen", "Fullscreen", r, 0)
        self.c_touches   = add_chk(scroll, "show_touch", "Show Touches", r, 1); r += 1
        self.c_top       = add_chk(scroll, "stay_top", "Always on Top", r, 0)
        self.c_readonly  = add_chk(scroll, "read_only", "Read-Only Mode", r, 1); r += 1

        # Reset Button
        ctk.CTkFrame(scroll, height=2, fg_color="gray25").grid(row=r, column=0, columnspan=2, pady=15, sticky="ew")
        r += 1
        ctk.CTkButton(scroll, text="🔄 Reset All Settings to Default", 
                      fg_color="transparent", border_width=1, border_color="#C42B1C", text_color="#C42B1C",
                      command=self.reset_settings_ui).grid(row=r, column=0, columnspan=2, pady=10)

    def reset_settings_ui(self):
        # Delete JSON first
        path = os.path.join(get_exe_dir(), "settings.json")
        if os.path.exists(path): os.remove(path)
        
        # Reset Widgets to Defaults
        self.o_v_source.set("display (Default)")
        self.o_v_codec.set("h264 (Default)")
        self.o_v_bit.set("8M (Default)")
        self.o_v_res.set("Original (0)")
        self.o_v_fps.set("Unlimited")
        self.o_v_orient.set("Auto")
        self.o_cam_face.set("Any")
        self.o_cam_ar.set("Auto")
        self.c_audio.select()
        self.o_a_codec.set("opus (Default)")
        self.o_a_src.set("output (Default)")
        self.o_k_mode.set("sdk (Default)")
        self.o_m_mode.set("sdk (Default)")
        
        for chk in [self.c_no_clip, self.c_legacy, self.c_screenoff, self.c_awake, 
                    self.c_full, self.c_touches, self.c_top, self.c_readonly]:
            chk.deselect()
        self.log("♻️ All settings reset to default.")

    def setup_advanced_tab(self, parent):
        scroll_adv = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_adv.pack(fill="both", expand=True, padx=20, pady=10)

        # 📹 Recording Configuration
        ctk.CTkLabel(scroll_adv, text="📹 Automated Recording", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3B8EDB").pack(pady=(10, 5))
        self.c_record = ctk.CTkCheckBox(scroll_adv, text="Auto-Record Session to PC")
        self.c_record.pack(pady=5)
        
        r_frame = ctk.CTkFrame(scroll_adv, fg_color="transparent")
        r_frame.pack(pady=5, fill="x")
        self.record_path_var = ctk.StringVar(value=self.config.get("record_path", os.path.expanduser("~\\Videos")))
        ctk.CTkEntry(r_frame, textvariable=self.record_path_var, width=350).pack(side="left", padx=5)
        ctk.CTkButton(r_frame, text="Browse", width=80, height=28, command=self._pick_save_folder, border_width=1, fg_color="transparent").pack(side="left")
        
        # Expert Flags
        ctk.CTkLabel(scroll_adv, text="Expert CLI Flags", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(30, 5))
        self.custom_flags_entry = ctk.CTkEntry(scroll_adv, width=450, placeholder_text="--no-clipboard-autosync --window-borderless")
        self.custom_flags_entry.pack(pady=10)
        stored = self.config.get("custom_flags", "")
        if stored: self.custom_flags_entry.insert(0, stored)

        ctk.CTkFrame(scroll_adv, height=2, fg_color="gray25").pack(fill="x", pady=20)

        # ⚙️ Overrides (Discreet)
        ctk.CTkButton(scroll_adv, text="⚙️ Override Bundled Tools (Advanced)", width=200, height=24, 
                      font=ctk.CTkFont(size=10), fg_color="transparent", border_width=1, 
                      command=self.show_binary_overrides).pack(pady=10)

        ctk.CTkFrame(scroll_adv, height=2, fg_color="gray25").pack(fill="x", pady=20)

        # 📂 Premium Utility Actions
        ctk.CTkLabel(scroll_adv, text="📂 App Utilities", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
        
        u_frame = ctk.CTkFrame(scroll_adv, fg_color="transparent")
        u_frame.pack(pady=10)

        ctk.CTkButton(u_frame, text="📁 Open App Folder", width=180, height=35, 
                      fg_color="#333", border_width=1, command=lambda: os.startfile(get_exe_dir())).pack(side="left", padx=10)
        
        ctk.CTkButton(u_frame, text="🛠️ Reset All Settings", width=180, height=35, 
                      fg_color="transparent", border_width=1, border_color="#C42B1C", text_color="#C42B1C",
                      command=self.reset_all_settings).pack(side="left", padx=10)

    def show_binary_overrides(self):
        win = ctk.CTkToplevel(self)
        win.title("Binary Tool Overrides")
        win.geometry("500x250")
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="📍 Manual Binary Paths", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=15)
        ctk.CTkLabel(win, text="Only change these if you want to use a different version\nof ADB or Scrcpy than what is bundled.", 
                      font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 15))

        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(pady=10, fill="x", padx=20)

        # Labels need to be updated live
        self.adb_ov_label = ctk.CTkLabel(f, text=f"ADB: {os.path.basename(ADB)}", font=ctk.CTkFont(size=12))
        self.adb_ov_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkButton(f, text="Set ADB", width=100, command=self._pick_adb_path_ov).grid(row=0, column=1, padx=10)

        self.scr_ov_label = ctk.CTkLabel(f, text=f"Scrcpy: {os.path.basename(SCRCPY)}", font=ctk.CTkFont(size=12))
        self.scr_ov_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkButton(f, text="Set Scrcpy", width=100, command=self._pick_scrcpy_path_ov).grid(row=1, column=1, padx=10)

    def _pick_adb_path_ov(self):
        f = filedialog.askopenfilename(title="Select adb.exe", filetypes=[("Executable Files", "*.exe")])
        if f:
            global ADB
            ADB = f
            if hasattr(self, 'adb_ov_label'): self.adb_ov_label.configure(text=f"ADB: {os.path.basename(f)}")
            self.log(f"✅ ADB path overridden: {f}")
            self.save_all_settings()

    def _pick_scrcpy_path_ov(self):
        f = filedialog.askopenfilename(title="Select scrcpy.exe", filetypes=[("Executable Files", "*.exe")])
        if f:
            global SCRCPY
            SCRCPY = f
            if hasattr(self, 'scr_ov_label'): self.scr_ov_label.configure(text=f"Scrcpy: {os.path.basename(f)}")
            self.log(f"✅ Scrcpy path overridden: {f}")
            self.save_all_settings()

    def setup_shortcuts_tab(self, parent):
        parent.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        def add_head(txt, r):
            ctk.CTkLabel(parent, text=txt, font=ctk.CTkFont(size=12, weight="bold"), text_color="#3B8EDB").grid(row=r, column=0, columnspan=5, pady=(6, 2), sticky="w")

        def add_btn(txt, cmd, r, c, color="#333", w=110):
            btn = ctk.CTkButton(parent, text=txt, height=28, width=w, font=ctk.CTkFont(size=11), 
                                fg_color=color, border_width=1, border_color="#444",
                                command=lambda: self.run_shell_cmd(cmd))
            btn.grid(row=r, column=c, padx=2, pady=1, sticky="ew")
            return btn

        row = 0
        # Category 1: Navigation
        add_head("📱 Navigation", row); row += 1
        add_btn("🏠 Home", "adb shell input keyevent 3", row, 0)
        add_btn("⬅️ Back", "adb shell input keyevent 4", row, 1)
        add_btn("📋 Recents", "adb shell input keyevent 187", row, 2)
        add_btn("☰ Menu", "adb shell input keyevent 82", row, 3)
        add_btn("🔍 Search", "adb shell input keyevent 84", row, 4); row += 1

        # Category 2: System
        add_head("🔋 Power & System", row); row += 1
        add_btn("⚡ Power", "adb shell input keyevent 26", row, 0, color="#C42B1C")
        add_btn("💡 Wake", "adb shell input keyevent 224", row, 1)
        add_btn("🌙 Sleep", "adb shell input keyevent 223", row, 2)
        add_btn("🔄 Reboot", "adb reboot", row, 3)
        add_btn("🔒 Lock", "adb shell input keyevent 276", row, 4); row += 1

        # Category 3: Media
        add_head("🎵 Audio & Media", row); row += 1
        add_btn("🔊 Vol +", "adb shell input keyevent 24", row, 0)
        add_btn("🔉 Vol -", "adb shell input keyevent 25", row, 1)
        add_btn("🔇 Mute", "adb shell input keyevent 164", row, 2)
        add_btn("⏯️ Play/Pause", "adb shell input keyevent 85", row, 3)
        add_btn("⏭️ Next", "adb shell input keyevent 87", row, 4); row += 1

        # Category 4: UI
        add_head("🖼️ UI & Display", row); row += 1
        add_btn("🔔 Notifs", "adb shell cmd statusbar expand-notifications", row, 0)
        add_btn("⚙️ Quick Set", "adb shell cmd statusbar expand-settings", row, 1)
        add_btn("🌙 Screen Off", "adb shell input keyevent 26", row, 2)
        add_btn("☕ Stay Awake", "adb shell svc power stayon true", row, 3)
        add_btn("📸 Screen", "adb shell screencap -p /sdcard/s.png", row, 4); row += 1

        # Category 5: Launch
        add_head("🚀 Quick Launch", row); row += 1
        add_btn("🌐 Browser", "adb shell am start -a android.intent.action.VIEW -d http://google.com", row, 0)
        add_btn("⚙️ Settings", "adb shell am start -n com.android.settings/.Settings", row, 1)
        add_btn("📅 Calendar", "adb shell am start -a android.intent.action.MAIN -c android.intent.category.APP_CALENDAR", row, 2)
        add_btn("🎵 Music", "adb shell am start -a android.intent.action.MAIN -c android.intent.category.APP_MUSIC", row, 3)
        add_btn("👥 Contacts", "adb shell am start -a android.intent.action.MAIN -c android.intent.category.APP_CONTACTS", row, 4); row += 1

        # Legend Popup Button at bottom
        ctk.CTkButton(parent, text="ⓘ Scrcpy Shortcuts Help", height=22, width=150, 
                      font=ctk.CTkFont(size=10, slant="italic"), fg_color="transparent", 
                      border_width=1, command=self.show_shortcuts_help).grid(row=row, column=4, pady=(10, 0), sticky="e")

    def show_shortcuts_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Keyboard Shortcuts Reference")
        win.geometry("500x600")
        win.attributes("-topmost", True)
        
        t = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#111", text_color="#AAA")
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert("0.0", SHORTCUTS_TEXT)
        t.configure(state="disabled")

    # --- Actions ---

    def on_device_select(self, choice):
        if choice in self.devices_map:
            self.current_serial = self.devices_map[choice]

    def refresh_devices(self):
        # Debounce: Prevent rapid-fire refreshes (at least 1s gap)
        now = time.time()
        if hasattr(self, "_last_refresh") and now - self._last_refresh < 1.0:
            return
        self._last_refresh = now

        self.log("🔄 Refreshing device list...")
        def _poll():
            res = subprocess.run([ADB, "devices", "-l"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            live_map = {}
            options = []
            
            # Step 1: Parse Live Devices
            for line in res.stdout.splitlines():
                if "device " in line and not line.startswith("List"):
                    parts = line.split()
                    serial = parts[0]
                    model = "Unknown"
                    for p in parts:
                        if p.startswith("model:"): model = p.replace("model:", "").replace("_", " ")
                    name = f"{model} ({'Wifi' if ':' in serial else 'USB'}) [{serial}]"
                    live_map[name] = serial
                    options.append(name)
                    # Save to persistent history
                    save_to_history(serial=serial, name=name)

            # Step 2: Merge with Known History
            history = load_history()["known_devices"]
            for serial, name in history.items():
                if name not in live_map:
                    offline_name = f"{name} (Offline)"
                    live_map[offline_name] = serial
                    options.append(offline_name)
            
            self.devices_map = live_map
            self.after(0, self._update_devices_ui, options)
        threading.Thread(target=_poll, daemon=True).start()

    def _update_devices_ui(self, options):
        if options:
            cur = self.opt_devices.get()
            self.opt_devices.configure(values=options)
            if cur in options:
                self.opt_devices.set(cur)
            else:
                self.opt_devices.set(options[0])
            self.current_serial = self.devices_map.get(self.opt_devices.get())
            self.log(f"✅ Device list updated ({len(options)} total)")
        else:
            self.opt_devices.configure(values=["No devices found"])
            self.opt_devices.set("No devices found")
            self.current_serial = None
            self.log("⚠️ No devices detected.")

    def launch_scrcpy(self):
        if not self.current_serial:
            self.log("⚠️ No device selected!")
            return

        choice = self.opt_devices.get()
        serial = self.current_serial
        
        args = self.get_scrcpy_args()
        cmd = [SCRCPY] + args
        
        def _task():
            # Auto-reconnect if offline and is a IP:Port
            if "(Offline)" in choice and ":" in serial:
                self.log(f"🔗 Re-establishing connection to {serial}...")
                ip = serial.split(":")[0]
                if not connect(ip, self.log):
                    self.log("❌ Failed to reconnect to offline device.")
                    return
            
            is_remote = ":" in serial or "._adb-tls-connect" in serial
            if is_remote:
                d_name = self._get_display_name(serial)
                self.log(f"🔌 Warming up transport for {d_name}...")
                subprocess.run([ADB, "connect", serial], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.save_all_settings() # Auto-save on launch
            d_name = self._get_display_name(serial)
            self.log(f"🚀 Launching Scrcpy for {d_name}...")
            self.log(f"CMD: {' '.join(cmd)}")
            
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if res.returncode != 0:
                    err = res.stderr.strip() or res.stdout.strip()
                    self.log(f"❌ Scrcpy Error: {err}")
                    
                    # Audio Troubleshooting Hint
                    if "audio" in err.lower() or "codec" in err.lower():
                        self.log("💡 Audio Pipeline Failure detected. Tips:")
                        self.log("   - Switch codec to AAC in Settings > Audio Pipeline")
                        self.log("   - Check if your Android version is 11+")
                        self.log("   - Try disabling audio if launch continues to fail")

                    if "connect failed: closed" in err.lower() and is_remote:
                        self.log("💡 Detected connection closure. Attempting tunnel reset...")
                        subprocess.run([ADB, "disconnect", serial], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        subprocess.run([ADB, "connect", serial], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        self.log("♻️ Tunnel reset. Please try launching again.")
                else:
                    self.log(f"✅ Scrcpy session ended for {serial}")
            except Exception as e:
                self.log(f"❌ Critical Error: {str(e)}")

        threading.Thread(target=_task, daemon=True).start()

    def get_scrcpy_args(self):
        args = ["-s", self.current_serial]
        
        # Video Pipeline
        v_src = self.o_v_source.get()
        if "camera" in v_src: args.append("--video-source=camera")
        
        v_codec = self.o_v_codec.get().split()[0]
        if v_codec != "h264": args.append(f"--video-codec={v_codec}")
        
        v_bit = self.o_v_bit.get().split()[0]
        if v_bit != "8M" and v_bit != "Unlimited": args.extend(["-b", v_bit])
        
        v_res = self.o_v_res.get().split()[0]
        if v_res != "Original": args.extend(["-m", v_res])
        
        v_fps = self.o_v_fps.get()
        if v_fps != "Unlimited": args.append(f"--max-fps={v_fps}")
        
        v_orient = self.o_v_orient.get()
        if v_orient != "Auto":
            orient_map = {"0": "0", "90": "1", "180": "2", "270": "3"}
            for key, val in orient_map.items():
                if key in v_orient:
                    args.append(f"--lock-video-orientation={val}")
                    break

        # Camera Tweaks
        cam_face = self.o_cam_face.get().lower()
        if cam_face != "any": args.append(f"--camera-facing={cam_face}")
        
        cam_ar = self.o_cam_ar.get()
        if cam_ar != "Auto": args.append(f"--camera-ar={cam_ar}")

        # Audio Pipeline
        if not self.c_audio.get():
            args.append("--no-audio")
        else:
            a_codec = self.o_a_codec.get().split()[0]
            if a_codec != "opus": args.append(f"--audio-codec={a_codec}")
            
            a_src = self.o_a_src.get().split()[0]
            if a_src != "output": args.append(f"--audio-source={a_src}")

        # Input Spoofing
        k_mode = self.o_k_mode.get().split()[0]
        if k_mode != "sdk": args.append(f"--keyboard={k_mode}")        # Window & Device
        if self.c_screenoff.get(): args.append("-S")
        if self.c_awake.get(): args.append("-w")
        if self.c_full.get(): args.append("-f")
        if self.c_touches.get(): args.append("-t")
        if self.c_top.get(): args.append("--always-on-top")
        if self.c_readonly.get(): args.append("-n")

        # --- Premium & Stability Overrides ---
        if self.c_record.get():
            p = os.path.join(self.record_path_var.get(), f"rec_{int(time.time())}.mp4")
            args.extend(["-r", p])
        
        custom = self.custom_flags_entry.get().strip()
        if custom: args.extend(shlex.split(custom))

        if self.c_low_bw.get():
            # Apply Stable Presets for Remote/Tailscale (Forces low bitrate & resolution)
            args.extend(["--max-size", "1024", "--video-bit-rate", "2M", "--max-fps", "30"])
            # Only disable audio in low-bw if user hasn't explicitly enabled it
            if not self.c_audio.get():
                args.append("--no-audio")
            else:
                args.extend(["--audio-bit-rate", "64k"]) # Reduce audio bandwidth
        
        return args

    def disconnect_all(self):
        self.log("🔌 Disconnecting all ADB devices...")
        def _run():
            subprocess.run([ADB, "disconnect"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.refresh_devices()
        threading.Thread(target=_run, daemon=True).start()


    def _pick_save_folder(self):
        f = filedialog.askdirectory()
        if f: self.record_path_var.set(f)

    def generate_and_scan(self):
        self.log("📷 Generating Sync QR Code...")
        self.name = f"ADB_{generate_name()}"
        self.password = generate_password()
        
        qr_text = f"WIFI:T:ADB;S:{self.name};P:{self.password};;"
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(qr_text)
        img = qr.make_image().get_image()
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(280, 280))
        self.qr_label.configure(image=ctk_img, text="")
        
        self.log("📡 Listening for pairing signals...")
        threading.Thread(target=self.scan_thread_task, daemon=True).start()

    def scan_thread_task(self):
        zeroconf = Zeroconf()
        listener = AdbListener()
        browser = ServiceBrowser(zeroconf, "_adb-tls-pairing._tcp.local.", listener)
        
        start = time.time()
        while time.time() - start < 60:
            if listener.device_info:
                ip, port = listener.device_info
                self.log(f"✨ Detected pairing request from {ip}:{port}")
                if pair(ip, port, self.password, self.log):
                    connect(ip, self.log)
                    self.refresh_devices()
                break
            time.sleep(1)
        zeroconf.close()

    def _manual_pair_task(self):
        target = self.manual_pair_ip.get().strip()
        code = self.manual_pair_code.get().strip()
        if ":" in target and code:
            self.log(f"🔗 Attempting manual pair with {target}...")
            ip, port = target.split(":")
            threading.Thread(target=lambda: pair(ip, port, code, self.log), daemon=True).start()
        else:
            self.log("⚠️ Enter both IP:Port and 6-digit Code.")

    def show_internet_help(self):
        if hasattr(self, "help_win") and self.help_win.winfo_exists():
            self.help_win.deiconify()
            self.help_win.focus()
            return
            
        self.help_win = ctk.CTkToplevel(self)
        self.help_win.title("ADB Remote Connection Guide")
        self.help_win.geometry("650x700")
        self.help_win.attributes("-topmost", True)
        
        t = ctk.CTkTextbox(self.help_win, font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
        t.pack(fill="both", expand=True, padx=20, pady=20)
        t.insert("0.0", "ADB CONNECTION GUIDE:\n\n1. Port Forwarding (Method 1)\n2. ngrok Tunnel (Method 2)\n3. Tailscale VPN (Method 3 - Recommended)\n\nVisit tailscale.com for easy remote access.")
        t.configure(state="disabled")

    def reset_all_settings(self):
        """Clears all configuration files and restarts the application."""
        if messagebox.askyesno("Reset All Settings", "This will clear all saved preferences and history. Exit and reset?"):
            try:
                if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
                if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
                self.destroy()
                if getattr(sys, 'frozen', False):
                    os.startfile(sys.executable)
                else:
                    os.system(f'start python "{os.path.abspath(__file__)}"')
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reset: {str(e)}")

    def save_all_settings(self):
        """Serializes all application settings and window state to JSON."""
        try:
            data = {
                "v_source": self.o_v_source.get(),
                "v_codec": self.o_v_codec.get(),
                "v_bit": self.o_v_bit.get(),
                "v_res": self.o_v_res.get(),
                "v_fps": self.o_v_fps.get(),
                "v_orient": self.o_v_orient.get(),
                "cam_face": self.o_cam_face.get(),
                "cam_ar": self.o_cam_ar.get(),
                "audio_en": bool(self.c_audio.get()),
                "a_codec": self.o_a_codec.get(),
                "a_src": self.o_a_src.get(),
                "k_mode": self.o_k_mode.get(),
                "m_mode": self.o_m_mode.get(),
                "no_clip": bool(self.c_no_clip.get()),
                "legacy_v": bool(self.c_legacy.get()),
                "screen_off": bool(self.c_screenoff.get()),
                "stay_awake": bool(self.c_awake.get()),
                "fullscreen": bool(self.c_full.get()),
                "show_touch": bool(self.c_touches.get()),
                "stay_top": bool(self.c_top.get()),
                "read_only": bool(self.c_readonly.get()),
                "terminal_path": self.custom_path,
                "custom_flags": self.custom_flags_entry.get().strip(),
                "low_bw": bool(self.c_low_bw.get()),
                "record_path": self.record_path_var.get(),
                "window_geometry": self.geometry(),
                "adb_path": ADB,
                "scrcpy_path": SCRCPY
            }
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def on_closing(self):
        self.save_all_settings()
        self.destroy()

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = AdbApp()
    app.mainloop()
