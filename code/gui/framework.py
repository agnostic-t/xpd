import tkinter


class GUIContainer:
    def __init__(self) -> None:
        self.frame = None
        self.root = None
        self.widgets = None

    def __enter__(self):
        pass

    def __exit__(self):
        pass


class GUIApp:
    def __init__(self, title: str, geometry: tuple[int, int]) -> None:
        self.title = title
        self.geometry = geometry

        self.container_stack: list[GUIContainer] = []
        self.current_container: int = 0

    def new_container(self):
        pass

    def add_widget(self):
        pass

    def run(self):
        pass
