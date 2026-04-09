# Scrcpy Master Control Panel

> **A powerful, modern Windows GUI for mirroring and controlling multiple Android devices using [scrcpy](https://github.com/Genymobile/scrcpy) and ADB — with built-in wireless pairing, internet tunneling support, and comprehensive settings.**

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![scrcpy](https://img.shields.io/badge/scrcpy-3.3.4-orange)

---

### 🎯 Scrcpy Master v2.0.0 Enhancements
- **Global Header Control**: Switch target devices instantly from any tab using the persistent header selector.
- **📡 Broadcast (Batch) Mode**: Toggle "Broadcast to All" to send shortcuts and commands to every connected device simultaneously.
- **⚡ Tailscale Stability Mode**: One-click optimization for remote connections (Forces 1024p, 2M Bitrate, and 30fps. If Audio is enabled, it keeps it active but throttles it to 64k for low-latency mirroring over VPNs).
- **🚀 Turbo Performance**: Buffered UI logging using a background queue ensures the interface never lags, even during high-frequency terminal output.
- **📜 Smart Terminal History**: Full persistent history for console commands; use Up/Down arrows to navigate previous commands.
- **📂 Context-Aware Console**: Integrated terminal with `cd` awareness and automatic path resolution for `adb` and `scrcpy`.
- **🔌 Transport Warm-up**: Automated ADB "warming" logic to prevent "connect failed: closed" errors during remote session starts.

---

## 🚀 Installation

### Option A — Portable (Recommended, No Python Needed)

1. Download the latest **scrcpy** for Windows from the [scrcpy releases page](https://github.com/Genymobile/scrcpy/releases)
2. Download **`ADB_Wireless_GUI.exe`** from the [Releases](../../releases) section of this repo
3. Place `ADB_Wireless_GUI.exe` **inside the scrcpy folder**:
   ```
   📁 scrcpy-win64-v3.3.4\
       ├── scrcpy.exe
       ├── adb.exe
       └── ADB_Wireless_GUI.exe   ← drop it here
   ```
4. Run `ADB_Wireless_GUI.exe` — no Python, no install needed!

> If scrcpy is not found, the app will **automatically download** the latest version from GitHub on first launch.

---

### Option B — Run from Source

**Requirements:**
- Python 3.10+
- scrcpy installed and in PATH (or placed in same folder)

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/scrcpy-master-control.git
cd scrcpy-master-control

# Install dependencies
pip install customtkinter pillow qrcode zeroconf

# Run
python adb_wifi_qr_gui.py
```

**Build your own exe:**
```bash
pip install pyinstaller
python -m PyInstaller --onedir --noconsole --name "ScrcpyMaster" adb_wifi_qr_gui.py
```

### 📁 Portable Structure
For the best experience, ensure your directory looks like this:
```
📁 ScrcpyMaster-v2.0.0\
    ├── tools\ (Place adb.exe & scrcpy.exe here)
    ├── settings.json
    └── ScrcpyMaster.exe
```

---

## 📖 Quick Start Guide

### Connect via USB
1. Enable **USB Debugging** on your phone (`Settings → Developer Options → USB Debugging`)
2. Plug in USB → click **Refresh Devices**
3. Select your device from the dropdown
4. Click **🚀 Launch Scrcpy**

### Connect via Wi-Fi (Wireless Debugging)
1. Enable **Wireless Debugging** on your phone (`Settings → Developer Options → Wireless Debugging`)
2. Go to the **Pair New** tab → click **Generate QR Code**
3. On your phone, tap **"Pair device with QR code"** and scan

### Connect over the Internet (Tailscale — easiest)
1. Install [Tailscale](https://tailscale.com/download) on your PC and Android phone
2. Sign in with the same account on both
3. Connect phone via USB once and run: `adb tcpip 5555`, then unplug
4. In the **Devices** tab, enter your phone's Tailscale IP (`100.x.x.x`) and port `5555`
5. Click **Connect** → then **Refresh Devices**

---

## ⚠️ Notes
- Settings apply only on the **next scrcpy launch** — close the scrcpy window first before changing settings
- Camera features require **Android 12+**
- `adb tcpip 5555` must be re-run after each phone reboot for wireless/internet connections
- TCP mode survives reboots on some rooted devices

---

## 🛠️ Built With
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — modern dark UI
- [scrcpy](https://github.com/Genymobile/scrcpy) — the underlying screen mirror engine
- [zeroconf](https://github.com/jstasiak/python-zeroconf) — mDNS discovery for wireless pairing
- [qrcode](https://github.com/lincolnloop/python-qrcode) — QR generation for ADB pairing

---

## 📄 License
MIT License — feel free to fork, modify, and distribute.
