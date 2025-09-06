import tkinter as tk

COL_BG='#000000'; COL_TEXT='#FFFFFF'; COL_FRAME='#FFFFFF'

class Pill(tk.Canvas):
    def __init__(self, parent, label_text, bg_hex, command=None):
        super().__init__(parent, bg=COL_BG, bd=0, highlightthickness=0, height=64, cursor='hand2')
        self._bg = bg_hex
        self._label_item = self.create_text(0, 0, text=label_text, fill='#FFFFFF',
                                            font=('DejaVu Sans', 14, 'normal'), tags=('pill_label',))
        self._value_item = self.create_text(0, 0, text='--° F', fill='#FFFFFF',
                                            font=('DejaVu Sans', 24, 'bold'), tags=('pill_value',))
        if command:
            self.bind('<Button-1>', lambda e: command())

    def set_value(self, value_text):
        self.itemconfigure(self._value_item, text=value_text)

    def resize(self, w, h):
        self.config(width=w, height=h)
        self.delete('pill_bg')
        r = max(18, h // 2)
        self.create_rectangle(r, 0, w - r, h, outline='', fill=self._bg, tags='pill_bg')
        self.create_oval(0, 0, 2*r, h, outline='', fill=self._bg, tags='pill_bg')
        self.create_oval(w - 2*r, 0, w, h, outline='', fill=self._bg, tags='pill_bg')

        # layout: small label on top, big value below
        label_fs = max(12, int(h * 0.28))
        value_fs = max(18, int(h * 0.46))
        self.itemconfigure(self._label_item, font=('DejaVu Sans', label_fs, 'normal'))
        self.itemconfigure(self._value_item,  font=('DejaVu Sans', value_fs, 'bold'))
        # vertical positions
        self.coords(self._label_item, w//2, int(h*0.35))
        self.coords(self._value_item,  w//2, int(h*0.72))
        # ensure text on top
        self.tag_raise(self._label_item); self.tag_raise(self._value_item)

class Router(tk.Frame):
    def __init__(self, root):
        super().__init__(root, bg=COL_BG); self.pack(fill='both', expand=True); self.screens={}; self.current=None
    def register(self,n,w): self.screens[n]=w
    def show(self,n):
        if self.current: self.screens[self.current].pack_forget()
        self.current=n; self.screens[n].pack(fill='both', expand=True)
