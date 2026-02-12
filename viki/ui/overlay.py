import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen

class GhostOverlay(QWidget):
    """
    "Ghost Overlay": A transparent, click-through UI layer for visual augmentation.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.WindowTransparentForInput | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.highlights = [] # List of (x, y, w, h, label)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        for x, y, w, h, label in self.highlights:
            # Draw glowing rectangle
            pen = QPen(QColor(255, 0, 0, 200), 3)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)
            
            # Draw label
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(x, y - 5, label)

    def add_highlight(self, x, y, w, h, label="", duration=5000):
        self.highlights.append((x, y, w, h, label))
        self.update()
        if duration > 0:
            QTimer.singleShot(duration, self.clear_highlights)

    def clear_highlights(self):
        self.highlights = []
        self.update()

# Helper function to run the overlay in a separate process/thread
def run_overlay():
    app = QApplication(sys.argv)
    overlay = GhostOverlay()
    overlay.showFullScreen()
    sys.exit(app.exec_())
