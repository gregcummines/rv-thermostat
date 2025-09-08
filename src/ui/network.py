import logging
import socket
import subprocess
import tkinter as tk
from enum import Enum
from typing import Callable, List

class NetworkStatus(Enum):
    CONNECTED = 'ok'
    NO_INTERNET = 'no_internet'
    DISCONNECTED = 'disconnected'

class NetworkMonitor:
    """Monitors network connectivity and notifies listeners of changes"""
    def __init__(self, check_interval_ms: int = 1000):
        self._status: NetworkStatus | None = None
        self._interval = check_interval_ms
        self._listeners: List[Callable[[NetworkStatus], None]] = []
        self._app: tk.Misc | None = None
        self._running = False
        self._log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._log.info("NetworkMonitor init interval=%dms", check_interval_ms)

    def add_listener(self, callback: Callable[[NetworkStatus], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)
            if self._status is not None:
                try:
                    callback(self._status)
                except Exception:
                    pass

    def remove_listener(self, callback: Callable[[NetworkStatus], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def start_monitoring(self, app: tk.Misc) -> None:
        if self._running:
            return
        self._running = True
        self._app = app
        self._log.info("Starting monitor")
        self._tick()  # immediate first check

    def stop(self) -> None:
        self._running = False
        self._app = None
        self._log.info("Stopped monitor")

    def _schedule_next(self):
        if self._running and self._app:
            try:
                self._app.after(self._interval, self._tick)
            except Exception:
                pass

    def _tick(self):
        try:
            current = self.check_status()
            if current != self._status:
                self._log.info("Network status changed %s -> %s",
                               getattr(self._status, "name", None), current.name)
                self._status = current
                for listener in list(self._listeners):
                    try:
                        listener(current)
                    except Exception as e:
                        self._log.error("Listener error: %s", e)
        except Exception as e:
            self._log.exception("Network tick failed: %s", e)
            self._status = NetworkStatus.DISCONNECTED
        finally:
            self._schedule_next()

    def check_status(self) -> NetworkStatus:
        # Check Wi-Fi association
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=1.5)
            if "ESSID:" not in result.stdout:
                return NetworkStatus.DISCONNECTED
        except Exception as e:
            self._log.warning("iwconfig failed: %s", e)
            return NetworkStatus.DISCONNECTED

        # Check internet reachability
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return NetworkStatus.CONNECTED
        except OSError:
            return NetworkStatus.NO_INTERNET