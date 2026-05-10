import math
import tkinter as tk

class ContactCard(tk.Frame):
    def __init__(
        self,
        master,
        name: str,
        token: int,
        initial: str = "?",
        bg_normal="#f8f9fa",
        bg_hover="#e9ecef",
        bg_online="#8ce26b",
        command=None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.config(bd=0)
        self.bg_normal = bg_normal
        self.bg_hover = bg_hover
        self.current_bg = bg_normal
        self.command = command
        self.name = name
        self.token = token

        self.is_online = False
        self.bg_online = bg_online
        self.indicator_id = None

        self.bg_canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.avatar = tk.Canvas(
            self, width=36, height=36, highlightthickness=0, bd=0, bg=bg_normal
        )
        self.avatar.pack(side="left", padx=(12, 10), pady=10)
        self.avatar.create_oval(2, 2, 34, 34, fill="#3b82f6", outline="")
        self.avatar.create_text(
            18, 18, text=initial.upper(), fill="white", font=("Arial", 14, "bold")
        )

        self.name_lbl = tk.Label(
            self, text=name, bg=bg_normal, fg="#1f2937", font=("Arial", 14)
        )
        self.name_lbl.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=10)

        for w in (self, self.bg_canvas, self.avatar, self.name_lbl):
            w.bind("<Enter>", self._on_hover)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

        self.bind("<Configure>", lambda e: self._draw_bg())
        self._draw_bg()

    def set_status(self, is_online: bool):
        self.is_online = is_online

        if self.indicator_id:
            self.avatar.delete(self.indicator_id)
            self.indicator_id = None

        if self.is_online:
            self.indicator_id = self.avatar.create_oval(
                24, 24, 34, 34, fill=self.bg_online, outline="white", width=2
            )

    def _on_click(self, event):
        if self.command:
            self.command(self.token, self.name)

    def _draw_bg(self, color=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        fill = color if color else self.current_bg
        self.bg_canvas.delete("card_bg")

        r = 12
        pts =[]
        steps = 16

        def _arc(cx, cy, start_ang, end_ang):
            for i in range(steps):
                ang = math.radians(start_ang + i * (end_ang - start_ang) / steps)
                pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

        _arc(r, r, 180, 270)
        _arc(w - r, r, 270, 360)
        _arc(w - r, h - r, 0, 90)
        _arc(r, h - r, 90, 180)

        flat_pts = [round(v, 1) for p in pts for v in p]
        self.bg_canvas.create_polygon(
            flat_pts, fill=fill, outline="", smooth=True, tags="card_bg"
        )

    def _on_hover(self, event):
        if self.current_bg != self.bg_hover:
            self.current_bg = self.bg_hover
            self._apply_theme(self.bg_hover)

    def _on_leave(self, event):
        if self.current_bg != self.bg_normal:
            self.current_bg = self.bg_normal
            self._apply_theme(self.bg_normal)

    def _apply_theme(self, color):
        self._draw_bg(color)
        self.name_lbl.config(bg=color)
        self.avatar.config(bg=color)
