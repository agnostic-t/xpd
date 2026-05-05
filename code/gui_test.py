from tkinter import Label

import gui.framework as frm

if __name__ == "__main__":
    app = frm.GUIApp(geometry=(1000, 900), title="Test")

    with app.new_container(size=(900, 400), direction="vertical"):
        app.add_widget(Label(text="Header", font=("Arial", 32, "bold")))
        app.add_widget(Label(text="Body content"))

    with app.new_container(size=(900, 400), direction="horizontal"):
        app.add_widget(Label(text="Left"))
        app.add_widget(Label(text="Center"))
        app.add_widget(Label(text="Right"))

    app.run()
