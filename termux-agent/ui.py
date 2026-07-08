"""
UI helpers untuk terminal: spinner, status log, dan warna dasar.
"""
import sys
import time
import itertools
import threading

NO_COLOR = False


def _c(text: str, code: str) -> str:
    if NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(t):    return _c(t, "96")
def green(t):   return _c(t, "92")
def yellow(t):  return _c(t, "93")
def red(t):     return _c(t, "91")
def bold(t):    return _c(t, "1")
def dim(t):     return _c(t, "2")
def magenta(t): return _c(t, "95")


class Spinner:
    """Animasi spinner untuk operasi yang memakan waktu."""
    def __init__(self, text: str, delay: float = 0.1):
        self.text = text
        self.delay = delay
        self._stop = threading.Event()
        self._thread = None

    def _spin(self):
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for frame in itertools.cycle(frames):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r  {frame} {self.text}")
            sys.stdout.flush()
            time.sleep(self.delay)
        # clear line
        sys.stdout.write("\r" + " " * (len(self.text) + 10) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread:
            self._thread.join()


def log_action(icon: str, name: str, detail: str = ""):
    """Cetak baris status aksi ke terminal."""
    if detail:
        print(f"  {icon} {bold(name)} {dim(detail)}")
    else:
        print(f"  {icon} {bold(name)}")


def log_done(name: str):
    """Cetak baris status aksi selesai."""
    print(f"  {green('✓')} {dim(name)}")
