import time

import db.chat as chd
import gui.client as cli

if __name__ == "__main__":
    chat_db = chd.ChatDatabase("./runtime/databases")
    if chat_db.is_empty():
        print("DB is empty")
        chat_db.new_contact("Дизайнер", 123)
        chat_db.new_contact("Василий", 234)
        chat_db.new_contact("Февраль", 345)

        chat_db.new_message(123, int(time.time()), "Привет 123", True)
        chat_db.new_message(123, int(time.time()), "Привет я!", False)

        chat_db.new_message(234, int(time.time()), "Привет 234", True)
        chat_db.new_message(234, int(time.time()), "Привет я!", False)

        chat_db.new_message(345, int(time.time()), "Привет 345", True)
        chat_db.new_message(345, int(time.time()), "Привет я!", False)

    app = cli.GUIClient(chat_db)
    app.build()
    app.import_from_db()

    app.run()
