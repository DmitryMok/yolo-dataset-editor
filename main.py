# запуск из win \\wsl.localhost\Ubuntu\home\mdm3\Projects\yololabel\setup_and_run.bat

import sys
import os
from pathlib import Path

# Без этого Windows показывает иконку python.exe на панели задач вместо иконки приложения
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yololabel.app.1")

# Загрузить переменные окружения из .env для корректной работы GUI в PyCharm/WSL
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication
from gui.theme import setup_theme
from gui.main_window import MainWindow
from gui.app_icon import make_app_icon


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YOLO Label Viewer")

    icon = make_app_icon()
    app.setWindowIcon(icon)

    # Автоматически установить правильную тему в зависимости от платформы
    setup_theme(app)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
