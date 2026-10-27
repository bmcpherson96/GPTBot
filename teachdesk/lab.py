"""Harmless separate process with movable controls and observable transitions."""
from __future__ import annotations

import random
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QMainWindow, QPushButton, QWidget


class Lab(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TeachDesk Practice Lab")
        self.resize(850, 620)
        self.setMinimumSize(850, 620)
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("QWidget { background: #ecf0f6; color: #16283f; font-size: 17px; } QPushButton {background:#ffffff; border:2px solid #325d88; padding:8px; border-radius:5px;} QPushButton:disabled {color:#8794a3;} QLineEdit {background:white; border:2px solid #325d88; padding:6px;}")
        label = QLabel("Practice: select Oak, type oak, then Finish.\nShuffle the controls before a held-out demonstration.", root)
        label.setGeometry(25, 18, 800, 58)
        self.status = QLabel(root)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setGeometry(25, 92, 780, 55)
        self.status.setStyleSheet("background:#16283f;color:white;font-size:24px;border-radius:5px")
        self.oak = QPushButton("Select Oak", root)
        self.oak.resize(175, 55)
        self.oak.clicked.connect(self.select)
        self.edit = QLineEdit(root)
        self.edit.setPlaceholderText("Item name")
        self.edit.resize(215, 55)
        self.edit.textChanged.connect(self.typed)
        self.finish = QPushButton("Finish task", root)
        self.finish.resize(175, 55)
        self.finish.clicked.connect(self.complete)
        self.reset = QPushButton("Reset", root)
        self.reset.setGeometry(25, 540, 130, 50)
        self.reset.clicked.connect(self.reset_state)
        shuffle = QPushButton("Shuffle layout", root)
        shuffle.setGeometry(175, 540, 190, 50)
        shuffle.clicked.connect(self.shuffle)
        self.exception = QCheckBox("Unexpected state", root)
        self.exception.setGeometry(405, 550, 230, 30)
        self.exception.toggled.connect(self.reset_state)
        self.selected = False
        self.shuffle()

    def reset_state(self, *_):
        self.selected = False
        self.edit.clear()
        self.oak.setEnabled(not self.exception.isChecked())
        self.edit.setEnabled(False)
        self.finish.setEnabled(False)
        self.status.setText("UNSUPPORTED: ask for help" if self.exception.isChecked() else "READY — choose an item")

    def shuffle(self):
        locations = [(45, 200), (315, 305), (575, 420)]
        random.shuffle(locations)
        for widget, point in zip((self.oak, self.edit, self.finish), locations):
            widget.move(*point)
        self.reset_state()

    def select(self):
        self.selected = True
        self.oak.setEnabled(False)
        self.edit.setEnabled(True)
        self.status.setText("ITEM SELECTED — enter oak")

    def typed(self, text):
        valid = self.selected and text == "oak"
        self.finish.setEnabled(valid)
        if self.selected:
            self.status.setText("TEXT ACCEPTED — finish task" if valid else "ITEM SELECTED — enter oak")

    def complete(self):
        if self.selected and self.edit.text() == "oak":
            self.status.setText("COMPLETE — oak stored")
            self.finish.setEnabled(False)
            self.edit.setEnabled(False)


def main():
    from .windows import enable_dpi_awareness
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Lab()
    window.show()
    if "--diagnostic-edit" in sys.argv:
        # Native test fixture starts with a harmless editable field in focus.
        # This is not used by any learned workflow or normal application launch.
        window.select()
        window.edit.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
