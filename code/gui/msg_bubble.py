import math
import tkinter as tk

class MessageBubble(tk.Frame):
    def __init__(
        self,
        master,
        text: str,
        max_width: int,
        style: str = "incoming",  # "incoming", "outgoing", "system"
        radius: int = 10,
        bg: str = "#0084ff",
        fg: str = "#ffffff",
        padding: tuple = (12, 8),
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.config(bg=bg, bd=0)

        styles = {
            "incoming": (False, True, True, True),
            "outgoing": (True, False, True, True),
            "system": (True, True, True, True),
        }
        self.corners = styles.get(style, styles["system"])
        self.radius = radius
        self.bg = bg
        self.padding = padding

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.lbl = tk.Label(
            self.canvas,
            text=text,
            bg=bg,
            fg=fg,
            wraplength=max_width,
            justify="left",
            font=("Arial", 13),
        )
        self.lbl_window = self.canvas.create_window(0, 0, window=self.lbl, anchor="nw")

        self.lbl.bind("<Configure>", self._resize)
        self._resize()

    def _resize(self, event=None):
        w = self.lbl.winfo_reqwidth()
        h = self.lbl.winfo_reqheight()
        tw = w + self.padding[0] * 2
        th = h + self.padding[1] * 2

        self.canvas.config(width=tw, height=th)
        self.canvas.coords(self.lbl_window, self.padding[0], self.padding[1])
        self._draw(tw, th)

    def _draw(self, w, h):
        self.canvas.delete("bg")
        r = min(self.radius, w / 2, h / 2)
        c = self.corners
        pts = []
        steps = 24

        def add_arc(cx, cy, start_ang, end_ang):
            for i in range(steps):
                ang = math.radians(start_ang + i * (end_ang - start_ang) / steps)
                pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

        if c[0]: add_arc(r, r, 180, 270)
        else: pts.append((0, 0))

        if c[1]: add_arc(w - r, r, 270, 360)
        else: pts.append((w, 0))

        if c[2]: add_arc(w - r, h - r, 0, 90)
        else: pts.append((w, h))

        if c[3]: add_arc(r, h - r, 90, 180)
        else: pts.append((0, h))

        flat_pts = [round(v, 1) for p in pts for v in p]

        self.canvas.create_polygon(flat_pts, fill=self.bg, outline="", smooth=True)
