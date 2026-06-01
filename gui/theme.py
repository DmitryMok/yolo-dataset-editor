from PyQt6.QtWidgets import QApplication
from gui.style import make_stylesheet


def setup_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(make_stylesheet())
