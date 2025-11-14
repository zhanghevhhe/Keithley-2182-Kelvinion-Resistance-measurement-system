# -*- coding: utf-8 -*-
"""
controller.py: Contains the main application logic and state management.
- AppController: The "brain" of the application, handling business logic.
- MeasurementWorker: The QObject that runs the measurement sequence in a separate thread.
"""
import time
import os
import csv
import datetime
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QDialog


def lowerT(temp_a):
    """根据回路 A 的温度计算回路 B 的目标温度（降低约10K，但不低于2K）。"""
    lowered = temp_a - 10
    return lowered if lowered > 2 else temp_a


class MeasurementWorker(QObject):
    """
    在后台线程中执行测量序列的工人对象。
    避免在测量过程中UI冻结，并通过信号与主线程通信。
    """
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    new_data = pyqtSignal(float, dict)
    update_set_temp = pyqtSignal(float)
    block_changed = pyqtSignal(int)

    def __init__(self, msys, sequence):
        """
        Args:
            msys: MeasurementSystem 实例（model）
            sequence: 从 UI 获取的序列数据（列表）
        """
        super().__init__()
        self.msys = msys
        self.sequence = sequence or []
        self._is_running = True

    def stop(self):
        """请求停止正在运行的测量循环（由 controller 调用）。"""
        self._is_running = False

    def _generate_temps_for_block(self, block):
        """为一个温度块生成所有目标温度点。"""
        try:
            start_temp = float(block['start'])
            stop_temp = float(block['stop'])
            step_val = float(block['step'])
        except (ValueError, TypeError, KeyError):
            return []

        temp_points = []
        if step_val == 0:
            temp_points.append(start_temp)
        else:
            if start_temp > stop_temp:
                step = -abs(step_val)
            else:
                step = abs(step_val)

            points = np.arange(start_temp, stop_temp, step, dtype=float)
            temp_points.extend(points.tolist())

            if not points.size or not np.isclose(points[-1], stop_temp):
                if (step > 0 and stop_temp >= start_temp) or \
                   (step < 0 and stop_temp <= start_temp):
                    temp_points.append(stop_temp)
        return temp_points

    def _get_all_target_temps(self):
        """获取所有将要测量的温度点，用于预先打印调试。"""
        all_temps = []
        for block in self.sequence:
            temps_in_block = self._generate_temps_for_block(block)
            all_temps.extend(temps_in_block)
            if block.get('end', False):
                break
        return all_temps

    def run(self):
        """主测量循环。"""
        self.progress.emit("Measurement sequence started.")

        target_temps = self._get_all_target_temps()
        print("--- Target Temperature Sequence ---")
        print(target_temps)
        print("---------------------------------")

        for i, block in enumerate(self.sequence):
            if not self._is_running:
                break

            self.block_changed.emit(i)
            temp_points_in_block = self._generate_temps_for_block(block)

            if not temp_points_in_block:
                self.progress.emit(f"Block {i+1}: Invalid parameters or empty sequence. Skipping.")
                continue

            for temp_point in temp_points_in_block:
                if not self._is_running:
                    break

                self.update_set_temp.emit(temp_point)
                self.progress.emit(f"Block {i+1}/{len(self.sequence)}: Setting temperature to {temp_point:.2f} K...")

                if self.msys.kelvinion:
                    self.msys.kelvinion.set_temperature(temp_point, 'A')
                    self.msys.kelvinion.set_temperature(lowerT(temp_point), 'B')
                    self.progress.emit(f"Block {i+1}/{len(self.sequence)}: Waiting for temperature to stabilize at {temp_point:.2f} K...")
                    self.msys.kelvinion.wait_for_stable(temp_point, is_running_checker=lambda: self._is_running)

                if not self._is_running:
                    break

                self.progress.emit(f"Block {i+1}/{len(self.sequence)}: Measuring at {temp_point:.2f} K...")

                resistances = {}
                # 采集一份已启用通道的参数快照，避免在测量过程中被 UI 或其它线程修改
                enabled_channels = [item for item in self.msys.channels.items() if item[1].get('enabled', False)]
                snapshot = []
                for ch_name, ch_config in enabled_channels:
                    try:
                        pins = list(ch_config.get('pins', [])) if ch_config.get('pins') is not None else []
                    except Exception:
                        pins = []
                    try:
                        current_val = float(ch_config.get('current', 1e-6))
                    except Exception:
                        current_val = 1e-6
                    vrange = ch_config.get('voltage_range', '1V')
                    snapshot.append((ch_name, pins, current_val, vrange))

                # 顺序测量快照中的每个通道
                for ch_name, pins, current_val, vrange in snapshot:
                    if not self._is_running:
                        break

                    self.progress.emit(f"Measuring channel: {ch_name}")

                    # 在调用下层测量前尝试断开矩阵的所有连接，避免残留影响
                    try:
                        if getattr(self.msys, 'matrix', None) is not None:
                            try:
                                self.msys.matrix.open_all()
                            except Exception as e:
                                print(f"[Controller] Warning: matrix.open_all() failed before measuring {ch_name}: {e}")
                            time.sleep(0.08)
                    except Exception:
                        pass

                    channel_config = {
                        'pins': pins,
                        'current': current_val,
                        'voltage_range': vrange
                    }

                    try:
                        res = self.msys.measure_single_channel(ch_name, channel_config)
                    except Exception as e:
                        print(f"[Controller] Measurement error for {ch_name}: {e}")
                        res = float('nan')
                    resistances[ch_name] = res

                    # 在通道间添加保守延迟
                    try:
                        time.sleep(0.6)
                    except Exception:
                        pass

                if not self._is_running:
                    break

                temp = self.msys.get_sample_temperature()
                self.new_data.emit(temp, resistances)

            if not self._is_running:
                break

            if block.get('end', False):
                self.progress.emit("End of sequence reached (END checkbox).")
                break

        if self._is_running:
            self.progress.emit("Measurement sequence finished.")
        else:
            self.progress.emit("Measurement sequence stopped by user.")

        self.finished.emit()


