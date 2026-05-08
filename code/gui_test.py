import gui.client as cli

if __name__ == "__main__":
    app = cli.GUIClient(geo=(700, 900))
    app.build()

    app.import_contacts(
        ["Февраль", "Алексей", "Дизайнер"]
    )

    msgs = [("Привет, как дела с GUI?", False),
            ("Всё ок, Tkinner поддался.", True)]
    for i in range(200):
        msgs.append(("Тестовое сообщение", i % 2 == 0))

    app.import_messages("Дизайнер", msgs)

    app.run()
