import os.path as pth

from db.database import DataBase


class ChatDatabase:
    def __init__(self, dir_path: str) -> None:
        self.db_contacts = DataBase(pth.join(dir_path, "contacts.sqlite3"))
        self.db_messages = DataBase(pth.join(dir_path, "messages.sqlite3"))

    def clear(self, contacts: bool, messages: bool):
        if contacts:
            for t in self.db_contacts.all():
                self.db_contacts.delete(t)

        if messages:
            for t in self.db_messages.all():
                self.db_messages.delete(t)

    def new_message(
        self, token: int, time: int, text: str, outgoing: bool
    ) -> tuple[bool, str]:
        msgs = self.db_messages.get(token)

        if msgs is None:
            return False, "Failed to register message from unknown addressant"

        msgs["messages"].append((time, outgoing, text))

        self.db_messages.set(token, msgs)
        return True, "Ok"

    def new_contact(self, name: str, token: int):
        if self.db_contacts.get(token) is not None:
            return False, "Failed to register new contact, already exists"

        self.db_contacts.set(token, name)
        self.db_messages.set(token, {"messages": []})

        return True, "Ok"

    def get_messages_from(self, token: int) -> None | list[tuple[int, bool, str]]:
        msgs = self.db_messages.get(token)
        if not msgs:
            return None

        return msgs["messages"]

    def get_contacts(self) -> list[tuple[int, str]]:
        return [(t, self.db_contacts.get(t) or "") for t in self.db_contacts.all()]

    def check_contact(self, token: int) -> bool:
        return self.db_contacts.get(token) is not None

    def is_empty(self) -> bool:
        return len(self.db_contacts.all()) == 0

    def remove_contact(self, token: int, messages: bool):
        self.db_contacts.delete(token)

        if messages:
            self.db_messages.delete(token)
