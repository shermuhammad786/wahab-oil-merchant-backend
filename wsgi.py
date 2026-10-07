import os
import sys
import threading

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_ROOT)
os.chdir(APP_ROOT)

_adapter = None
_adapter_pid = None
_lock = threading.Lock()


def application(environ, start_response):
    global _adapter, _adapter_pid
    pid = os.getpid()

    if _adapter is None or _adapter_pid != pid:
        with _lock:
            if _adapter is None or _adapter_pid != pid:
                from a2wsgi import ASGIMiddleware
                from main import app

                _adapter = ASGIMiddleware(app)
                _adapter_pid = pid

    return _adapter(environ, start_response)