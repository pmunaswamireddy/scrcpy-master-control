import os
import random
import string
import time
import subprocess
import sys
import qrcode
import asyncio
from zeroconf import ServiceBrowser, Zeroconf

def generate_name():
    charset = string.ascii_letters + string.digits
    part1 = ''.join(random.choice(charset) for _ in range(14))
    part2 = ''.join(random.choice(charset) for _ in range(6))
    return f"{part1}-{part2}"

def generate_password():
    charset = string.ascii_letters + string.digits
    return ''.join(random.choice(charset) for _ in range(21))

name = f"ADB_WIFI_{generate_name()}"
password = generate_password()

def show_qr():
    qr_text = f"WIFI:T:ADB;S:{name};P:{password};;"
    qr = qrcode.QRCode()
    qr.add_data(qr_text)
    qr.make(fit=True)
    qr.print_ascii()

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


def start_discover():
    print("🔍 Searching for ADB devices and waiting for scan qrcode...")
    zeroconf = Zeroconf()
    listener = AdbListener()
    browser = ServiceBrowser(zeroconf, "_adb-tls-pairing._tcp.local.", listener)
    try:
        while True:
            if listener.device_info:
                ip, port = listener.device_info
                print(f"✅ Found Device for pairing: {ip}:{port}")
                return ip, port
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        zeroconf.close()

def pair(ip, port):
    print(f"🔗 Pairing with ADB Device: {ip}:{port} {password}")
    result = subprocess.run(["adb", "pair", f"{ip}:{port}", password], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr.strip() or result.stdout.strip()}")
        return False
    print(f"✅ Pairing Success: {result.stdout.strip()}")
    return True

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
    semaphore = asyncio.Semaphore(1000)
    tasks = [scan_port(ip, port, semaphore) for port in range(30000, 45000)]
    for f in asyncio.as_completed(tasks):
        port = await f
        if port:
            res = subprocess.run(["adb", "connect", f"{ip}:{port}"], capture_output=True, text=True)
            if "connected to" in res.stdout.lower() or "already connected" in res.stdout.lower():
                return port
    return None

def connect(ip):
    subprocess.run(["adb", "kill-server"], capture_output=True)
    print(f"🔗 Connecting to ADB Device: {ip}")
    
    # Try resolving connect port using mDNS first
    zeroconf = Zeroconf()
    listener = AdbListener(target_ip=ip)
    browser = ServiceBrowser(zeroconf, "_adb-tls-connect._tcp.local.", listener)
    
    connect_port = None
    timeout = 10
    start_time = time.time()
    while time.time() - start_time < timeout:
        if listener.device_info:
            connect_port = listener.device_info[1]
            break
        time.sleep(0.5)
        
    zeroconf.close()
    
    if connect_port:
        print(f"✅ Found connect port via mDNS: {connect_port}")
        res = subprocess.run(["adb", "connect", f"{ip}:{connect_port}"], capture_output=True, text=True)
        print(res.stdout.strip())
        subprocess.run(["adb", "devices"])
        return True

    print("⚠️ mDNS connect port not found. Executing port scan fallback...")
    
    for attempt in range(1, 3):
        print(f"🔄 Scanning ports on {ip}...")
        try:
            connect_port = asyncio.run(scan_ports_async(ip))
        except Exception as e:
            pass
            
        if connect_port:
            print(f"✅ Connected to {ip}:{connect_port}")
            subprocess.run(["adb", "devices"])
            return True
            
        print("⚠️ No open port found or adb connect failed, checking previous connections...")
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        if ip in res.stdout:
            print("✅ Device already connected")
            return True
            
        subprocess.run(["adb", "kill-server"], capture_output=True)
    
    print("❌ Unable to connect to ADB device")
    return False

def main():
    print("📱 ADB Wireless Debugging & Scrcpy Launcher for Windows")
    print("Go to setting [Developer options] -> [Wireless debugging] -> [Pair device with QR code]")
    show_qr()
    
    try:
        ip, pair_port = start_discover()
        if pair(ip, pair_port):
            if connect(ip):
                print("🚀 Launching Scrcpy...")
                scrcpy_path = "scrcpy"
                fallback_scrcpy_dir = r"C:\Users\PMR\OneDrive\Desktop\scrcpy-win64-v3.3.4"
                
                # Check if it exists in the fallback path
                if os.path.exists(os.path.join(fallback_scrcpy_dir, "scrcpy.exe")):
                    scrcpy_path = os.path.join(fallback_scrcpy_dir, "scrcpy.exe")
                    
                try:
                    # Launch scrcpy so that it mirrors the device automatically
                    subprocess.run([scrcpy_path], check=True)
                except FileNotFoundError:
                    print("\n⚠️ 'scrcpy.exe' could not be found in PATH or in the specified fallback folder.")
                    print(f"Fallback checked: {fallback_scrcpy_dir}")
                    print("Make sure scrcpy is installed or place this executable in your scrcpy folder.")
                    # Keep console open to see the error
                    input("\nPress Enter to exit...")
            else:
                input("\nPress Enter to exit...")
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

if __name__ == "__main__":
    main()
