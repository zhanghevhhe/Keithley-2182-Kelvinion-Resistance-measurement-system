# -*- coding: utf-8 -*-
"""
set_temp_dialog.py: Defines the SetTempDialog for manually setting a target temperature.
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt5.QtGui import QDoubleValidator

class SetTempDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Temperature")
        self.resize(260, 110)
        vbox = QVBoxLayout(self)

        # 温度输入
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Temp [K]:"))
        self.temp_edit = QLineEdit()
        self.temp_edit.setValidator(QDoubleValidator(0.0, 1000.0, 3, self))
        h1.addWidget(self.temp_edit)
        vbox.addLayout(h1)

        # Ramp 输入（可选）
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Ramp [K/min] (optional):"))
        self.ramp_edit = QLineEdit()
        self.ramp_edit.setValidator(QDoubleValidator(0.0, 1000.0, 3, self))
        self.ramp_edit.setPlaceholderText("leave empty to use PIDRAMP")
        h2.addWidget(self.ramp_edit)
        vbox.addLayout(h2)

        # 按钮
        btns = QHBoxLayout()
        ok = QPushButton("OK"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(ok); btns.addWidget(cancel)
        vbox.addLayout(btns)

    def get_values(self):
        """
        返回 (temp: float or None, ramp: float or None)
        """
        try:
            temp_text = self.temp_edit.text().strip()
            temp = float(temp_text) if temp_text else None
        except Exception:
            temp = None
        try:
            ramp_text = self.ramp_edit.text().strip()
            ramp = float(ramp_text) if ramp_text else None
        except Exception:
            ramp = None
        return temp, ramp