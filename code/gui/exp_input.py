import tkinter as tk
import tkinter.font as tkFont

class ExpandingInput(tk.Frame):
    def __init__(
        self,
        master=None,
        placeholder="Enter message...",
        min_height=1,
        max_height=5,
        font=None,
        on_send=None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self.min_h = min_height
        self.max_h = max_height
        self.on_send = on_send
        self.font = font or tkFont.Font(family="Arial", size=12)
        self.is_placeholder = True

        self.text = tk.Text(
            self,
            height=self.min_h,
            font=self.font,
            width=1,
            wrap="word",
            bd=0,
            highlightthickness=1,
            highlightbackground="#ccc",
            padx=5,
            pady=5,
        )
        self.text.pack(fill="both", expand=True, side="left")

        self.text.bind("<FocusIn>", self._on_focus_in)
        self.text.bind("<FocusOut>", self._on_focus_out)
        self.text.bind("<Key-Return>", self._on_return)
        self.text.bind("<Key>", self._auto_resize, add="+")
        self.text.bind("<KeyRelease-BackSpace>", self._auto_resize)
        self.text.bind("<KeyRelease-Delete>", self._auto_resize)

        self._set_placeholder()

    def _set_placeholder(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.placeholder)
        self.text.config(fg="grey", state="disabled")
        self.is_placeholder = True

    def _on_focus_in(self, event):
        if self.is_placeholder:
            self.text.config(state="normal", fg="black")
            self.text.delete("1.0", "end")
            self.is_placeholder = False

    def _on_focus_out(self, event):
        if not self.text.get("1.0", "end-1c").strip():
            self._set_placeholder()

    def _on_return(self, event):
        if self.is_placeholder:
            return "break"

        if event.state & 0x1:  # Shift+Enter
            self._auto_resize(event)
            return None

        content = self.text.get("1.0", "end-1c").strip()
        if content and self.on_send:
            self.on_send(content)

        self.text.delete("1.0", "end")
        self.text.config(height=self.min_h)

        self.text.config(state="normal")
        self.master.after(10, self.text.focus_set)
        return "break"

    def _auto_resize(self, event=None):
        content = self.text.get("1.0", "end-1c")
        lines = content.count("\n") + 1 if content else 1
        new_h = max(self.min_h, min(lines, self.max_h))
        if self.text.cget("height") != new_h:
            self.text.config(height=new_h)

    def get(self):
        return self.text.get("1.0", "end-1c").strip()
