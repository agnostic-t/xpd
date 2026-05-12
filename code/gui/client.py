import queue
import threading
import tkinter as tk
import tkinter.font as tkFont
import tkinter.ttk as ttk
from hashlib import sha256
from time import time

from db.chat import ChatDatabase

from gui.cli_card import ContactCard
from gui.exp_input import ExpandingInput
from gui.frame import ScrollableFrame
from gui.msg_bubble import MessageBubble

import base64
from tkinter import filedialog


class GUIClient:
    def __init__(
        self, db: ChatDatabase, upd_dt: int = 2, geo: tuple[int, int] = (800, 500)
    ) -> None:
        self.root = tk.Tk()
        self.root.title("XTCli")
        self.root.geometry(f"{geo[0]}x{geo[1]}")
        # self.root.resizable(False, False)

        self.inbox = queue.Queue()
        self.outbox = queue.Queue()

        self.running = threading.Event()
        self.running.set()

        self.sfont = tkFont.Font(family="Arial", size=16)
        self.contacts: ttk.Frame
        self.chat: ttk.Frame
        self.msg_label: ExpandingInput

        self.chat_scroll: ScrollableFrame
        self.contacts_scroll: ScrollableFrame
        self.chat_name: ttk.Label

        self.contacts_exists: set[int] = set()
        self.cards: dict[int, ContactCard] = {}

        self.db = db
        self.upd_dt = upd_dt
        self.current_contact: int = -1
        self.current_chat_name: str = "No chat selected"

        for c in range(3):
            self.root.columnconfigure(index=c, weight=1)
        for r in range(1):
            self.root.rowconfigure(index=r, weight=1)

    def build(self):
        self.contacts = ttk.Frame(
            master=self.root, borderwidth=1, relief="flat", padding=(8, 10)
        )

        ttk.Label(
            master=self.contacts,
            text="Contacts",
            anchor="center",
            font=self.sfont,
            background="#eee",
            padding=(5, 5),
        ).pack(side="top", fill="x")

        self.contacts_scroll = ScrollableFrame(
            master=self.contacts, max_width=300, min_width=150, padding=(0, 5)
        )
        self.contacts_scroll.pack(side="top", fill="both", expand=True)

        self.root.columnconfigure(0, minsize=100)
        self.contacts.grid(row=0, column=0, sticky="nsew")

        self.chat = ttk.Frame(
            master=self.root,
            borderwidth=1,
            relief="flat",
            padding=(2, 10),
        )
        self.chat_name = ttk.Label(
            master=self.chat,
            text="Chat",
            anchor="center",
            font=self.sfont,
            background="#eee",
            padding=(0, 5),
        )
        self.chat_name.pack(side="top", fill="x")

        self.input_frame = ttk.Frame(master=self.chat)
        self.input_frame.pack(side="bottom", fill="x", pady=(10, 0))

        # Кнопка прикрепления изображения
        self.attach_btn = tk.Button(
            master=self.input_frame,
            text="📎",
            font=("Arial", 16),
            bd=0,
            cursor="hand2",
            command=self._handle_send_image
            )
        self.attach_btn.pack(side="left", padx=(0, 10), fill="y")

        # Поле ввода текста
        self.msg_label = ExpandingInput(
            master=self.input_frame,
            placeholder="Enter message...",
            font=self.sfont,
            min_height=1,
            max_height=6,
            on_send=self._handle_send,
        )
        self.msg_label.pack(side="left", fill="x", expand=True)

        self.chat_scroll = ScrollableFrame(master=self.chat, padding=(0, 10))
        ttk.Label(
            master=self.chat_scroll.inner,
            anchor="center",
            text="You can select chat from contacts from left panel",
            wraplength=500,
            font=("Arial", 30),
        ).pack(fill="both", expand=True, anchor="center", pady=200)

        self.chat_scroll.pack(side="top", fill="both", expand=True)

        self.chat.grid(row=0, column=1, columnspan=2, sticky="nsew")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll_queues)

    def force_exit(self):
        self.inbox.put(("sys", "__SHUTDOWN__"))

    def _poll_queues(self):
        while not self.inbox.empty():
            try:
                mtype, msg_data = self.inbox.get_nowait()
                if mtype == "sys" and msg_data == "__SHUTDOWN__":
                    self.on_close()
                    return
                if mtype == "msg":
                    self._handle_incoming_network_msg(msg_data)
                if mtype == "peer":
                    name = sha256(f"{msg_data[1]}".encode()).hexdigest()[2:9]
                    self._add_contact(name, msg_data[1])
                    self.db.new_contact(name, msg_data[0], msg_data[1])

            except queue.Empty:
                break

        if self.running.is_set():
            self.root.after(100, self._poll_queues)

    def _handle_incoming_network_msg(self, data: tuple[int, str, int, bool]):
        token, text, timestamp, is_outgoing = data
        st, msg = self.db.new_message(token, timestamp, text, is_outgoing)
        if not st:
            print(f"[HANDLE] failed to reg new msg: {msg}")

        if token == self.current_contact:
            self._add_message(text, is_outgoing)

    def import_from_db(self):
        self._import_contacts(self.db.get_contacts())

    def _card_click(self, token: int, name: str):
        self.current_contact = token

        # print(self.db.get_messages_from(token))
        self._import_messages(name, self.db.get_messages_from(token) or [])

    def _import_contacts(self, contacts: list[tuple[int, str]]):
        for child in self.contacts_scroll.inner.winfo_children():
            child.destroy()

        for token, name in contacts:
            card = ContactCard(
                master=self.contacts_scroll.inner,
                token=int(token),
                name=name,
                initial=name[0] if name else "?",
                bg_normal="#fff",
                bg_hover="#eee",
                command=self._card_click,
            )
            card.pack(fill="x", padx=8, pady=4)
            self.contacts_exists.add(int(token))
            self.cards[int(token)] = card



        self.contacts_scroll._on_inner_configure(None)

    def _import_messages(self, with_whom: str, messages: list[tuple[int, bool, str]]):
        for child in self.chat_scroll.inner.winfo_children():
            child.destroy()

        canvas_w = self.chat_scroll.canvas.winfo_width()
        max_w = max(150, canvas_w - 40) if canvas_w > 40 else 300

        self.chat_name.config(text=f"<{with_whom}>")

        for timest, is_outgoing, text in messages:
            bg = "#0084ff" if is_outgoing else "#e5e5ea"
            fg = "#fff" if is_outgoing else "#000"

            if text.startswith("IMG:"):
                b64_data = text[4:]
                msg_b = MessageBubble(
                    self.chat_scroll.inner, image_b64=b64_data, max_width=max_w, style="system", bg=bg, fg=fg
                )
            else:
                msg_b = MessageBubble(
                    self.chat_scroll.inner, text=text, max_width=max_w, style="system", bg=bg, fg=fg
                )
            if is_outgoing:
                msg_b.pack(anchor="e", pady=3, padx=10)
            else:
                msg_b.pack(anchor="w", pady=3, padx=10)

        self.chat_scroll._on_inner_configure(None)
        self._scroll_to_bottom()
        # self.chat_scroll._stick_to_bottom()

    def _add_contact(self, name: str, token: int):
        print("add:", token, self.contacts_exists)
        if token in self.contacts_exists:
            return

        self.contacts_exists.add(token)
        card = ContactCard(
            master=self.contacts_scroll.inner,
            token=token,
            name=name,
            initial=name[0] if name else "?",
            bg_normal="#fff",
            bg_hover="#eee",
            command=self._card_click,
        )
        card.pack(fill="x", padx=8, pady=4)
        self.cards[token] = card

        self.contacts_scroll._on_inner_configure(None)

    def set_contact_online(self, token: int, is_online: bool):
        if token in self.cards:
            self.cards[token].set_status(is_online)

    def _add_message(self, text: str, is_outgoing: bool = False):
        was_at_bottom = self.chat_scroll.is_at_bottom(tolerance=50)

        canvas_w = self.chat_scroll.canvas.winfo_width()
        max_w = max(150, canvas_w - 40) if canvas_w > 40 else 300

        bg = "#0084ff" if is_outgoing else "#e5e5ea"
        fg = "#fff" if is_outgoing else "#000"

        if text.startswith("IMG:"):
            b64_data = text[4:]
            msg_b = MessageBubble(
                self.chat_scroll.inner, image_b64=b64_data, max_width=max_w, style="system", bg=bg, fg=fg
            )
        else:
            msg_b = MessageBubble(
                self.chat_scroll.inner, text=text, max_width=max_w, style="system", bg=bg, fg=fg
            )

        if is_outgoing:
            msg_b.pack(anchor="e", pady=3, padx=10)
        else:
            msg_b.pack(anchor="w", pady=3, padx=10)

        self.chat_scroll._on_inner_configure(None)

        msg_data = (self.current_contact, text)
        if is_outgoing:
            self.outbox.put(msg_data)

        if is_outgoing or was_at_bottom:
            self.chat_scroll._stick_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_scroll.canvas.yview_moveto(1.0)

    def _handle_send(self, text: str):
        print(f"[SEND] {text}")
        if self.current_contact == -1:
            print("[SEND] cannot send any message, current contact is -1")
            return

        status, msg = self.db.new_message(self.current_contact, int(time()), text, True)
        if not status:
            print("[SEND] failed:", msg)

        self._add_message(text, True)

    def _handle_send_image(self):
        if self.current_contact == -1:
            print("[SEND] cannot send image (current contact is -1)")
            return

        filepath = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif")]
        )

        if filepath:
            try:
                with open(filepath, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

                img_msg = f"IMG:{encoded_string}"

                status, msg = self.db.new_message(self.current_contact, int(time()), img_msg, True)
                if not status:
                    print("[SEND IMAGE] ошибка сохранения в БД:", msg)

                self._add_message(img_msg, True)

            except Exception as e:
                print(f"[SEND] Failed to send image {e}")

    def run(self):
        self.root.mainloop()

    def on_close(self):
        self.running.clear()
        self.root.destroy()
