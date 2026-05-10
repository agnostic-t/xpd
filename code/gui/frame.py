import tkinter as tk
import tkinter.ttk as ttk


class ScrollableFrame(ttk.Frame):
    def __init__(
        self,
        master=None,
        max_width: int | None = None,
        min_width: int = 10,
        adt_on_resize=None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.max_width = max_width
        self.min_width = min_width

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, width=1)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, relief="flat")
        self.adt_on_resize = adt_on_resize

        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        self.canvas.pack(side="left", fill="both")
        self.vsb.pack(side="right", fill="y")

        self.bind("<Configure>", self._on_frame_resize)

        self.inner.bind("<Configure>", self._on_inner_configure)

        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._on_mousewheel)
            w.bind("<Button-4>", self._on_mousewheel)
            w.bind("<Button-5>", self._on_mousewheel)

    def _stick_to_bottom(self):
        self.update_idletasks()

        bbox = self.canvas.bbox("all")

        if bbox is None:
            return

        self.canvas.coords(self.window_id, 0, 0)
        self.canvas.yview_moveto(1.0)

    def is_at_bottom(self, tolerance: int = 100) -> bool:
        self.update_idletasks()

        canvas_h = self.canvas.winfo_height()
        bbox = self.canvas.bbox("all")

        if bbox is None:
            return True

        content_h = bbox[3]

        if content_h <= canvas_h:
            return True

        yview = self.canvas.yview()

        distance_to_bottom = (1.0 - yview[1]) * content_h

        return distance_to_bottom <= tolerance

    def _on_frame_resize(self, event):
        sb_w = self.vsb.winfo_width() if self.vsb.winfo_width() > 1 else 16
        available_w = event.width - sb_w

        target_w = available_w

        if self.max_width:
            target_w = min(target_w, self.max_width)

        if self.min_width:
            target_w = max(target_w, self.min_width)

        if target_w > 0:
            self.canvas.config(width=target_w)
            self.canvas.itemconfig(self.window_id, width=target_w)

        if self.adt_on_resize:
            self.adt_on_resize()

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
