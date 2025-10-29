# -*- coding: utf-8 -*-
"""
channel_config_dialog.py: Defines the ChannelConfigDialog for configuring measurement channels.
新增：当勾选启用某通道时，自动以 5s 间隔在最后一列显示该通道的 delta 模式电阻测量值（持续更新，界面打开时生效）。
硬件测量通过传入的 msys.measure_single_channel(...) 异步执行，UI 层仅显示结果。
"""
import json
import threading
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGridLayout, QLabel, QCheckBox, QComboBox, QLineEdit, QPushButton
from PyQt5.QtCore import pyqtSignal, Qt, QTimer

class ChannelConfigDialog(QDialog):
    config_changed = pyqtSignal(dict)
    measurement_updated = pyqtSignal(str, float)  # channel_name, resistance

    def __init__(self, msys, parent=None, is_locked=False):
        super().__init__(parent)
        self.msys = msys
        self.setWindowTitle("Channel Configuration")
        self.resize(760, 220)
        self.setStyleSheet("QDialog { background: #f8fafd; border-radius: 12px; border: 1px solid #d0d7de; } QPushButton { background: #388e3c; color: #fff; font-weight: bold; border-radius: 6px; padding: 6px 18px; } QComboBox, QLineEdit { background: #fff; border: 1px solid #a0a0a0; border-radius: 4px; } QCheckBox { padding: 2px; } QLabel { color: #222; }")
        self.channels_file = "config/channels.json"
        self.channels_data = self.load_channels()

        layout = QVBoxLayout()
        grid = QGridLayout()
        headers = ["Channel", "Enable", "I+", "V+", "V-", "I-", "Current[A]", "V Range", "Last R [Ohm]"]
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet("font-weight:bold; color:#222; background:#e0e0e0; padding:2px 6px; border-radius:4px;")
            grid.addWidget(label, 0, i, Qt.AlignLeft)

        self.channel_rows = {}
        self.res_labels = {}
        for row, ch_name in enumerate(["CH1", "CH2", "CH3", "CH4"], 1):
            ch_config = self.channels_data.get(ch_name, {})
            enable_cb = QCheckBox()
            enable_cb.setChecked(ch_config.get('enabled', False))

            pin_cbs = []
            pins = ch_config.get('pins', [1,1,1,1])
            for i in range(4):
                cb = QComboBox()
                cb.addItems([str(x) for x in range(1, 17)])
                cb.setCurrentText(str(pins[i]) if i < len(pins) else "1")
                cb.setStyleSheet("background:#fff; border:1px solid #a0a0a0; border-radius:3px;")
                pin_cbs.append(cb)

            current_edit = QLineEdit(str(ch_config.get('current', '1e-6')))
            current_edit.setStyleSheet("background:#fff; border:1px solid #a0a0a0; border-radius:3px;")

            volt_cb = QComboBox()
            volt_cb.addItems(["10V", "1V", "100mV", "10mV"])
            volt_cb.setCurrentText(ch_config.get('voltage_range', '1V'))
            volt_cb.setStyleSheet("background:#fff; border:1px solid #a0a0a0; border-radius:3px;")

            res_label = QLabel("--")
            res_label.setStyleSheet("background:#fff; border:1px solid #cfcfcf; padding:4px; border-radius:4px;")
            res_label.setMinimumWidth(140)

            grid.addWidget(QLabel(ch_name), row, 0)
            grid.addWidget(enable_cb, row, 1)
            for i, cb in enumerate(pin_cbs):
                grid.addWidget(cb, row, 2+i)
            grid.addWidget(current_edit, row, 6)
            grid.addWidget(volt_cb, row, 7)
            grid.addWidget(res_label, row, 8)

            self.channel_rows[ch_name] = (enable_cb, pin_cbs, current_edit, volt_cb)
            self.res_labels[ch_name] = res_label

            # 立即在勾选变化时触发一次测量（若启用）
            enable_cb.stateChanged.connect(lambda state, cn=ch_name: self._on_enable_changed(cn, state))

        layout.addLayout(grid)
        self.apply_btn = QPushButton("Apply & Exit")
        self.apply_btn.setStyleSheet("background:#388e3c; color:#fff; font-weight:bold; border-radius:5px; padding:6px 18px;")
        self.apply_btn.clicked.connect(self.apply_and_exit)
        layout.addWidget(self.apply_btn)
        self.setLayout(layout)

        # 根据is_locked锁定控件
        if is_locked:
            for row in self.channel_rows.values():
                enable_cb, pin_cbs, current_edit, volt_cb = row
                enable_cb.setEnabled(False)
                for cb in pin_cbs:
                    cb.setEnabled(False)
                current_edit.setReadOnly(True)
                volt_cb.setEnabled(False)
            self.apply_btn.setEnabled(False)

        # 定时器用于周期性触发测量（8s）
        self._timer = QTimer(self)
        self._timer.setInterval(8000)
        self._timer.timeout.connect(self._on_timer_tick)

        # 信号连接：从工作线程更新 UI
        self.measurement_updated.connect(self._update_res_label)

        # 启动定时测量仅当提供了 msys 并且其具有 measure_single_channel 方法
        if self.msys and hasattr(self.msys, "measure_single_channel"):
            self._timer.start()

        # 存储活跃线程引用以便管理（非必须）
        self._worker_threads = []

    def load_channels(self):
        try:
            with open(self.channels_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            # 默认值
            return {
                "CH1": {"enabled": False, "pins": [1,1,1,1], "current": "1e-6", "voltage_range": "1V"},
                "CH2": {"enabled": False, "pins": [1,1,1,1], "current": "1e-6", "voltage_range": "1V"},
                "CH3": {"enabled": False, "pins": [1,1,1,1], "current": "1e-6", "voltage_range": "1V"},
                "CH4": {"enabled": False, "pins": [1,1,1,1], "current": "1e-6", "voltage_range": "1V"}
            }

    def _on_enable_changed(self, ch_name, state):
        # 如果被勾选，立即触发一次测量
        if state:
            self._start_measure_thread(ch_name)

    def _on_timer_tick(self):
        # 为所有已启用的通道启动异步测量线程
        for ch_name, widgets in self.channel_rows.items():
            enable_cb, _, _, _ = widgets
            if enable_cb.isChecked():
                self._start_measure_thread(ch_name)

    def _start_measure_thread(self, ch_name):
        # 避免过多并发：允许短暂并发但不保存线程引用过多
        t = threading.Thread(target=self._measure_and_emit, args=(ch_name,), daemon=True)
        t.start()
        self._worker_threads.append(t)
        # 清理已结束线程引用
        self._worker_threads = [thr for thr in self._worker_threads if thr.is_alive()]

    def _measure_and_emit(self, ch_name):
        try:
            # 构造 channel_config 与 MeasurementSystem.measure_single_channel 所需字段
            enable_cb, pin_cbs, current_edit, volt_cb = self.channel_rows[ch_name]
            try:
                pins = [int(cb.currentText()) for cb in pin_cbs]
            except Exception:
                pins = []
            current_text = current_edit.text().strip()
            try:
                current_val = float(current_text)
            except Exception:
                current_val = float(current_text) if current_text else 1e-6

            channel_config = {
                "pins": pins,
                "current": current_val,
                "voltage_range": volt_cb.currentText()
            }

            # 调用 MeasurementSystem 的接口（可能是模拟或真实测量）
            result = float('nan')
            try:
                result = self.msys.measure_single_channel(ch_name, channel_config)
            except Exception as e:
                # 若测量抛异常，保留 NaN 并在控制台打印
                print(f"[ChannelConfigDialog] Measurement error for {ch_name}: {e}")

            # 发射信号回主线程更新 UI
            try:
                self.measurement_updated.emit(ch_name, result)
            except Exception:
                pass
        except Exception as e:
            print(f"[ChannelConfigDialog] _measure_and_emit failed for {ch_name}: {e}")

    def _update_res_label(self, ch_name, value):
        lbl = self.res_labels.get(ch_name)
        if not lbl:
            return
        if value is None or (isinstance(value, float) and (value != value)):  # NaN
            lbl.setText("--")
        else:
            try:
                # 使用 6 位有效数字显示电阻
                lbl.setText(f"{value:.6g}")
            except Exception:
                lbl.setText(str(value))

    def apply_and_exit(self):
        new_channels_data = {}
        for ch_name, widgets in self.channel_rows.items():
            enable_cb, pin_cbs, current_edit, volt_cb = widgets
            pins = [int(cb.currentText()) for cb in pin_cbs]
            new_channels_data[ch_name] = {
                'enabled': enable_cb.isChecked(),
                'pins': pins,
                'current': current_edit.text(),
                'voltage_range': volt_cb.currentText()
            }
        with open(self.channels_file, 'w', encoding='utf-8') as f:
            json.dump(new_channels_data, f, indent=4)
        self.config_changed.emit(new_channels_data)
        # 停止定时器并关闭
        try:
            self._timer.stop()
        except Exception:
            pass
        self.accept()

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)