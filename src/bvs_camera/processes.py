"""Shutdown process groups created by this transmitter."""
import os,signal,subprocess

def stop_children(children):
    for proc in reversed(children):
        if proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
    for proc in reversed(children):
        try:proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=3)
