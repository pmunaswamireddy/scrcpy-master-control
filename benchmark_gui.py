import time
import queue
import customtkinter as ctk

class BenchmarkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.log_queue = queue.Queue()
        self.console_log = ctk.CTkTextbox(self)
        self.console_log.pack()

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
    app = BenchmarkApp()

    # Pre-fill queue
    for i in range(1000):
        app.log_queue.put(f"Message {i}")

    start_time = time.time()
    app._process_log_queue_original()
    orig_time = time.time() - start_time

    # Reset and pre-fill queue
    app.console_log.configure(state="normal")
    app.console_log.delete("1.0", "end")
    app.console_log.configure(state="disabled")

    for i in range(1000):
        app.log_queue.put(f"Message {i}")

    start_time = time.time()
    app._process_log_queue_optimized()
    opt_time = time.time() - start_time

    print(f"Original: {orig_time:.6f}s")
    print(f"Optimized: {opt_time:.6f}s")
    if orig_time > 0:
        print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")

run_benchmark()
