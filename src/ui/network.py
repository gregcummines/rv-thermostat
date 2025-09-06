from enum import Enum
from typing import Callable, List
import socket
import tkinter as tk

class NetworkStatus(Enum):
    """Network connectivity states"""
    CONNECTED = 'ok'          # WiFi + Internet
    NO_INTERNET = 'no_internet'  # WiFi only
    DISCONNECTED = 'disconnected'  # No WiFi

class NetworkMonitor:
    """Monitors network connectivity and notifies listeners of changes"""
    def __init__(self, check_interval_ms: int = 1000):
        self._status = None
        self._interval = check_interval_ms
        self._listeners: List[Callable[[NetworkStatus], None]] = []

    def add_listener(self, callback: Callable[[NetworkStatus], None]) -> None:
        """Add listener and immediately notify with current status"""
        self._listeners.append(callback)
        # Send current status to new listener if we have one
        if self._status is not None:
            try:
                callback(self._status)
            except Exception as e:
                print(f"Error notifying new listener: {e}")

    def remove_listener(self, callback: Callable[[NetworkStatus], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def check_status(self) -> NetworkStatus:
        try:
            import subprocess
            result = subprocess.run(['iwconfig'], capture_output=True, text=True)
            if "ESSID:" not in result.stdout:
                return NetworkStatus.DISCONNECTED
            
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=1)
                return NetworkStatus.CONNECTED
            except OSError:
                return NetworkStatus.NO_INTERNET
                
        except Exception as e:
            print(f"Network check error: {e}")
            return NetworkStatus.DISCONNECTED

    def start_monitoring(self, app: tk.Misc) -> None:
        """Start periodic network status checking"""
        try:
            # Force initial status check and notify
            current = self.check_status()
            self._status = current
            # Notify all listeners of initial status
            for listener in self._listeners:
                try:
                    listener(current)
                except Exception as e:
                    print(f"Error in network status listener: {e}")
        except Exception as e:
            print(f"Error checking network status: {e}")
            
        # Schedule next check
        app.after(self._interval, lambda: self.start_monitoring(app))