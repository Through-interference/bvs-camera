"""Camera process lifecycle shared by the adaptive capture implementation."""
from collections import deque
import subprocess,threading

class Camera:
    def __init__(self):
        self.condition = threading.Condition()
        self.change_lock = threading.Lock()
        self.process = None
        self.generation = 0
        self.profile = 'medium'
        self.frame = None
        self.frames = 0
        self.last_frame = None
        self.error = None
        self.logs = deque(maxlen=12)
        self.closing = False
    def _stop_process(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
    def _read_errors(self, proc, generation):
        for line in proc.stderr:
            with self.condition:
                if generation != self.generation:
                    return
                self.logs.append(line.decode('utf-8', errors='replace').strip())
    def close(self):
        with self.change_lock:
            self.closing = True
            with self.condition:
                self.condition.notify_all()
            self._stop_process()
