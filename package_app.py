import os
import subprocess
import sys

# Configuration
APP_NAME = "ScrcpyMaster"
SCRIPT_NAME = "adb_wifi_qr_gui.py"
ICON_PNG = "scrcpy_master_icon.png" # You'll need to copy the generated png here
ICON_ICO = "scrcpy_master.ico"

def log(msg):
    print(f"\n>>> {msg}\n" + "="*50)

def run(cmd):
    return subprocess.run(cmd, shell=True)

def main():
    log("Installing dependencies...")
    run(f"{sys.executable} -m pip install pyinstaller pillow customtkinter qrcode pillow zeroconf")

    if os.path.exists(ICON_PNG):
        log("Converting PNG to ICO...")
        run(f"{sys.executable} convert_icon.py {ICON_PNG} {ICON_ICO}")
    else:
        print(f"⚠️ Warning: {ICON_PNG} not found. Build will use default icon.")

    log(f"Building {APP_NAME} with PyInstaller...")
    
    # We use --onedir for better performance with binary dependencies
    # We bundle the 'tools' folder if it exists
    cmd = [
        "pyinstaller",
        "--noconsole",
        f"--name={APP_NAME}",
        f"--icon={ICON_ICO}" if os.path.exists(ICON_ICO) else "",
        "--add-data \".;.\"", # Include current directory files
        f"{SCRIPT_NAME}"
    ]
    
    run(" ".join(cmd))

    log("Build complete! Check the 'dist' folder.")
    print(f"\nNext Steps:\n1. Copy your 'tools' folder into: dist/{APP_NAME}/tools")
    print("2. Compile ScrcpyMasterInstaller.iss with Inno Setup to create the final installer.")

if __name__ == "__main__":
    main()
