# -*- coding: utf-8 -*-
import sys
import os
import csv
import datetime
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QFrame, QScrollArea, QSplitter,
    QMessageBox, QDialog, QCheckBox, QGridLayout, QGroupBox, QToolButton, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
import pyqtgraph as pg
from measure_core import MeasurementSystem
from controller import AppController
import numpy as np

# 导入其他模块模块
from ui_utils import get_labview_style, create_run_icon, create_stop_icon, create_lock_icon, create_labview_folder_icon
from widgets.temp_block_widget import TempBlockWidget
from dialogs.set_temp_dialog import SetTempDialog
from dialogs.channel_config_dialog import ChannelConfigDialog

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# =============================================================================
# Main Window (View) - 主窗口界面类
# =============================================================================
class MainWindow(QMainWindow):
    """
    低温测量系统的主窗口界面类。
    
    主要功能：
    - 系统状态显示（运行状态、锁定状态）
    - 温度序列管理（添加、删除温度块）
    - 实时温度显示（样品温度F通道、样品腔温度D通道）
    - 数据保存路径设置
    - 实时数据图表显示
    - 手动温度设置
    """
    def __init__(self, controller):
        super().__init__()
        self.setWindowTitle("Low Temperature Measurement System")
        self.resize(1200, 800)
        self.controller = controller
        self._setup_ui()
        self._connect_signals()
        self.is_running = False
        
    def _setup_ui(self):
        """
        初始化主窗口UI布局。
        
        布局结构：
        - 左侧面板：控制面板（状态、按钮、温度序列、温度显示）
        - 右侧面板：实时数据图表显示
        - 使用水平分割器，左侧固定宽度420px
        """
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        
        left_panel = self._create_left_panel()
        right_panel = self._create_right_panel()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([420, 780])
        splitter.handle(1).setDisabled(True)
        left_panel.setFixedWidth(420)

        main_layout.addWidget(splitter)
        # 定义可锁定的控件列表（运行时或手动锁定时禁用）
        self.lockable_widgets = [
            self.path_edit, self.path_btn,
            self.temp_blocks_container, self.add_block_btn, self.clear_all_btn,
            self.set_temp_edit,
        ]
        self.setStyleSheet(get_labview_style())
        
    def _connect_signals(self):
        """
        连接UI控件信号到控制器方法。
        
        信号连接：
        - 运行/停止按钮 -> 切换测量状态
        - 锁定按钮 -> 切换UI锁定状态
        - 退出按钮 -> 关闭应用
        - 路径按钮 -> 选择保存路径
        - 添加块按钮 -> 添加温度序列块
        - 清除所有按钮 -> 清除所有温度块
        - 通道设置按钮 -> 打开通道配置对话框
        - 设置温度输入框 -> 手动设置温度对话框
        """
        self.run_stop_btn.clicked.connect(self.controller.toggle_measurement)
        self.lock_btn.clicked.connect(self.controller.toggle_lock)
        self.quit_btn.clicked.connect(self._on_quit_clicked)
        self.path_btn.clicked.connect(self.controller.choose_path)
        self.add_block_btn.clicked.connect(self.controller.add_temp_block)
        self.clear_all_btn.clicked.connect(self.controller.clear_all_temp_blocks)
        self.channel_btn.clicked.connect(self.controller.open_channel_config)
        # PIDRAMP open/load buttons - 更稳健的连接：如果 controller 方法不存在则显示提示
        # 确保按钮可用
        self.open_pid_btn.setEnabled(True)
        self.load_pid_btn.setEnabled(True)

        if hasattr(self.controller, 'choose_pidramp_file'):
            self.open_pid_btn.clicked.connect(self.controller.choose_pidramp_file)
        else:
            self.open_pid_btn.clicked.connect(lambda: QMessageBox.warning(self, "Not ready", "Controller not ready to open PIDRAMP."))

        if hasattr(self.controller, 'load_pidramp_file'):
            # connect normally
            self.load_pid_btn.clicked.connect(self.controller.load_pidramp_file)
        else:
            self.load_pid_btn.clicked.connect(lambda: QMessageBox.warning(self, "Not ready", "Controller not ready to load PIDRAMP."))
        # connect apply button
        if hasattr(self.controller, 'apply_pidramp_to_hardware'):
            self.apply_pid_btn.clicked.connect(self.controller.apply_pidramp_to_hardware)
        else:
            self.apply_pid_btn.clicked.connect(lambda: QMessageBox.warning(self, "Not ready", "Controller not ready to apply PIDRAMP to device."))
        self.set_temp_edit.mousePressEvent = self._on_set_temp_edit_clicked

    def _create_left_panel(self):
        """
        创建左侧控制面板。
        
        面板结构（从上到下）：
        1. 系统状态面板 - 显示系统就绪和运行状态指示灯
        2. 状态显示文本框 - 显示当前操作状态信息
        3. 手动控制按钮 - RUN/STOP、LOCK、QUIT按钮
        4. 数据保存路径设置
        5. 温度序列管理区域（可滚动）
        6. 温度显示区域（样品温度、样品腔温度、设置温度）
        7. 通道设置按钮
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # --- 上部：系统状态面板 ---
        status_group = self._create_status_panel()
        layout.addWidget(status_group)

        # --- 状态显示文本框 ---
        self.status_display = QLineEdit("System Ready")
        self.status_display.setReadOnly(True)
        self.status_display.setStyleSheet("background-color: #e9ecef; border: 1px solid #ced4da; border-radius: 4px; padding: 4px; color: #495057;")
        layout.addWidget(self.status_display)
        
        # --- 错误信息显示区域 ---
        self.error_display = QLineEdit("")
        self.error_display.setReadOnly(True)
        self.error_display.setStyleSheet("background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 4px; color: #721c24;")
        self.error_display.setVisible(False)  # 默认隐藏
        layout.addWidget(self.error_display)

        # --- 手动控制按钮面板 ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_height = 40
        icon_size = QSize(24, 24)

        # RUN/STOP按钮 - 启动/停止测量序列
        self.run_stop_btn = QToolButton()
        self.run_stop_btn.setText("RUN")
        self.run_stop_btn.setIcon(create_run_icon())
        self.run_stop_btn.setIconSize(icon_size)
        self.run_stop_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.run_stop_btn.setCheckable(True)
        self.run_stop_btn.setMinimumHeight(btn_height)
        self.run_stop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # LOCK按钮 - 锁定/解锁UI控件
        self.lock_btn = QToolButton()
        self.lock_btn.setText("LOCK")
        self.lock_btn.setIcon(create_lock_icon())
        self.lock_btn.setIconSize(icon_size)
        self.lock_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setMinimumHeight(btn_height)
        self.lock_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # QUIT按钮 - 退出应用程序
        self.quit_btn = QToolButton()
        self.quit_btn.setText("QUIT")
        self.quit_btn.setIconSize(icon_size)
        self.quit_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.quit_btn.setMinimumHeight(btn_height)
        self.quit_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.quit_btn.setStyleSheet("QToolButton {background-color: red;color: white;border: 1px solid red;}QToolButton:hover { background-color: pink; }QToolButton:pressed { background-color: darkred; }")

        btn_layout.addWidget(self.run_stop_btn)
        btn_layout.addWidget(self.lock_btn)
        btn_layout.addWidget(self.quit_btn)

        layout.addLayout(btn_layout)
        
        layout.addWidget(self._create_path_panel())

        # --- 中部 (拉伸填满) ---
        
        layout.addWidget(self._create_sequence_panel(), 1) # 占据所有剩余空间

        # --- 下部 (固定在底部) ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0,0,0,0)
        bottom_layout.setSpacing(10)
        
        # --- 温度显示区域 ---
        # 样品温度显示（F通道）- 显示样品实际温度
        sample_temp_row = QHBoxLayout()
        sample_temp_row.setContentsMargins(0,0,0,0); sample_temp_row.setSpacing(8)
        sample_temp_row.addWidget(QLabel("Sample Temp[K]:"))
        self.sample_temp_edit = QLineEdit("--"); self.sample_temp_edit.setReadOnly(True); self.sample_temp_edit.setFixedWidth(70)
        sample_temp_row.addWidget(self.sample_temp_edit)
        sample_temp_row.addStretch()
        bottom_layout.addLayout(sample_temp_row)
        
        # 样品腔温度显示（D通道）- 显示样品腔环境温度
        chamber_temp_row = QHBoxLayout()
        chamber_temp_row.setContentsMargins(0,0,0,0); chamber_temp_row.setSpacing(8)
        chamber_temp_row.addWidget(QLabel("Chamber Temp[K]:"))
        self.chamber_temp_edit = QLineEdit("--"); self.chamber_temp_edit.setReadOnly(True); self.chamber_temp_edit.setFixedWidth(70)
        chamber_temp_row.addWidget(self.chamber_temp_edit)
        chamber_temp_row.addStretch()
        bottom_layout.addLayout(chamber_temp_row)
        
        # 设置温度输入框 - 用于手动设置目标温度
        set_temp_row = QHBoxLayout()
        set_temp_row.setContentsMargins(0,0,0,0); set_temp_row.setSpacing(8)
        set_temp_row.addWidget(QLabel("Set Temp[K]:"))
        self.set_temp_edit = QLineEdit("--"); self.set_temp_edit.setFixedWidth(70)
        set_temp_row.addWidget(self.set_temp_edit)
        set_temp_row.addStretch()
        bottom_layout.addLayout(set_temp_row)
        
        # Channel Settings 放在单独一行，占满宽度
        self.channel_btn = QPushButton("Channel Settings")
        self.channel_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bottom_layout.addWidget(self.channel_btn)

        # 下一行放置三个配置按钮，水平排列，三个按钮等宽并填满与上方 channel_btn 相同的可用宽度
        pid_btn_row = QHBoxLayout()
        pid_btn_row.setContentsMargins(0, 0, 0, 0)
        pid_btn_row.setSpacing(8)
        # 按钮名称
        self.open_pid_btn = QPushButton("Open Config")
        self.load_pid_btn = QPushButton("Load Config")
        self.apply_pid_btn = QPushButton("Apply Config")
        # 按钮等宽扩展以对齐 channel_btn 的左右边距
        self.open_pid_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.load_pid_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.apply_pid_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pid_btn_row.addWidget(self.open_pid_btn)
        pid_btn_row.addWidget(self.load_pid_btn)
        pid_btn_row.addWidget(self.apply_pid_btn)
        bottom_layout.addLayout(pid_btn_row)


        
        layout.addWidget(bottom_widget)
        
        return container

    def _create_status_panel(self):
        """
        创建系统状态面板。
        
        包含：
        - 系统就绪状态指示灯（绿色表示就绪）
        - 序列运行状态指示灯（绿色表示正在运行）
        """
        status_group = QGroupBox("System Status")
        status_layout = QHBoxLayout(status_group)
        # 系统就绪状态指示灯
        self.status_lamp = QCheckBox(); self.status_lamp.setChecked(True); self.status_lamp.setEnabled(False)
        self.status_lamp.setStyleSheet("""
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
                border-radius: 11px;
            }
            QCheckBox::indicator:checked {
                background-color: qradialgradient(spread:pad, cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.4, stop:0 rgba(230, 255, 230, 255), stop:0.5 rgba(139, 226, 139, 255), stop:1 rgba(76, 175, 80, 255));
                border: 1px solid #43a047;
            }
            QCheckBox::indicator:unchecked {
                background-color: qradialgradient(spread:pad, cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.4, stop:0 rgba(250, 250, 250, 255), stop:0.5 rgba(224, 224, 224, 255), stop:1 rgba(189, 189, 189, 255));
                border: 1px solid #a0a0a0;
            }
        """)
        self.run_status_label = QLabel("Sequence Run")
        self.run_status_lamp = QCheckBox(); self.run_status_lamp.setEnabled(False); self.run_status_lamp.setChecked(False)
        self.run_status_lamp.setStyleSheet("""
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
                border-radius: 11px;
            }
            QCheckBox::indicator:checked {
                background-color: qradialgradient(spread:pad, cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.4, stop:0 rgba(230, 255, 230, 255), stop:0.5 rgba(139, 226, 139, 255), stop:1 rgba(76, 175, 80, 255));
                border: 1px solid #43a047;
            }
            QCheckBox::indicator:unchecked {
                background-color: qradialgradient(spread:pad, cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.4, stop:0 rgba(250, 250, 250, 255), stop:0.5 rgba(224, 224, 224, 255), stop:1 rgba(189, 189, 189, 255));
                border: 1px solid #a0a0a0;
            }
        """)
        status_layout.addWidget(QLabel("System Ready")); status_layout.addWidget(self.status_lamp)
        status_layout.addSpacing(30); status_layout.addWidget(self.run_status_label); status_layout.addWidget(self.run_status_lamp)
        status_layout.addStretch()
        return status_group

    def _create_path_panel(self):
        path_group = QGroupBox("Data Path")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(self.controller.get_save_path())
        self.path_btn = QPushButton(); self.path_btn.setIcon(create_labview_folder_icon())
        path_layout.addWidget(QLabel("Save Path:")); path_layout.addWidget(self.path_edit); path_layout.addWidget(self.path_btn)
        return path_group

    def _create_sequence_panel(self):
        temp_group = QGroupBox("Sequence")
        temp_layout = QVBoxLayout(temp_group)
        self.temp_blocks = []
        self.temp_blocks_container = QWidget()
        self.temp_blocks_layout = QVBoxLayout(self.temp_blocks_container)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.temp_blocks_container)
        self.scroll_area.setMinimumHeight(300)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.add_block_btn = QPushButton("Add Block")
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setObjectName("clearAllButton")
        btns_layout = QHBoxLayout()
        btns_layout.addWidget(self.add_block_btn); btns_layout.addWidget(self.clear_all_btn); btns_layout.addStretch()
        temp_layout.addWidget(self.scroll_area)
        temp_layout.addLayout(btns_layout)
        self.temp_blocks_layout.addStretch()  # 只添加一个stretch
        return temp_group

    def _create_manual_control_panel(self):
        manual_group = QGroupBox("Manual Control")
        manual_layout = QVBoxLayout(manual_group)
        temp_disp_group = QGroupBox("Temperature Status")
        temp_disp_layout = QHBoxLayout(temp_disp_group)
        self.current_temp_edit = QLineEdit("--"); self.current_temp_edit.setReadOnly(True)
        self.set_temp_edit = QLineEdit("--"); self.set_temp_edit.installEventFilter(self)
        temp_disp_layout.addWidget(QLabel("Temp[K]:")); temp_disp_layout.addWidget(self.current_temp_edit)
        temp_disp_layout.addWidget(QLabel("Set Temp[K]:")); temp_disp_layout.addWidget(self.set_temp_edit)
        manual_layout.addWidget(temp_disp_group)
        return manual_group

    def _create_right_panel(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot_grid = pg.GraphicsLayoutWidget()
        self.plot_grid.setBackground('#fcfcfc')
        layout.addWidget(self.plot_grid)
        self.plot_items = {}
        ch_names = list(self.controller.model.channels.keys())
        plot_positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        tickFont = QFont("Segoe UI", 9)
        for i, (ch, pos) in enumerate(zip(ch_names, plot_positions)):
            color = self.controller.model.channels[ch].get('color', '#808080')
            plot = self.plot_grid.addPlot(row=pos[0], col=pos[1])
            plot.setMenuEnabled(True)
            # 极简扁平风网格
            plot.showGrid(x=True, y=True, alpha=0.7)
            plot.showAxis('top'); plot.showAxis('right')
            plot.getAxis('top').setStyle(showValues=False)
            plot.getAxis('right').setStyle(showValues=False)
            plot.getAxis('left').setPen(pg.mkPen(color='#888', width=1))
            plot.getAxis('bottom').setPen(pg.mkPen(color='#888', width=1))
            plot.getAxis('left').setTextPen(pg.mkPen(color='#222'))
            plot.getAxis('bottom').setTextPen(pg.mkPen(color='#222'))
            plot.getAxis('left').setTickFont(tickFont)
            plot.getAxis('bottom').setTickFont(tickFont)
            plot.getViewBox().setBackgroundColor('#fcfcfc')
            plot.getViewBox().setBorder(None)
            plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            # 标题/标签
            plot.setLabel('bottom', '<span style="color:#222; font-family: Segoe UI; font-size: 11pt; font-weight:600;">Temp [K]</span>')
            self.plot_items[ch] = plot
        self.update_plot_titles()
        return container

    def update_sample_temp_display(self, temp):
        """
        更新样品温度显示（F通道）。
        
        Args:
            temp (float): 样品温度值，单位为K
        """
        self.sample_temp_edit.setText(f"{temp:.3f}")
    
    def update_chamber_temp_display(self, temp):
        """
        更新样品腔温度显示（D通道）。 
        
        Args:
            temp (float): 样品腔温度值，单位为K
        """
        self.chamber_temp_edit.setText(f"{temp:.3f}")

    def update_progress(self, message):
        self.status_display.setText(message)
    
    def show_error(self, error_message):
        """
        显示错误信息。
        
        Args:
            error_message (str): 错误信息文本
        """
        self.error_display.setText(f"ERROR: {error_message}")
        self.error_display.setVisible(True)
        # 设置错误样式
        self.error_display.setStyleSheet("background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 4px; color: #721c24;")
    
    def clear_error(self):
        """清除错误信息显示"""
        self.error_display.setVisible(False)
        self.error_display.setText("")
    
    def show_warning(self, warning_message):
        """
        显示警告信息。
        
        Args:
            warning_message (str): 警告信息文本
        """
        self.error_display.setText(f"WARNING: {warning_message}")
        self.error_display.setVisible(True)
        # 设置警告样式
        self.error_display.setStyleSheet("background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 4px; color: #856404;")

    def update_set_temp_display(self, temp):
        self.set_temp_edit.setText(f"{temp:.3f}")

    def update_running_status(self, is_running):
        self.run_status_lamp.setChecked(is_running)

    def highlight_running_block(self, running_index):
        """高亮当前正在执行的温度块。"""
        for i, block in enumerate(self.temp_blocks):
            is_currently_executing = (i == running_index)
            
            # 重新应用样式，确保状态正确
            block.check_edited(is_currently_executing=is_currently_executing)

    def set_ui_locked(self, is_manual_locked, is_running):
        self.lock_btn.setChecked(is_manual_locked)
        self.lock_btn.setEnabled(not is_running)
        self.run_stop_btn.setEnabled(True)
        self.run_stop_btn.setChecked(is_running)
        self._update_run_stop_button_style(is_running)
        for widget in self.lockable_widgets:
            widget.setEnabled(not is_manual_locked and not is_running)
        for block in getattr(self, 'temp_blocks', []):
            for w in [block.start, block.stop, block.step, block.ramp]:
                w.setReadOnly(is_manual_locked or is_running)
            block.end_checkbox.setEnabled(not is_manual_locked and not is_running)
        self.run_stop_btn.setStyleSheet("")
        self.lock_btn.setStyleSheet("")

    def plot_data_batch(self, data_by_ch, clear=True):
        """
        批量绘制或追加数据到右侧图表。
        
        Args:
            data_by_ch (dict): 通道数据字典，格式为 {ch: {'x': [...], 'y': [...]}}
            clear (bool): 是否清除现有数据后重新绘制
        """
        for ch, plot_item in self.plot_items.items():
            if clear:
                plot_item.clear()
            if ch in data_by_ch and data_by_ch[ch]['x']:
                color = self.controller.model.channels[ch].get('color', '#808080')
                pen = pg.mkPen(color=color, width=2)
                symbolBrush = pg.mkBrush(color)
                symbolPen = pg.mkPen('w', width=1)
                plot_item.plot(data_by_ch[ch]['x'], data_by_ch[ch]['y'], pen=pen, symbol='o', symbolSize=8, symbolBrush=symbolBrush, symbolPen=symbolPen)

    def update_plots_from_file(self, file_path):
        """
        读取历史数据文件并绘制到右侧图表。
        
        Args:
            file_path (str): 数据文件路径，支持CSV格式
        """
        import csv
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header or len(header) < 3:
                    return
                temp_idx = 1
                ch_indices = {}
                for i, h in enumerate(header):
                    if h.startswith('Resistance_'):
                        ch_name = h.split('_')[1].split('[')[0]
                        ch_indices[ch_name] = i
                data_by_ch = {ch: {'x': [], 'y': []} for ch in ch_indices}
                for row in reader:
                    if len(row) < max(ch_indices.values())+1:
                        continue
                    try:
                        temp = float(row[temp_idx])
                        for ch, idx in ch_indices.items():
                            val = row[idx]
                            if 'X' in val or val.strip() == '':
                                continue
                            y = float(val)
                            data_by_ch[ch]['x'].append(temp)
                            data_by_ch[ch]['y'].append(y)
                    except Exception:
                        continue
                self.plot_data_batch(data_by_ch, clear=True)
        except Exception as e:
            print(f"[update_plots_from_file] Error: {e}")

    def handle_new_data(self, temp, resistances):
        """
        处理新的测量数据并更新图表。
        
        Args:
            temp (float): 当前温度值
            resistances (dict): 各通道的电阻值字典
        """
        # 先取出现有数据，再追加新点
        data_by_ch = {ch: {'x': [], 'y': []} for ch in self.plot_items}
        for ch, plot_item in self.plot_items.items():
            data_items = plot_item.listDataItems()
            if data_items:
                data_by_ch[ch]['x'] = list(data_items[0].xData)
                data_by_ch[ch]['y'] = list(data_items[0].yData)
        for ch_name, res_value in resistances.items():
            if ch_name in data_by_ch and res_value is not None:
                data_by_ch[ch_name]['x'].append(temp)
                data_by_ch[ch_name]['y'].append(res_value)
        self.plot_data_batch(data_by_ch, clear=True)

    def clear_plots(self):
        for plot_item in self.plot_items.values():
            plot_item.clear()

    def update_plot_titles(self):
        titles = self.controller.get_plot_titles()
        for ch_name, title in titles.items():
            if ch_name in self.plot_items:
                title_html = f'<span style="font-family: Segoe UI; font-size: 12pt; font-weight:600; color:#222;">{title}</span>'
                self.plot_items[ch_name].setTitle(title_html)

    def add_temp_block(self):
        # 先移除末尾stretch
        layout = self.temp_blocks_layout
        if layout.count() > 0 and isinstance(layout.itemAt(layout.count()-1).widget(), type(None)):
            layout.takeAt(layout.count()-1)
        block = TempBlockWidget()
        self.temp_blocks.append(block)
        layout.addWidget(block)
        # 添加分隔线（除了第一个块）
        if len(self.temp_blocks) > 1:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("color: #d0d7de; background: #d0d7de; height: 0.5px; margin: 0;")
            layout.insertWidget(layout.count()-1, line)
        layout.addStretch()  # 重新添加stretch
        self.set_ui_locked(self.lock_btn.isChecked(), self.run_stop_btn.isChecked())

    def clear_all_temp_blocks(self):
        # 移除所有widget和stretch
        layout = self.temp_blocks_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.temp_blocks.clear()
        for i in range(3):
            self.add_temp_block()
        # 保证只有一个stretch
        if layout.count() == 0 or not isinstance(layout.itemAt(layout.count()-1).widget(), type(None)):
            layout.addStretch()
        self.set_ui_locked(self.lock_btn.isChecked(), self.run_stop_btn.isChecked())

    def get_sequence_data(self):
        sequence_data = []
        for block_widget in self.temp_blocks:
            # 检查是否有有效的非空输入（包括缺省值）
            if all(w.text().strip() for w in [block_widget.start, block_widget.stop, block_widget.step, block_widget.ramp]):
                sequence_data.append({
                    'start': block_widget.start.text(), 'stop': block_widget.stop.text(),
                    'step': block_widget.step.text(), 'ramp': block_widget.ramp.text(),
                    'end': block_widget.end_checkbox.isChecked()
                })
        return sequence_data

    def get_save_path(self):
        return self.path_edit.text()

    def set_save_path(self, path):
        self.path_edit.setText(path)
    

    def closeEvent(self, event):
        self.controller._stop_measurement()
        event.accept()

    def _on_set_temp_edit_clicked(self, event):
        """
        打开 SetTempDialog 获取 temp, ramp；交由 controller.set_manual_temperature 处理。
        """
        # 如果系统在运行中，可按需阻止
        if getattr(self.controller, "is_running", False):
            QMessageBox.warning(self, "运行中", "系统正在运行，无法手动设置温度。")
            return

        dlg = SetTempDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            temp, ramp = dlg.get_values()
            if temp is None:
                QMessageBox.warning(self, "输入错误", "请输入有效的温度数值！")
                return

            # 更新 UI 显示 set temp 文本框（保留两位小数）
            try:
                self.set_temp_edit.setText(f"{temp:.2f}")
            except Exception:
                pass

            # 委托 controller 处理（controller 将负责同时写 A 和 B）
            try:
                if hasattr(self, "controller") and hasattr(self.controller, "set_manual_temperature"):
                    self.controller.set_manual_temperature(temp, ramp=ramp)
                else:
                    QMessageBox.warning(self, "未实现", "控制器未实现 set_manual_temperature 接口。")
            except Exception as e:
                QMessageBox.critical(self, "设定失败", f"设置温度失败：{e}")

    def _on_quit_clicked(self):
        self.close()

    def _update_run_stop_button_style(self, is_running):
        if is_running:
            self.run_stop_btn.setText("STOP")
            self.run_stop_btn.setIcon(create_stop_icon())
            self.run_stop_btn.setStyleSheet("""
                QToolButton { 
                    background-color: #f8d7da; 
                    color: #721c24; 
                    border: 1px solid #f5c6cb; 
                    font-weight: bold;
                }
                QToolButton:hover { background-color: #f4b6bc; }
                QToolButton:pressed { background-color: #f1aeb5; }
            """)
        else:
            self.run_stop_btn.setText("RUN")
            self.run_stop_btn.setIcon(create_run_icon())
            self.run_stop_btn.setStyleSheet("")

# =============================================================================
# Application Entry Point
# =============================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    model = MeasurementSystem()
    controller = AppController(model)
    main_win = MainWindow(controller)
    controller.set_view(main_win)
    controller.initialize_ui()
    main_win.show()
    sys.exit(app.exec_())