import gui.client as cli

if __name__ == "__main__":
    app = cli.GUIClient(geo=(1000, 900))
    app.build()

    app.add_contact("Февраль")
    app.add_contact("Алексей")
    app.add_contact("Дизайнер")

    app.add_message("Привет, как дела с GUI?", is_outgoing=False)
    app.add_message("Всё ок, Tkinner поддался.", is_outgoing=True)
    for i in range(200):
        app.add_message("Добавил скролл, сообщения и контакты.", is_outgoing=True)

    app.run()
