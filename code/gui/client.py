import tkinter as tk
import tkinter.font as tkFont
import tkinter.ttk as ttk

from gui.frame import ScrollableFrame
from gui.exp_input import ExpandingInput
from gui.msg_bubble import MessageBubble
from gui.cli_card import ContactCard


class GUIClient:
    def __init__(self, geo: tuple[int, int] = (800, 500)) -> None:
        self.root = tk.Tk()
        self.root.title("XTCli")
        self.root.geometry(f"{geo[0]}x{geo[1]}")
        # self.root.resizable(False, False)

        self.sfont = tkFont.Font(family="Arial", size=16)
        self.contacts: ttk.Frame
        self.chat: ttk.Frame
        self.msg_label: ExpandingInput

        self.chat_scroll: ScrollableFrame
        self.contacts_scroll: ScrollableFrame
        self.chat_name: ttk.Label

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
            master=self.contacts, text="Contacts", anchor="center", font=self.sfont, background="#eee", padding=(5, 5)
        ).pack(side="top", fill="x")

        self.contacts_scroll = ScrollableFrame(master=self.contacts, max_width=300, min_width=150, padding=(0, 5))
        self.contacts_scroll.pack(side="top", fill="both", expand=True)

        self.root.columnconfigure(0, minsize=100)
        self.contacts.grid(row=0, column=0, sticky="nsew")


        self.chat = ttk.Frame(
            master=self.root, borderwidth=1, relief=tk.RAISED, padding=(2, 10),
        )
        self.chat_name = ttk.Label(master=self.chat, text="Chat", anchor="center", font=self.sfont, background="#eee", padding = (0, 5))
        self.chat_name.pack(side="top", fill="x")

        self.msg_label = ExpandingInput(
            master=self.chat,
            placeholder="Enter message...",
            font=self.sfont,
            min_height=1,
            max_height=6,
            on_send=self._handle_send,
        )
        self.msg_label.pack(side="bottom", fill="x", pady=(10, 0))

        self.chat_scroll = ScrollableFrame(master=self.chat, padding=(0, 10), adt_on_resize= lambda: self.chat_scroll._stick_to_bottom())
        self.chat_scroll.pack(side="top", fill="both", expand=True)

        self.chat.grid(row=0, column=1, columnspan=2, sticky="nsew")


    def add_contact(self, name: str, chat_db):
        card = ContactCard(
            master=self.contacts_scroll.inner,
            name=name,
            initial=name[0] if name else '?',
            bg_normal="#fff",
            bg_hover="#eee"
        )
        card.pack(fill="x", padx=8, pady=4)

        self.contacts_scroll._on_inner_configure(None)

    def import_contacts(self, contacts: list[str]):
        for child in self.contacts_scroll.inner.winfo_children():
            child.destroy()

        for name in contacts:
            card = ContactCard(
                master=self.contacts_scroll.inner,
                name=name,
                initial=name[0] if name else '?',
                bg_normal="#fff",
                bg_hover="#eee"
            )
            card.pack(fill="x", padx=8, pady=4)

        self.contacts_scroll._on_inner_configure(None)

    def import_messages(self, with_whom: str, messages: list[tuple[str, bool]]):
        for child in self.chat_scroll.inner.winfo_children():
            child.destroy()

        canvas_w = self.chat_scroll.canvas.winfo_width()
        max_w = max(150, canvas_w - 40) if canvas_w > 40 else 300

        self.chat_name.config(text=f"<{with_whom}>")

        for text, is_outgoing in messages:
            bg = "#0084ff" if is_outgoing else "#e5e5ea"
            fg = "#fff" if is_outgoing else "#000"

            msg_b = MessageBubble(
                self.chat_scroll.inner, text, max_w,
                style="system", bg=bg, fg=fg
            )
            if is_outgoing:
                msg_b.pack(anchor="e", pady=3, padx=10)
            else:
                msg_b.pack(anchor="w", pady=3, padx=10)

        self.chat_scroll._on_inner_configure(None)
        self.chat_scroll._stick_to_bottom()

    def add_message(self, text: str, is_outgoing: bool = False):
        canvas_w = self.chat_scroll.canvas.winfo_width()
        max_w = max(150, canvas_w - 40) if canvas_w > 40 else 300

        bg = "#0084ff" if is_outgoing else "#e5e5ea"
        fg = "#fff" if is_outgoing else "#000"

        msg_b = MessageBubble(self.chat_scroll.inner, text, max_w, style="system", bg=bg, fg=fg)
        if is_outgoing:
            msg_b.pack(anchor="e", pady=3, padx=10)
        else:
            msg_b.pack(anchor="w", pady=3, padx=10)

        self.chat_scroll._on_inner_configure(None)
        self.chat_scroll._stick_to_bottom()

    def _handle_send(self, text: str):
        print(self.chat_scroll.canvas.yview())
        print(f"[SEND] {text}")

    def run(self):
        self.root.mainloop()
