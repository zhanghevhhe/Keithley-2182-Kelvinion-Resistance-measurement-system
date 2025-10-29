# -*- coding: utf-8 -*-
"""
ui_utils.py: Contains UI-related utility functions, such as icon creators and style providers.
"""
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QIcon, QPolygon

def create_labview_folder_icon():
    pix = QPixmap(16, 16); pix.fill(Qt.transparent); painter = QPainter(pix)
    painter.setBrush(QColor(255, 204, 0)); painter.setPen(QPen(QColor(100, 100, 100), 1))
    painter.drawRect(1, 3, 14, 12); painter.drawRect(2, 1, 5, 2); painter.drawRect(1, 6, 14, 9)
    painter.end(); return QIcon(pix)

def create_run_icon():
    pix = QPixmap(16, 16); pix.fill(Qt.transparent); painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing); painter.setPen(Qt.NoPen); painter.setBrush(QColor(0, 180, 0))
    painter.drawPolygon(QPolygon([QPoint(3, 2), QPoint(3, 14), QPoint(13, 8)]))
    painter.end(); return QIcon(pix)

def create_stop_icon():
    pix = QPixmap(16, 16); pix.fill(Qt.transparent); painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing); painter.setPen(Qt.NoPen); painter.setBrush(QColor(200, 0, 0))
    painter.drawRect(3, 3, 10, 10); painter.end(); return QIcon(pix)

def create_lock_icon(is_locked=False):
    pix = QPixmap(16, 16); pix.fill(Qt.transparent); painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(0,0,0), 1.5); painter.setPen(pen); painter.setBrush(Qt.NoBrush)
    painter.drawArc(5, 2, 6, 6, 0, 180 * 16); painter.drawLine(5, 5, 5, 9); painter.drawLine(11, 5, 11, 9)
    painter.setBrush(QColor(0,0,0)); painter.drawRect(3, 8, 10, 7)
    painter.end(); return QIcon(pix)

def get_labview_style():
    return """
        * {
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QMainWindow, QDialog { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; background-color: #f0f0f0; border: 1px solid #a0a0a0; border-radius: 6px; margin-top: 15px; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 8px; background-color: #e0e0e0; border-radius: 4px; border: 1px solid #a0a0a0; color: #000; }
        QPushButton { background-color: #e1e1e1; border: 1px solid #adadad; border-radius: 4px; padding: 5px 15px; text-align: center; }
        QToolButton {
            font-weight: bold;
            border-radius: 4px;
            border: 1px solid #b0b0b0;
            padding: 5px 15px;
            text-align: center;
            font-size: 16px;
            min-width: 0px;
        }
        QToolButton:checked {
            background-color: #43a047;
            color: #fff;
            border: 1px solid #388e3c;
        }
        QToolButton:hover, QPushButton:hover { background-color: #e9e9e9; border-color: #888888; }
        QToolButton:pressed, QPushButton:pressed { background-color: #d1d1d1; border-color: #555555; }
        QPushButton#clearAllButton { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        QPushButton#clearAllButton:hover { background-color: #f4b6bc; border-color: #f1aeb5; }
        QPushButton#clearAllButton:pressed { background-color: #f1aeb5; border-color: #eea6ac; }
        QToolButton:checked { background-color: #43a047; border: 1px solid #388e3c; }
        QLineEdit { background-color: #ffffff; border: 1px solid #a0a0a0; border-radius: 4px; padding: 3px; }
        QLineEdit:read-only { background-color: #f0f0f0; }
        QLabel { color: #000; background-color: transparent; }
        QComboBox { border: 1px solid #a0a0a0; border-radius: 4px; padding: 3px 18px 3px 5px; background-color: #e1e1e1; }
        QScrollArea { border: 1px solid #a0a0a0; background-color: #ffffff; }
    """ 