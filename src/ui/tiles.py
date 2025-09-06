import os
import tkinter as tk

from src.ui.screens import COL_BG
from src.ui.network import NetworkStatus

class BaseTile(tk.Canvas):
    """Base class for all tiles in the thermostat UI"""
    def __init__(self, parent, size, command=None):
        super().__init__(parent, width=size, height=size, 
                        bg=COL_BG, bd=0, highlightthickness=0)
        self._size = size
        if command:
            self.bind('<Button-1>', lambda e: command())
        self.draw(size)

    def draw(self, size):
        """Override in subclasses to draw tile content"""
        self.delete('all')
        self.config(width=size, height=size)
        self._size = size

    def resize(self, size):
        self.draw(size)

class WifiTile(BaseTile):
    """First tile (1) - Shows WiFi connection status"""
    def __init__(self, parent, size, app):
        self._status = None
        super().__init__(parent, size)
        app.network.add_listener(self._on_network_status)
        
    def draw(self, size):
        """Override draw method to ensure canvas is properly configured"""
        super().draw(size)  # Configure canvas size
        if self._status:  # Redraw icon if we have a status
            self._draw_wifi_icon(self._status)

    def _on_network_status(self, status: NetworkStatus) -> None:
        """Handle network status changes"""            
        if status != self._status:
            self._status = status
            self._draw_wifi_icon(status)

    def _draw_wifi_icon(self, status: NetworkStatus) -> None:
        """Draw the WiFi icon with appropriate color"""
        colors = {
            NetworkStatus.CONNECTED: '#00C853',    # green
            NetworkStatus.NO_INTERNET: '#0A3D91',  # blue
            NetworkStatus.DISCONNECTED: '#E53935',  # red
        }
        
        color = colors.get(status)
        if not color:
            self.delete('wifi_icon')
            return

        w = self._size
        icon_size = int(w * 0.8)
        x = w/2
        y = w/2
        
        self.delete('wifi_icon')
        
        # Draw three Wi-Fi arcs
        for radius_factor in (1/2, 1/3, 1/6):
            r = icon_size * radius_factor
            self.create_arc(x-r, y-r, x+r, y+r, 
                start=45, extent=90, style='arc', width=4, 
                outline=color, tags='wifi_icon')
        
        # Center dot
        dot_size = icon_size * 0.1
        self.create_oval(x-dot_size/2, y-dot_size/2, 
            x+dot_size/2, y+dot_size/2, 
            fill=color, outline=color, tags='wifi_icon')
        
        self.update()  # Force immediate update

class WeatherIndicationTile(BaseTile):
    """Second tile (2) - Shows weather condition icon"""
    def __init__(self, parent, size, command=None):
        self._img_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'weather.png')
        self._photo = None
        super().__init__(parent, size, command)

    # def draw(self, size):
    #     if os.path.exists(self._img_path):
    #         self._photo = tk.PhotoImage(file=self._img_path)
    #         iw = int(size * 0.58)
    #         try:
    #             self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
    #         except Exception:
    #             pass
    #         self.create_image(size//2, size//2, image=self._photo)

class OutsideTempTile(BaseTile):
    """Third tile (3) - Shows outside temperature"""
    def __init__(self, parent, size):
        self._temp = None
        super().__init__(parent, size)

class InformationTile(BaseTile):
    """Fourth tile (4) - Shows system information"""
    def __init__(self, parent, size, command=None):
        self._img_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'info.png')
        self._photo = None
        super().__init__(parent, size, command)

    def draw(self, size):
        if os.path.exists(self._img_path):
            self._photo = tk.PhotoImage(file=self._img_path)
            iw = int(size * 0.58)
            try:
                self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
            except Exception:
                pass
            self.create_image(size//2, size//2, image=self._photo)

# Right column tiles
class ReservedTile(BaseTile):
    """Fifth tile (5) - Reserved for future use"""
    def __init__(self, parent, size):
        super().__init__(parent, size)

class ModeSelectionTile(BaseTile):
    """Sixth tile (6) - Heat/Cool/Auto mode selection"""
    def __init__(self, parent, size, command=None):
        self._img_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'flame.png')
        self._photo = None
        super().__init__(parent, size, command)

    def draw(self, size):
        if os.path.exists(self._img_path):
            self._photo = tk.PhotoImage(file=self._img_path)
            iw = int(size * 0.58)
            try:
                self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
            except Exception:
                pass
            self.create_image(size//2, size//2, image=self._photo)

class FanSpeedSelectionTile(BaseTile):
    """Seventh tile (7) - Fan speed control"""
    def __init__(self, parent, size, command=None):
        self._img_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fan.png')
        self._photo = None
        super().__init__(parent, size, command)

    def draw(self, size):
        if os.path.exists(self._img_path):
            self._photo = tk.PhotoImage(file=self._img_path)
            iw = int(size * 0.58)
            try:
                self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
            except Exception:
                pass
            self.create_image(size//2, size//2, image=self._photo)

class SettingsTile(BaseTile):
    """Eighth tile (8) - System settings"""
    def __init__(self, parent, size, command=None):
        self._img_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'settings.png')
        self._photo = None
        super().__init__(parent, size, command)

    def draw(self, size):
        if os.path.exists(self._img_path):
            self._photo = tk.PhotoImage(file=self._img_path)
            iw = int(size * 0.58)
            try:
                self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
            except Exception:
                pass
            self.create_image(size//2, size//2, image=self._photo)