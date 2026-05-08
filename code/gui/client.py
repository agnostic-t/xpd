import tkinter as tk
import tkinter.font as tkFont
import tkinter.ttk as ttk


class PlaceholderEntry(tk.Entry):
    def __init__(
        self,
        master=None,
        placeholder="PLACEHOLDER",
        color="grey",
        textvariable=None,
        **kwargs,
    ):
        super().__init__(master=master, textvariable=textvariable, **kwargs)

        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = self["fg"]

        self.bind("<FocusIn>", self.foc_in)
        self.bind("<FocusOut>", self.foc_out)
        self.put_placeholder()

    def put_placeholder(self):
        self.insert(0, self.placeholder)
        self["fg"] = self.placeholder_color

    def foc_in(self, *args):
        if self["fg"] == self.placeholder_color:
            self.delete("0", "end")
            self["fg"] = self.default_fg_color

    def foc_out(self, *args):
        if not self.get():
            self.put_placeholder()
            self["show"] = ""


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

        # Привязки
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

        if event.state & 0x1:
            self._auto_resize(event)
            return None

        content = self.text.get("1.0", "end-1c").strip()
        if content and self.on_send:
            self.on_send(content)

        self.text.delete("1.0", "end")
        self.text.config(height=self.min_h)
        self._on_focus_out(event)
        return "break"

    def _auto_resize(self, event=None):
        content = self.text.get("1.0", "end-1c")
        lines = content.count("\n") + 1 if content else 1
        new_h = max(self.min_h, min(lines, self.max_h))
        if self.text.cget("height") != new_h:
            self.text.config(height=new_h)

    def get(self):
        return self.text.get("1.0", "end-1c").strip()


class ScrollableFrame(ttk.Frame):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, width=1, height=1)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<Button-4>", self._on_mousewheel)
        self.inner.bind("<Button-5>", self._on_mousewheel)

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.window_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")


class MessageBubble(tk.Frame):
    def __init__(
        self,
        master,
        text: str,
        is_outgoing: bool = False,
        max_width: int = 350,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.config(bd=0)

        bg = "#0084ff" if is_outgoing else "#e5e5ea"
        fg = "#ffffff" if is_outgoing else "#000000"

        self.config(bg=bg, padx=10, pady=6)
        self.lbl = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            wraplength=max_width,
            justify="left",
            font=("Arial", 23),
        )
        self.lbl.pack(fill="both", expand=True)

        self.pack(anchor="e" if is_outgoing else "w", pady=3, padx=10)


class ContactCard(tk.Frame):
    def __init__(self, master, name: str, initial: str = "?", **kwargs):
        super().__init__(master, **kwargs)
        self.config(bg="#f8f9fa", bd=1, relief="solid", padx=10, pady=6, cursor="hand2")

        self.avatar = tk.Canvas(self, width=61, height=61, highlightthickness=0, bd=0)
        self.avatar.pack(side="left", padx=(0, 10))
        self.avatar.create_oval(1, 1, 60, 60, fill="#3b82f6", outline="")
        self.avatar.create_text(
            35, 35, text=initial.upper(), fill="white", font=("Arial", 18, "bold")
        )

        self.name_lbl = tk.Label(
            self, text=name, bg="#f8f9fa", fg="#1f2937", font=("Arial", 20)
        )
        self.name_lbl.pack(side="left", fill="x", expand=True)

        for w in (self, self.avatar, self.name_lbl):
            w.bind("<Enter>", self._hover)
            w.bind("<Leave>", self._unhover)

    def _hover(self, e):
        self.config(bg="#e9ecef")

    def _unhover(self, e):
        self.config(bg="#f8f9fa")


class GUIClient:
    def __init__(self, geo: tuple[int, int] = (800, 500)) -> None:
        self.root = tk.Tk()
        self.root.title("XTCli")
        self.root.geometry(f"{geo[0]}x{geo[1]}")

        self.sfont = tkFont.Font(family="Arial", size=25)
        self.contacts: ttk.Frame
        self.chat: ttk.Frame
        self.msg_label: ExpandingInput

        self.chat_scroll: ScrollableFrame
        self.contacts_scroll: ScrollableFrame

        self.current_contact: int = -1

        for c in range(3):
            self.root.columnconfigure(index=c, weight=1)
        for r in range(1):
            self.root.rowconfigure(index=r, weight=1)

    def build(self):
        self.contacts = ttk.Frame(
            master=self.root, borderwidth=1, relief=tk.RAISED, padding=(8, 10)
        )

        ttk.Label(
            master=self.contacts, text="Contacts", anchor="nw", font=self.sfont
        ).pack(side="top", fill="x")

        self.contacts_scroll = ScrollableFrame(master=self.contacts)
        self.contacts_scroll.pack(side="top", fill="both", expand=True)
        self.contacts.grid(row=0, column=0, sticky="nsew")

        self.chat = ttk.Frame(
            master=self.root, borderwidth=1, relief=tk.RAISED, padding=(2, 10)
        )
        ttk.Label(master=self.chat, text="Chat", anchor="center", font=self.sfont).pack(
            side="top", fill="x"
        )

        self.msg_label = ExpandingInput(
            master=self.chat,
            placeholder="Enter message...",
            font=self.sfont,
            min_height=1,
            max_height=6,
            on_send=self._handle_send,
        )
        self.msg_label.pack(side="bottom", fill="x", pady=(10, 0))

        self.chat_scroll = ScrollableFrame(master=self.chat)
        self.chat_scroll.pack(side="top", fill="both", expand=True)

        self.chat.grid(row=0, column=1, columnspan=2, sticky="nsew")

    def add_contact(self, name: str):
        initial = name[0] if name else "?"
        ContactCard(self.contacts_scroll.inner, name, initial).pack(
            fill="x", padx=5, pady=2
        )

        self.contacts_scroll._on_inner_configure(None)

    def add_message(self, text: str, is_outgoing: bool = False):
        canvas_w = self.chat_scroll.canvas.winfo_width()
        max_w = max(150, canvas_w - 40) if canvas_w > 40 else 300

        MessageBubble(self.chat_scroll.inner, text, is_outgoing, max_width=max_w)
        self.chat_scroll._on_inner_configure(None)
        self.chat_scroll.canvas.yview_moveto(1.0)

    def _handle_send(self, text: str):
        print(f"[SEND] {text}")

    def run(self):
        self.root.mainloop()