class AppController(QObject):
    """
    应用程序的"大脑"，处理所有业务逻辑和状态管理。
    连接View（GUI）和Model（MeasurementSystem）。
    """
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.view = None

        # --- State Management ---
        self.is_running = False
        self.is_manual_locked = False

        # --- Thread Management ---
        self.measurement_thread = None
        self.measurement_worker = None

    def set_view(self, view):
        """将Controller与View关联起来。"""
        self.view = view
        self.model.sample_temp_changed.connect(self.view.update_sample_temp_display)
        self.model.chamber_temp_changed.connect(self.view.update_chamber_temp_display)
        self.model.error_occurred.connect(self.view.show_error)
        self.model.warning_occurred.connect(self.view.show_warning)

    def initialize_ui(self):
        """初始化UI状态，创建默认的温度块。"""
        self.view.clear_all_temp_blocks()

    def add_temp_block(self):
        """命令View添加一个新的温度块。"""
        self.view.add_temp_block()

    def clear_all_temp_blocks(self):
        """命令View清除所有温度块并重置。"""
        self.view.clear_all_temp_blocks()

    def _update_ui_lock_state(self):
        """计算并更新UI的锁定状态。"""
        is_locked = self.is_running or self.is_manual_locked
        self.view.set_ui_locked(is_locked, self.is_running)

    # -------------------------------------------------------------------------
    # 业务逻辑方法
    # -------------------------------------------------------------------------

    def toggle_measurement(self):
        """根据当前状态，开始或停止测量。"""
        if self.is_running:
            self._stop_measurement()
        else:
            self._start_measurement()
        self._update_ui_lock_state()

    def _start_measurement(self):
        """开始测量序列。"""
        sequence_data = self.view.get_sequence_data()
        print(sequence_data)
        if not sequence_data:
            QMessageBox.warning(self.view, "Warning", "No valid temperature blocks to run.")
            self._update_ui_lock_state()
            return

        file_path = self.view.get_save_path().strip()
        if not file_path or not file_path.lower().endswith('.txt') or os.path.isdir(file_path):
            QMessageBox.critical(self.view, "Error", "Please set a valid .txt file path.")
            self._update_ui_lock_state()
            return

        # 只在文件不存在时写表头，存在就直接追加
        if not os.path.exists(file_path):
            self._write_header_to_file(file_path)

        self.is_running = True
        self._update_ui_lock_state()
        self.view.update_running_status(True)
        self.view.clear_plots()
        self.view.update_plots_from_file(file_path)
        self.view.clear_error()

        self.measurement_thread = QThread()
        self.measurement_worker = MeasurementWorker(self.model, sequence_data)
        self.measurement_worker.moveToThread(self.measurement_thread)

        # --- 连接Worker的信号到Controller和View ---
        self.measurement_thread.started.connect(self.measurement_worker.run)
        self.measurement_worker.finished.connect(self.on_measurement_finished)
        self.measurement_worker.new_data.connect(self.handle_new_data)
        self.measurement_worker.progress.connect(self.view.update_progress)
        self.measurement_worker.update_set_temp.connect(self.view.update_set_temp_display)
        self.measurement_worker.block_changed.connect(self.on_block_changed)

        self.measurement_thread.start()

    def _stop_measurement(self):
        """停止测量序列。"""
        if self.measurement_worker:
            try:
                self.measurement_worker.stop()
            except Exception:
                pass

        self.is_running = False
        self._update_ui_lock_state()

        try:
            if self.view:
                self.view.update_running_status(False)
        except Exception:
            pass

    def on_measurement_finished(self):
        """测量完成后的清理工作。"""
        self.is_running = False
        self._update_ui_lock_state()
        self.view.update_running_status(False)
        self.view.highlight_running_block(-1)

        if self.measurement_thread:
            self.measurement_thread.quit()
            self.measurement_thread.wait(100)
            self.measurement_thread = None
        self.measurement_worker = None

    def toggle_lock(self):
        """切换手动锁定状态。"""
        if not self.is_running:
            self.is_manual_locked = not self.is_manual_locked
            self._update_ui_lock_state()

    def on_block_changed(self, block_index):
        """处理当前执行块变化的信号。"""
        self.view.highlight_running_block(block_index)

    def handle_new_data(self, temp, resistances):
        """
        处理新数据：
        1. 命令Model更新其内部状态。
        2. 命令View更新UI。
        3. 将数据写入文件。
        """
        for ch_name, res_value in resistances.items():
            if res_value is not None:
                self.model.update_last_resistance(ch_name, res_value)

        self.view.handle_new_data(temp, resistances)
        self.view.update_plot_titles()
        self._write_data_to_file(temp, resistances)

    def _write_data_to_file(self, temp, resistances):
        """将一行数据写入CSV文件。"""
        try:
            path = self.view.get_save_path()
            with open(path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                row_data = []
                for ch in self.model.channels.keys():
                    res_value = resistances.get(ch)
                    if res_value is not None and self.model.channels[ch].get('enabled', False):
                        row_data.append(f"{res_value:.6e}")
                    else:
                        row_data.append('XXXXXXE0')

                row = [timestamp, f"{temp:.6e}"] + row_data
                writer.writerow(row)
        except Exception as e:
            QMessageBox.critical(self.view, "File Write Error", f"Error writing data to file:\n{e}")

    def choose_path(self):
        """处理文件路径选择。"""
        current_path = self.view.get_save_path()
        file_path, _ = QFileDialog.getSaveFileName(
            self.view, "Select Data Save File", current_path, "Text Files (*.txt);;All Files (*)"
        )

        if not file_path:
            return

        self.view.set_save_path(file_path)
        self.model.set_save_path(file_path)
        self.view.update_plots_from_file(file_path)

    def _write_header_to_file(self, file_path):
        """向指定文件写入表头。"""
        try:
            header = self.model.get_csv_header()
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)
        except Exception as e:
            QMessageBox.critical(self.view, "File Write Error", f"Error writing header to file:\n{e}")

    def get_save_path(self):
        """为View提供获取初始保存路径的方法。"""
        return self.model.save_path

    def get_plot_titles(self):
        """从Model获取所有图表的标题信息。"""
        titles = {}
        for ch_name in self.model.channels.keys():
            info = self.model.get_channel_info_for_display(ch_name)
            titles[ch_name] = info['title']
        return titles

    def open_channel_config(self):
        """打开通道配置对话框。"""
        from gui import ChannelConfigDialog
        is_locked = self.is_running or self.is_manual_locked
        dlg = ChannelConfigDialog(self.model, self.view, is_locked=is_locked)
        dlg.config_changed.connect(self.on_channel_config_changed)
        dlg.exec_()

    def on_channel_config_changed(self, new_config):
        """处理来自ChannelConfigDialog的配置更改。"""
        self.model.update_channels(new_config)
        self.view.update_plot_titles()

    def choose_pidramp_file(self):
        """打开 PIDRAMP 编辑器对话框。"""
        try:
            from dialogs.pidramp_editor import PidRampEditorDialog
            dlg = PidRampEditorDialog(self.model, parent=self.view)
            if dlg.exec_() == QDialog.Accepted:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                cfg_path = os.path.join(base_dir, 'config', 'PIDRAMP.json')
                self._pending_pidramp_path = cfg_path
                try:
                    self.view.update_progress(f"PIDRAMP saved and loaded: {os.path.basename(cfg_path)}")
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self.view, "Error", f"Failed to open PIDRAMP editor: {e}")

    def load_pidramp_file(self, path: str = None):
        """载入指定或最近选择的 PIDRAMP 文件并应用到 model。"""
        try:
            selected = path or getattr(self, '_pending_pidramp_path', None)
            if not selected:
                selected, _ = QFileDialog.getOpenFileName(
                    self.view,
                    "Select PIDRAMP JSON to Load",
                    os.path.dirname(self.model.save_path) if self.model and self.model.save_path else os.getcwd(),
                    "JSON Files (*.json);;All Files (*)"
                )
                if not selected:
                    return

            try:
                success = self.model.load_pidramp(selected)
            except Exception as e:
                QMessageBox.critical(self.view, "Load Error", f"Failed to load PIDRAMP: {e}")
                return

            if success:
                QMessageBox.information(self.view, "PIDRAMP Loaded", f"PIDRAMP configuration loaded from:\n{selected}")
                try:
                    self.view.update_progress(f"PIDRAMP loaded: {os.path.basename(selected)}")
                except Exception:
                    pass
            else:
                QMessageBox.warning(self.view, "PIDRAMP", "Loaded file did not contain valid PIDRAMP configuration.")
        except Exception as e:
            QMessageBox.critical(self.view, "Error", f"Unexpected error: {e}")

    def set_manual_temperature(self, temp: float, ramp: float = None):
        """
        设置手动温度。
        - 样品回路 A: 写入 setpoint 并写入 ramp（ramp=None 使用 pid 表）
        - 腔体回路 B: 仅写入 setpoint
        """
        model = getattr(self, "model", None)
        if model is None:
            print("[Controller] No model attached; cannot apply temperature.")
            return

        try:
            if getattr(model, "kelvinion", None):
                model.kelvinion.set_temperature(temp, loop='A', ramp_override=ramp)
                model.kelvinion.set_temperature(lowerT(temp), loop='B', ramp_override=None)
                try:
                    model.sample_temp_changed.emit(temp)
                    model.chamber_temp_changed.emit(temp + 0.5)
                    model.current_temp_changed.emit(temp)
                except Exception:
                    pass
        except Exception as e:
            msg = f"[Controller] set_manual_temperature failed: {e}"
            print(msg)
            try:
                model.error_occurred.emit(msg)
            except Exception:
                pass

    def apply_pidramp_to_hardware(self):
        """将当前 model.pidramp 应用到已连接的 Kelvinion 仪器（设置 ramp 与 PID）。"""
        model = getattr(self, 'model', None)
        view = getattr(self, 'view', None)
        if model is None or view is None:
            QMessageBox.warning(None, "Apply PIDRAMP", "Model or View not available.")
            return

        kelvin = getattr(model, 'kelvinion', None)
        if kelvin is None:
            QMessageBox.warning(view, "Apply PIDRAMP", "Kelvinion instrument not initialized.")
            return

        def _parse_view_temp():
            try:
                txt = view.set_temp_edit.text().strip()
                return float(txt)
            except Exception:
                return None

        # 确定样品目标温度 (A)
        target_a = _parse_view_temp()
        if target_a is None:
            try:
                target_a = kelvin.get_set_temperature('A')
            except Exception:
                try:
                    target_a = model.get_sample_temperature()
                except Exception:
                    target_a = None

        # 确定腔体目标温度 (B)
        target_b = None
        if target_a is not None:
            try:
                target_b = kelvin.get_set_temperature('B')
            except Exception:
                try:
                    target_b = lowerT(target_a)
                except Exception:
                    target_b = None
        else:
            try:
                target_b = kelvin.get_set_temperature('B')
            except Exception:
                try:
                    target_b = model.get_chamber_temperature()
                except Exception:
                    target_b = None

        # 应用 ramp 和 PID
        try:
            if target_a is not None:
                view.update_progress(f"Applying sample ramp/PID for target {target_a:.2f} K...")
                kelvin.set_sample_ramp(target_a)
                kelvin.set_sample_pid(target_a)
                kelvin.set_sample_range(target_a)
            else:
                view.update_progress("Skipping sample ramp/PID: no valid sample target found.")

            if target_b is not None:
                view.update_progress(f"Applying chamber ramp/PID for target {target_b:.2f} K...")
                kelvin.set_chamber_ramp(target_b)
                kelvin.set_chamber_pid(target_b)
                kelvin.set_chamber_range(target_b)
            else:
                view.update_progress("Skipping chamber ramp/PID: no valid chamber target found.")

            QMessageBox.information(view, "Apply PIDRAMP", "PIDRAMP parameters applied to device.")
        except Exception as e:
            QMessageBox.critical(view, "Apply PIDRAMP Error", f"Failed to apply PIDRAMP to device: {e}")