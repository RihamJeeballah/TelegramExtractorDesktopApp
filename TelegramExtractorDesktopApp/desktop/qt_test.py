from PySide6.QtWidgets import QApplication, QLabel
app = QApplication([])
w = QLabel("Qt is working ✅")
w.resize(300, 80)
w.show()
app.exec()
