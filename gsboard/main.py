import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from gsboard.app import AppController
from gsboard.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GSBoard")
    app.setQuitOnLastWindowClosed(False)

    controller = AppController()
    controller.start()

    window = MainWindow(controller)
    controller.main_window = window
    controller.setup_tray(app)

    window.show()

    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
