import os
import tkinter as tk

from src.ui.screens import COL_BG
from src.ui.network import NetworkStatus
from src.ui.weather import WeatherData, WeatherCondition

class BaseTile(tk.Canvas):
    """Base class for all tiles in the thermostat UI"""
    def __init__(self, parent, size, command=None):
        # Initialize canvas with consistent properties
        super().__init__(parent, width=size, height=size, 
                        bg=COL_BG, bd=0, highlightthickness=0)
        self._size = size
        if command:
            self.bind('<Button-1>', lambda e: command())

    def resize(self, size):
        """Handle resize events"""
        self._size = size
        self.config(width=size, height=size)
        self.draw(size)

    def draw(self, size):
        """Template method for subclasses to override"""
        self.delete('all')  # Clear canvas for redraw

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
    def __init__(self, parent, size, app, command=None):
        super().__init__(parent, size, command)
        self._condition: WeatherCondition | None = None
        app.weather_monitor.add_listener(self._on_weather_update)

    def draw(self, size):
        super().draw(size)
        if self._condition:
            self._draw_weather_icon(self._condition)

    def _on_weather_update(self, data: WeatherData) -> None:
        if not data:
            return
        if data.condition != self._condition:
            self._condition = data.condition
            self._draw_weather_icon(self._condition)

    def _draw_weather_icon(self, cond: WeatherCondition) -> None:
        # Simple canvas iconography (no external images), colored accent
        self.delete('wx_icon')
        w = self._size
        x = y = w / 2
        r = int(w * 0.28)

        # Choose color per condition
        palette = {
            WeatherCondition.CLEAR: '#FFC107',       # amber sun
            WeatherCondition.CLOUDS: '#90A4AE',      # blue-grey
            WeatherCondition.RAIN: '#42A5F5',        # blue
            WeatherCondition.DRIZZLE: '#64B5F6',
            WeatherCondition.THUNDERSTORM: '#FFB300',# amber lightning
            WeatherCondition.SNOW: '#E0F7FA',        # light cyan
            WeatherCondition.MIST: '#B0BEC5',
            WeatherCondition.FOG: '#B0BEC5',
            WeatherCondition.HAZE: '#B0BEC5',
            WeatherCondition.UNKNOWN: '#9E9E9E',
        }
        color = palette.get(cond, '#9E9E9E')

        # Clear sky: a sun
        if cond in (WeatherCondition.CLEAR,):
            self.create_oval(x-r, y-r, x+r, y+r, outline=color, width=4, tags='wx_icon')
            # sun rays
            for angle in range(0, 360, 45):
                rad = angle * 3.14159 / 180.0
                x1 = x + r * 1.2 * 0.7 * tk._tkinter.cos(rad) if hasattr(tk._tkinter, 'cos') else x + r * 1.2 * 0.7
                y1 = y + r * 1.2 * 0.7 * tk._tkinter.sin(rad) if hasattr(tk._tkinter, 'sin') else y + r * 1.2 * 0.7
            # Keep it simple: a filled circle
            self.create_oval(x-r, y-r, x+r, y+r, fill=color, outline=color, tags='wx_icon')
            return

        # Clouds: a cloud blob
        if cond in (WeatherCondition.CLOUDS, WeatherCondition.MIST, WeatherCondition.FOG, WeatherCondition.HAZE):
            # three overlapping ovals
            self.create_oval(x-r-10, y-10, x-r+40, y+20, fill=color, outline=color, tags='wx_icon')
            self.create_oval(x-20, y-20, x+30, y+20, fill=color, outline=color, tags='wx_icon')
            self.create_oval(x+10, y-5, x+r+20, y+25, fill=color, outline=color, tags='wx_icon')
            return

        # Rain / Drizzle: cloud + drops
        if cond in (WeatherCondition.RAIN, WeatherCondition.DRIZZLE, WeatherCondition.THUNDERSTORM):
            # cloud
            self.create_oval(x-r-10, y-10, x-r+40, y+20, fill='#90A4AE', outline='#90A4AE', tags='wx_icon')
            self.create_oval(x-20, y-20, x+30, y+20, fill='#90A4AE', outline='#90A4AE', tags='wx_icon')
            self.create_oval(x+10, y-5, x+r+20, y+25, fill='#90A4AE', outline='#90A4AE', tags='wx_icon')
            # drops / bolt
            if cond == WeatherCondition.THUNDERSTORM:
                # lightning bolt
                self.create_polygon(
                    x, y+25, x+8, y+25, x-5, y+50, x+2, y+50, x-10, y+75,
                    fill=color, outline=color, tags='wx_icon'
                )
            else:
                for i in range(-1, 2):
                    self.create_line(x+i*15, y+25, x+i*15-4, y+50, fill=color, width=3, tags='wx_icon')
            return

        # Snow: dots
        if cond == WeatherCondition.SNOW:
            self.create_oval(x-35, y-5, x-25, y+5, fill=color, outline=color, tags='wx_icon')
            self.create_oval(x-5, y+10, x+5, y+20, fill=color, outline=color, tags='wx_icon')
            self.create_oval(x+25, y-5, x+35, y+5, fill=color, outline=color, tags='wx_icon')
            return

        # Unknown: muted dot
        self.create_oval(x-6, y-6, x+6, y+6, fill=color, outline=color, tags='wx_icon')
        self.update()

class OutsideTempTile(BaseTile):
    """Third tile (3) - Shows outside temperature"""
    def __init__(self, parent, size, app):
        super().__init__(parent, size)
        self._temp_str: str = '--'
        # Cache units preference; fall back to metric
        self._units = getattr(getattr(app, 'cfg', None), 'weather', None)
        self._units = getattr(self._units, 'units', 'metric')
        app.weather_monitor.add_listener(self._on_weather_update)

    def draw(self, size):
        super().draw(size)
        font_size = max(12, int(size * 0.36))
        self.create_text(
            size // 2, size // 2,
            text=self._temp_str,
            fill='#FFFFFF',
            font=('TkDefaultFont', font_size, 'bold'),
        )

    def _on_weather_update(self, data: WeatherData) -> None:
        if not data:
            return
        # Choose appropriate units
        if self._units == 'imperial' and data.temp_f is not None:
            self._temp_str = f'{data.temp_f:.0f}°'
        elif data.temp_c is not None:
            self._temp_str = f'{data.temp_c:.0f}°'
        else:
            self._temp_str = '--'
        self.draw(self._size)

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