# -*- coding: utf-8 -*-
import sys
import os
import csv
import datetime
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QFrame, QScrollArea, QSplitter,
    QMessageBox, QDialog, QCheckBox, QGridLayout, QGroupBox, QToolButton, QSizePolicy, QComboBox, QStyle, QProgressBar
)
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont, QIcon
import pyqtgraph as pg
from measure_core import MeasurementSystem
from controller import AppController
import numpy as np

# 导入其他模块模块
from ui_utils import get_labview_style, create_run_icon, create_stop_icon
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
    - 通道配置
    - PID配置管理
    """
    def __init__(self, controller):
        super().__init__()
        self.setWindowTitle("Low Temperature Measurement System")
        self.resize(1400, 800)
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
        - 使用水平分割器，左侧固定宽度400px
        - 右侧自适应宽度，最小宽度800px
        """
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        
        left_panel = self._create_left_panel()
        right_panel = self._create_right_panel()


        left_panel.setFixedWidth(420)
        right_panel.setMinimumWidth(600)        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)
        # 定义可锁定的控件列表（运行时或手动锁定时禁用）
        self.lockable_widgets = [
            self.path_edit, self.path_btn,
            self.temp_blocks_container, self.add_block_btn, self.clear_all_btn,
            self.save_blocks_btn, self.load_blocks_btn,
            self.set_temp_edit, self.channel_btn,
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
        self.quit_btn.clicked.connect(self._on_quit_clicked)
        self.path_btn.clicked.connect(self.controller.choose_path)
        
        self.add_block_btn.clicked.connect(self.controller.add_temp_block)
        self.clear_all_btn.clicked.connect(self.controller.clear_all_temp_blocks)
        self.save_blocks_btn.clicked.connect(self.controller.save_temp_blocks)
        self.load_blocks_btn.clicked.connect(self.controller.load_temp_blocks)

        self.channel_btn.clicked.connect(self.controller.open_channel_config)

        self.open_pid_btn.clicked.connect(self.controller.choose_pidramp_file)
        self.load_pid_btn.clicked.connect(self.controller.load_pidramp_file)
        self.apply_pid_btn.clicked.connect(self.controller.apply_pidramp_to_hardware)

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
        8. PID配置按钮组（打开、加载、应用）
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

        # QUIT按钮 - 退出应用程序
        self.quit_btn = QToolButton()
        self.quit_btn.setText("QUIT")
        self.quit_btn.setIconSize(icon_size)
        self.quit_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.quit_btn.setMinimumHeight(btn_height)
        self.quit_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.quit_btn.setStyleSheet("QToolButton {background-color: red;color: white;border: 1px solid red;}QToolButton:hover { background-color: pink; }QToolButton:pressed { background-color: darkred; }")

        btn_layout.addWidget(self.run_stop_btn)
        btn_layout.addWidget(self.quit_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(self._create_path_panel())

        # --- 中部 (拉伸填满) ---
        
        layout.addWidget(self._create_sequence_panel(), 1) # 占据所有剩余空间

        self.progressbar = QProgressBar()
        self.progressbar.setValue(0)
        self.progressbar.setTextVisible(True)
        self.progressbar.setFormat("Progress: %v/%m")
        self.progressbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(self.progressbar)


        # --- 下部 (固定在底部) ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0,0,0,0)
        bottom_layout.setSpacing(10)
        
        # --- 温度显示区域 ---
        # 使用 GridLayout 确保标签和输入框对齐
        temp_grid = QGridLayout()
        temp_grid.setContentsMargins(0, 0, 0, 0)
        temp_grid.setSpacing(8)
        temp_grid.setColumnStretch(1, 0)  # 输入框列不拉伸
        temp_grid.setColumnStretch(2, 0)  # 功率显示列不拉伸
        temp_grid.setColumnStretch(3, 1)   # 右侧空白列拉伸
        
        # 样品温度显示（F通道）- 显示样品实际温度
        sample_temp_label = QLabel("Sample [K]:")
        self.sample_temp_edit = QLineEdit("--")
        self.sample_temp_edit.setReadOnly(True)
        self.sample_temp_edit.setFixedWidth(70)
        temp_grid.addWidget(sample_temp_label, 0, 0)
        temp_grid.addWidget(self.sample_temp_edit, 0, 1)
        
        # 样品功率显示
        sample_power_label = QLabel("OUTPUT:")
        self.sample_power_bar = QProgressBar()
        self.sample_power_bar.setObjectName("heaterbar")
        self.sample_power_bar.setMinimum(0)
        self.sample_power_bar.setMaximum(100)
        self.sample_power_bar.setValue(0)
        self.sample_power_bar.setFixedWidth(40)
        self.sample_power_bar.setFixedHeight(10)  # 设置固定高度
        self.sample_power_bar.setTextVisible(False)  # 不显示文本，使用旁边的标签

        self.sample_power_value = QLabel("--")
        self.sample_power_value.setFixedWidth(40)
        self.sample_power_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sample_power_row = QHBoxLayout()
        sample_power_row.setContentsMargins(0, 0, 0, 0)
        sample_power_row.setSpacing(4)
        # sample_power_row.addWidget(sample_power_label)
        sample_power_row.addWidget(self.sample_power_bar)
        sample_power_row.addWidget(self.sample_power_value)
        sample_power_widget = QWidget()
        sample_power_widget.setLayout(sample_power_row)
        temp_grid.addWidget(sample_power_widget, 0, 2)
        
        # 样品腔温度显示（D通道）- 显示样品腔环境温度
        chamber_temp_label = QLabel("Chamber [K]:")
        self.chamber_temp_edit = QLineEdit("--")
        self.chamber_temp_edit.setReadOnly(True)
        self.chamber_temp_edit.setFixedWidth(70)
        temp_grid.addWidget(chamber_temp_label, 1, 0)
        temp_grid.addWidget(self.chamber_temp_edit, 1, 1)
        
        # 腔体功率显示
        chamber_power_label = QLabel("OUTPUT:")
        self.chamber_power_bar = QProgressBar()
        self.chamber_power_bar.setObjectName("heaterbar")
        self.chamber_power_bar.setMinimum(0)
        self.chamber_power_bar.setMaximum(100)
        self.chamber_power_bar.setValue(0)
        self.chamber_power_bar.setFixedWidth(40)
        self.chamber_power_bar.setFixedHeight(10)  # 设置固定高度
        self.chamber_power_bar.setTextVisible(False)  # 不显示文本，使用旁边的标签

        self.chamber_power_value = QLabel("--")
        self.chamber_power_value.setFixedWidth(40)
        self.chamber_power_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        chamber_power_row = QHBoxLayout()
        chamber_power_row.setContentsMargins(0, 0, 0, 0)
        chamber_power_row.setSpacing(4)
        # chamber_power_row.addWidget(chamber_power_label)
        chamber_power_row.addWidget(self.chamber_power_bar)
        chamber_power_row.addWidget(self.chamber_power_value)
        chamber_power_widget = QWidget()
        chamber_power_widget.setLayout(chamber_power_row)
        temp_grid.addWidget(chamber_power_widget, 1, 2)
        
        # 设置温度输入框 - 用于手动设置目标温度
        set_temp_label = QLabel("Set Temp[K]:")
        self.set_temp_edit = QLineEdit("--")
        self.set_temp_edit.setFixedWidth(70)
        temp_grid.addWidget(set_temp_label, 2, 0)
        temp_grid.addWidget(self.set_temp_edit, 2, 1)
        
        bottom_layout.addLayout(temp_grid)
        
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
        self.path_btn = QPushButton(); self.path_btn.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
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
        self.scroll_area.setMinimumHeight(150)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.add_block_btn = QPushButton("Add Block")
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setObjectName("clearAllButton")
        self.save_blocks_btn = QPushButton()
        self.save_blocks_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_blocks_btn.setToolTip("保存当前温度块配置为 JSON")
        self.save_blocks_btn.setFixedWidth(36)
        self.load_blocks_btn = QPushButton()
        self.load_blocks_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.load_blocks_btn.setToolTip("从 JSON 文件加载温度块配置")
        self.load_blocks_btn.setFixedWidth(36)
        btns_layout = QHBoxLayout()
        btns_layout.addWidget(self.add_block_btn)
        btns_layout.addWidget(self.clear_all_btn)
        btns_layout.addWidget(self.save_blocks_btn)
        btns_layout.addWidget(self.load_blocks_btn)
        btns_layout.addStretch()
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
        
        # 使用 Tab 控件在右侧切换不同功能页（Resistance / SweepIV）
        from PyQt5.QtWidgets import QTabWidget

        self.tab_widget = QTabWidget()

        # --- Resistance Tab （原有四图布局） ---
        res_tab = QWidget()
        res_layout = QVBoxLayout(res_tab)
        self.plot_grid = pg.GraphicsLayoutWidget()
        self.plot_grid.setBackground('#fcfcfc')
        res_layout.addWidget(self.plot_grid)
        self.plot_items = {}
        ch_names = list(self.controller.model.channels.keys())
        plot_positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        tickFont = QFont("Segoe UI", 9)
        for i, (ch, pos) in enumerate(zip(ch_names, plot_positions)):
            color = self.controller.model.channels[ch].get('color', '#808080')
            plot = self.plot_grid.addPlot(row=pos[0], col=pos[1])
            plot.setMenuEnabled(True)
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
            plot.setLabel('bottom', '<span style="color:#222; font-family: Segoe UI; font-size: 11pt; font-weight:600;">Temp [K]</span>')
            self.plot_items[ch] = plot
        self.update_plot_titles()

        # --- SweepIV Tab ---
        sweep_tab = QWidget()
        sweep_layout = QVBoxLayout(sweep_tab)
        sweep_layout.setContentsMargins(20, 20, 20, 20)
        sweep_layout.setSpacing(10)
        # Sweep plot (横轴为 Voltage, 纵轴为 Current)
        self.sweep_plot = pg.PlotWidget()
        self.sweep_plot.setBackground('#fcfcfc')
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.setLabel('bottom', 'Voltage [V]')
        self.sweep_plot.setLabel('left', 'Current [A]')
        self.sweep_plot.setMinimumHeight(280)
        sweep_layout.addWidget(self.sweep_plot, 1)

        # --- Sweep 参数（直接展示，无边框容器，位于图下方） ---
        sweep_params_widget = QWidget()
        sweep_params_layout = QHBoxLayout(sweep_params_widget)
        sweep_params_layout.setContentsMargins(0, 0, 0, 0)
        sweep_params_layout.setSpacing(8)
        sweep_params_layout.addWidget(QLabel('Start I [A]:'))
        self.sweep_start_edit = QLineEdit('1e-6'); self.sweep_start_edit.setFixedWidth(90)
        sweep_params_layout.addWidget(self.sweep_start_edit)
        sweep_params_layout.addWidget(QLabel('Stop I [A]:'))
        self.sweep_stop_edit = QLineEdit('1e-3'); self.sweep_stop_edit.setFixedWidth(90)
        sweep_params_layout.addWidget(self.sweep_stop_edit)
        sweep_params_layout.addWidget(QLabel('Step I [A]:'))
        self.sweep_step_edit = QLineEdit('1e-6'); self.sweep_step_edit.setFixedWidth(90)
        sweep_params_layout.addWidget(self.sweep_step_edit)
        sweep_params_layout.addWidget(QLabel('Channel:'))
        self.sweep_channel_combo = QComboBox()
        self.sweep_channel_combo.addItems(['CH1', 'CH2', 'CH3', 'CH4'])
        self.sweep_channel_combo.setCurrentIndex(0)
        self.sweep_channel_combo.setFixedWidth(90)
        self.sweep_channel_combo.setStyleSheet('QComboBox { background-color: white; }')
        
        sweep_params_layout.addWidget(self.sweep_channel_combo)
        sweep_params_layout.addStretch()
        sweep_layout.addWidget(sweep_params_widget)

        self.tab_widget.addTab(res_tab, 'Resistance')
        self.tab_widget.addTab(sweep_tab, 'SweepIV')

        # Sweep 绘图状态：图例、颜色映射、已绘制曲线引用
        self.sweep_legend = None
        self.sweep_color_map = {}
        self.sweep_color_index = 0
        self.sweep_traces = {}

        layout.addWidget(self.tab_widget)
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
    
    def update_sample_power_display(self, power):
        """
        更新样品功率显示。
        
        Args:
            power (float): 样品功率值，0~100的百分比
        """
        try:
            power_val = float(power)  # 确保转换为浮点数
            power_val = max(0.0, min(100.0, power_val))  # 限制在0~100范围
            bar_value = int(round(power_val))  # 四舍五入到整数
            self.sample_power_bar.setValue(bar_value)
            self.sample_power_bar.update()  # 强制更新进度条显示
            self.sample_power_value.setText(f"{power_val:.1f}%")
        except (ValueError, TypeError) as e:
            print(f"[Power] Error updating sample power: {e}, power={power}")
            self.sample_power_bar.setValue(0)
            self.sample_power_value.setText("--")
    
    def update_chamber_power_display(self, power):
        """
        更新腔体功率显示。
        
        Args:
            power (float): 腔体功率值，0~100的百分比
        """
        try:
            power_val = float(power)  # 确保转换为浮点数
            power_val = max(0.0, min(100.0, power_val))  # 限制在0~100范围
            bar_value = int(round(power_val))  # 四舍五入到整数
            self.chamber_power_bar.setValue(bar_value)
            self.chamber_power_bar.update()  # 强制更新进度条显示
            self.chamber_power_value.setText(f"{power_val:.1f}%")
        except (ValueError, TypeError) as e:
            print(f"[Power] Error updating chamber power: {e}, power={power}")
            self.chamber_power_bar.setValue(0)
            self.chamber_power_value.setText("--")

    def update_progress(self, message):
        self.status_display.setText(message)

    def set_total_steps(self, total_steps):
        self.progressbar.setMaximum(total_steps)
        self.progressbar.setValue(0)

    def update_step_progress(self, current_step):
        self.progressbar.setValue(current_step)
    
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

    def get_mode(self):
        """返回当前右侧选中的模式：'Resistance' 或 'SweepIV'"""
        idx = self.tab_widget.currentIndex()
        if idx == 0:
            return 'Resistance'
        elif idx == 1:
            return 'SweepIV'
        
        return 'Resistance'

    def get_sweep_params(self):
        """从 SweepIV 选项卡读取起始/结束/步长电流参数，返回 dict。"""
        try:
            start = float(self.sweep_start_edit.text())
            stop = float(self.sweep_stop_edit.text())
            step = float(self.sweep_step_edit.text())
        except Exception:
            return None
        # 读取所选通道
        try:
            channel = str(self.sweep_channel_combo.currentText())
        except Exception:
            channel = 'CH1'
        return {'start': start, 'stop': stop, 'step': step, 'channel': channel}

    def handle_new_sweep(self, temp, ch_name, currents, voltages):
        """在 SweepIV 选项卡上绘制新的一次 IV 扫描结果。
        Args:
            temp (float): 当前温度
            ch_name (str): 通道名
            currents (list[float]): 电流序列
            voltages (list[float]): 对应电压序列
        """
        try:
            # 使用显示温度作为图例标签
            label = f"{temp:.3f} K"

            # 颜色分配：相同温度使用相同颜色，按插入顺序分配新颜色
            if label in self.sweep_color_map:
                color = self.sweep_color_map[label]
            else:
                # 生成一个可辨识的颜色
                color = pg.intColor(self.sweep_color_index, hues=12, values=255)
                self.sweep_color_map[label] = color
                self.sweep_color_index += 1

            pen = pg.mkPen(color=color, width=2)

            # 创建图例（只创建一次）
            try:
                if self.sweep_legend is None:
                    self.sweep_legend = self.sweep_plot.addLegend(offset=(10, 10))
            except Exception:
                # 如果图例创建失败，也不要影响绘图
                self.sweep_legend = None

            # 绘制：x=Voltage, y=Current。使用 name 参数让图例自动关联曲线
            pdi = self.sweep_plot.plot(voltages, currents, pen=pen, symbol='o', symbolSize=6, symbolBrush=color, name=label, clear=False)
            # 保存曲线引用以便未来扩展（例如更新单条曲线）
            self.sweep_traces[label] = pdi

            # 标题显示通道信息，图例记录温度信息
            self.sweep_plot.setTitle(f"IV Sweep - {ch_name}")
        except Exception as e:
            print(f"[GUI] handle_new_sweep error: {e}")

    def update_running_status(self, is_running):
        self.run_status_lamp.setChecked(is_running)

    def highlight_running_block(self, running_index):
        """高亮当前正在执行的温度块。"""
        for i, block in enumerate(self.temp_blocks):
            is_currently_executing = (i == running_index)
            
            # 重新应用样式，确保状态正确
            block.check_edited(is_currently_executing=is_currently_executing)

    def set_ui_locked(self, is_running):
        # 运行/停止键状态更新
        self.run_stop_btn.setEnabled(True)
        self.run_stop_btn.setChecked(is_running)
        self._update_run_stop_button_style(is_running)
        # 界面静态组件
        for widget in self.lockable_widgets:
            widget.setEnabled(not is_running)
        # 禁用选项卡切换（仅禁用 tabBar，不会触发自动切换当前索引）
        try:
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                try:
                    self.tab_widget.tabBar().setEnabled(not is_running)
                except Exception:
                    # 回退：如果 tabBar 不可用，则保持原有行为不做任何处理
                    pass
        except Exception:
            pass

        # 温度块内的控件
        for block in getattr(self, 'temp_blocks', []):
            # 输入文本框
            for w in [block.start, block.stop, block.step, block.ramp]:
                w.setReadOnly(is_running)
            # 中止按钮
            block.end_checkbox.setEnabled(not is_running)
            # 删除按钮
            if hasattr(block, 'delete_btn'):
                block.delete_btn.setEnabled(not is_running)
        self.run_stop_btn.setStyleSheet("")

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
                ch_indices = {'CH1':2, 'CH2':3, 'CH3':4, 'CH4':5}
                for i, h in enumerate(header):
                    if h == 'Temperature[K]':
                        temp_idx = i
                    if h.startswith('Resistance_'):
                        ch_name = h.split('_')[1].split('[')[0]
                        ch_indices[ch_name] = i
                data_by_ch = {ch: {'x': [], 'y': []} for ch in ch_indices}
                print(ch_indices)
                for row in reader:
                    if len(row) < max(ch_indices.values())+1:
                        continue
                    try:
                        temp = float(row[temp_idx])
                        for ch, idx in ch_indices.items():
                            val = row[idx]
                            if val == '0.000000E0' or val.strip() == '':
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
        # 连接删除按钮：由主界面负责从布局和列表中移除控件
        if hasattr(block, 'delete_btn'):
            def _connect_delete(b):
                def on_delete():
                    # 在布局中查找并移除该块及其前置分隔线（如果有）
                    for i in range(self.temp_blocks_layout.count()):
                        item = self.temp_blocks_layout.itemAt(i)
                        w = item.widget() if item is not None else None
                        if w is b:
                            taken = self.temp_blocks_layout.takeAt(i)
                            if taken and taken.widget():
                                taken.widget().deleteLater()
                            # 如果前一个是分隔线则一并删除
                            if i-1 >= 0:
                                prev_item = self.temp_blocks_layout.itemAt(i-1)
                                if prev_item and prev_item.widget() and isinstance(prev_item.widget(), QFrame):
                                    prev_taken = self.temp_blocks_layout.takeAt(i-1)
                                    if prev_taken and prev_taken.widget():
                                        prev_taken.widget().deleteLater()
                            break
                    # 从内部列表移除
                    try:
                        self.temp_blocks.remove(b)
                    except ValueError:
                        pass
                    # 确保末尾只有一个 stretch
                    while self.temp_blocks_layout.count() and isinstance(self.temp_blocks_layout.itemAt(self.temp_blocks_layout.count()-1).widget(), type(None)):
                        self.temp_blocks_layout.takeAt(self.temp_blocks_layout.count()-1)
                    self.temp_blocks_layout.addStretch()
                    # 更新锁定状态确保界面一致
                    self.set_ui_locked(self.run_stop_btn.isChecked())
                return on_delete
            block.delete_btn.clicked.connect(_connect_delete(block))
        # 添加分隔线（除了第一个块）
        if len(self.temp_blocks) > 1:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("color: #d0d7de; background: #d0d7de; height: 0.5px; margin: 0;")
            layout.insertWidget(layout.count()-1, line)
        layout.addStretch()  # 重新添加stretch
        self.set_ui_locked(self.run_stop_btn.isChecked())
        return block

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
        self.set_ui_locked(self.run_stop_btn.isChecked())

    def load_sequence_blocks(self, sequence_data):
        """
        根据给定的温度块数据重建序列区域。
        Args:
            sequence_data (list[dict]): 包含 start/stop/step/ramp/end 的字典列表
        """
        layout = self.temp_blocks_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.temp_blocks.clear()

        if not sequence_data:
            self.add_temp_block()
        else:
            for data in sequence_data:
                block = self.add_temp_block()
                if not block:
                    continue
                block.start.setText(str(data.get('start', '')).strip())
                block.stop.setText(str(data.get('stop', '')).strip())
                block.step.setText(str(data.get('step', '')).strip())
                block.ramp.setText(str(data.get('ramp', '')).strip())
                block.end_checkbox.setChecked(bool(data.get('end', False)))
                block.check_edited()
        # 保证末尾有一个 stretch
        if layout.count() == 0 or not isinstance(layout.itemAt(layout.count()-1).widget(), type(None)):
            layout.addStretch()
        self.set_ui_locked(self.run_stop_btn.isChecked())

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

            # 更新 UI 显示 set temp 文本框（保留三位小数）
            self.set_temp_edit.setText(f"{temp:.3f}")

            # 委托 controller 处理（controller 将负责同时写 A 和 B）
            try:
                if hasattr(self, "controller") and hasattr(self.controller, "set_manual_temperature"):
                    self.controller.set_manual_temperature(temp, ramp)
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