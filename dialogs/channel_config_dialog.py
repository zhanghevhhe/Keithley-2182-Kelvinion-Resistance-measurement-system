# -*- coding: utf-8 -*-
"""
channel_config_dialog.py: Defines the ChannelConfigDialog for configuring measurement channels.
新增：当勾选启用某通道时，自动以 5s 间隔在最后一列显示该通道的 delta 模式电阻测量值（持续更新，界面打开时生效）。
硬件测量通过传入的 msys.measure_single_channel(...) 异步执行，UI 层仅显示结果。
"""
import json
import threading
import time
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
        self._timer.setInterval(12000)
        self._timer.timeout.connect(self._on_timer_tick)

        # 信号连接：从工作线程更新 UI
        self.measurement_updated.connect(self._update_res_label)

        # 启动定时测量仅当提供了 msys 并且其具有 measure_single_channel 方法
        if self.msys and hasattr(self.msys, "measure_single_channel"):
            self._timer.start()

        # 存储活跃线程引用以便管理（非必须）
        self._worker_threads = []
        # 停止标志，用于在关闭时阻止新测量线程启动
        self._stopping = False
        # 测量正在进行标志：确保一次只运行一个顺序测量线程
        self._measuring = False

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
        if self._stopping:
            return
        # 当任一通道被启用时，调度一次对所有已启用通道的顺序测量
        if state:
            self._schedule_measure_all()

    def _on_timer_tick(self):
        # 为所有已启用的通道启动异步测量线程
        if self._stopping:
            return
        # 周期性地顺序测量所有启用通道（避免并发对仪器的交叉访问）
        self._schedule_measure_all()

    def _schedule_measure_all(self):
        """
        启动一个后台线程，对所有已启用通道按顺序进行测量并依次更新 UI。
        这样可以保证在通道之间有短暂延迟，避免读取到上一通道的残留数据。
        """
        if self._stopping or self._measuring:
            return
        t = threading.Thread(target=self._measure_all_and_emit, daemon=True)
        t.start()
        self._worker_threads.append(t)
        # 清理已结束线程引用
        self._worker_threads = [thr for thr in self._worker_threads if thr.is_alive()]

    def _measure_all_and_emit(self):
        # 标记正在测量，确保不会并发启动多个测量线程
        self._measuring = True
        try:
            channel_order = ["CH1", "CH2", "CH3", "CH4"]
            for ch_name in channel_order:
                if self._stopping:
                    break
                widgets = self.channel_rows.get(ch_name)
                if not widgets:
                    continue
                enable_cb, pin_cbs, current_edit, volt_cb = widgets
                if not enable_cb.isChecked():
                    continue

                # 读取并解析参数
                try:
                    pins = [int(cb.currentText()) for cb in pin_cbs]
                except Exception:
                    pins = []
                current_text = current_edit.text().strip()
                try:
                    current_val = float(current_text)
                except Exception:
                    try:
                        current_val = float(current_text) if current_text else 1e-6
                    except Exception:
                        current_val = 1e-6

                channel_config = {
                    "pins": pins,
                    "current": current_val,
                    "voltage_range": volt_cb.currentText()
                }

                # DEBUG: 输出将传递给测量层的实际参数，便于定位映射或延时问题
                print(f"[ChannelConfigDialog] Starting sequential measurement for {ch_name} with pins={pins}, current={current_val}, voltage_range={channel_config['voltage_range']}")

                result = float('nan')
                try:
                    result = self.msys.measure_single_channel(ch_name, channel_config)
                except Exception as e:
                    print(f"[ChannelConfigDialog] Measurement error for {ch_name}: {e}")

                try:
                    self.measurement_updated.emit(ch_name, result)
                except Exception:
                    pass

                # 在通道间添加短暂延迟以确保仪器缓冲区/状态被清理
                try:
                    time.sleep(0.2)
                except Exception:
                    pass
        finally:
            self._measuring = False

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
        # 停止定时器并阻止新测量线程启动，然后等待现有线程结束后关闭对话框
        try:
            # 1) 阻止进一步启动新线程
            self._stopping = True
            # 2) 停止定时器
            try:
                self._timer.stop()
            except Exception:
                pass
            # 3) 断开 enable_cb 的 stateChanged 信号，避免外部回调触发
            for ch_name, widgets in self.channel_rows.items():
                enable_cb, _, _, _ = widgets
                try:
                    enable_cb.stateChanged.disconnect()
                except Exception:
                    pass
            # 4) 等待活跃线程短暂结束（每个线程最多等待 2s）
            for thr in list(self._worker_threads):
                try:
                    thr.join(timeout=2.0)
                except Exception:
                    pass
        finally:
            self.accept()

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)