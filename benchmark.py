import time
import queue
from unittest.mock import MagicMock

class MockConsoleLog:
    def __init__(self):
        self.state = "disabled"
        self.lines = 0
        self.content = []

    def configure(self, state):
        self.state = state

    def index(self, param):
        return f"{self.lines + 1}.0"

    def delete(self, start, end):
        self.lines -= 500

    def insert(self, pos, text):
        self.lines += text.count('\n')

    def see(self, pos):
        pass

class MockApp:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.console_log = MockConsoleLog()

    def after(self, ms, func):
        pass

    # Original version
    def _process_log_queue_original(self):
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

    # Optimized version
    def _process_log_queue_optimized(self):
        try:
            if not self.log_queue.empty():
                self.console_log.configure(state="normal")
                while not self.log_queue.empty():
                    message = self.log_queue.get_nowait()

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

def run_benchmark():
    app = MockApp()

    # Pre-fill queue
    for i in range(10000):
        app.log_queue.put(f"Message {i}")

    start_time = time.time()
    app._process_log_queue_original()
    orig_time = time.time() - start_time

    # Reset and pre-fill queue
    app.console_log.lines = 0
    for i in range(10000):
        app.log_queue.put(f"Message {i}")

    start_time = time.time()
    app._process_log_queue_optimized()
    opt_time = time.time() - start_time

    print(f"Original: {orig_time:.6f}s")
    print(f"Optimized: {opt_time:.6f}s")
    if orig_time > 0:
        print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")

run_benchmark()
