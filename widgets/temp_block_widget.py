# -*- coding: utf-8 -*-
"""
temp_block_widget.py: Defines the TempBlockWidget, a custom widget for a single temperature sequence block.
"""
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QCheckBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFocusEvent

class TempBlockWidget(QFrame):
    """
    温度序列中的单个温度设置块控件。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedHeight(30)
        self.setStyleSheet("QFrame { border: none; }") # 默认外框无边框

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        min_h = 20

        def create_label(text):
            label = QLabel(text)
            label.setFixedHeight(min_h)
            return label

        # 缺省值设置
        self.default_values = {
            'start': '300',
            'stop': '300', 
            'step': '1',
            'ramp': '4'
        }
        
        # 创建输入框并设置缺省值
        self.start = self._create_line_edit_with_default('start', 40)
        self.stop = self._create_line_edit_with_default('stop', 40)
        self.step = self._create_line_edit_with_default('step', 35)
        self.ramp = self._create_line_edit_with_default('ramp', 35)
        self.end_checkbox = QCheckBox(); self.end_checkbox.setFixedSize(min_h, min_h)
        self.end_checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
                border-radius: 6px;
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

        layout.addWidget(create_label("START"))
        layout.addWidget(self.start)
        layout.addWidget(create_label("STOP"))
        layout.addWidget(self.stop)
        layout.addWidget(create_label("STEP"))
        layout.addWidget(self.step)
        layout.addWidget(create_label("RAMP"))
        layout.addWidget(self.ramp)
        layout.addWidget(create_label("END"))
        layout.addWidget(self.end_checkbox, 0, Qt.AlignVCenter)
        self.setLayout(layout)
        for w in [self.start, self.stop, self.step, self.ramp]:
            w.textChanged.connect(lambda: self.check_edited())
        self.end_checkbox.stateChanged.connect(lambda: self.check_edited())
        self.check_edited() # 初始化样式
    
    def _create_line_edit_with_default(self, field_name, width):
        """创建带缺省值的输入框"""
        line_edit = QLineEdit()
        line_edit.setFixedWidth(width)
        line_edit.setFixedHeight(20)
        
        # 设置缺省值
        default_value = self.default_values[field_name]
        line_edit.setText(default_value)
        line_edit.setStyleSheet("QLineEdit { color: #999; }")  # 灰色缺省值
        
        # 连接焦点事件
        line_edit.focusInEvent = lambda event: self._on_focus_in(line_edit, event)
        line_edit.focusOutEvent = lambda event: self._on_focus_out(line_edit, event)
        
        return line_edit
    
    def _on_focus_in(self, line_edit, event):
        """获得焦点时，如果是缺省值则选中全部文本"""
        if line_edit.text() in self.default_values.values():
            line_edit.selectAll()
        line_edit.setStyleSheet("QLineEdit { color: #000; }")  # 黑色用户输入
        QLineEdit.focusInEvent(line_edit, event)
    
    def _on_focus_out(self, line_edit, event):
        """失去焦点时，如果为空则恢复缺省值"""
        if not line_edit.text().strip():
            # 找到对应的缺省值
            for field, default in self.default_values.items():
                if getattr(self, field) == line_edit:
                    line_edit.setText(default)
                    line_edit.setStyleSheet("QLineEdit { color: #999; }")  # 灰色缺省值
                    break
        QLineEdit.focusOutEvent(line_edit, event)

    def check_edited(self, is_currently_executing=False):
        """
        根据编辑状态和是否正在执行来更新背景颜色。
        - 未编辑: 透明
        - 已编辑: 浅绿色
        - 正在执行: 浅红色
        """
        # 检查是否有非缺省值的输入
        is_edited = all(
            w.text().strip() and w.text() not in self.default_values.values() 
            for w in [self.start, self.stop, self.step, self.ramp]
        )
        
        executing_color = "#ffdddd"   # 浅红色 (运行状态下正在执行)
        edited_color = "#e6ffed"     # 浅绿色 (已编辑 或 运行中但非当前)
        default_color = "transparent" # 透明 (未编辑)

        frame_color = default_color
        if is_edited:
            if is_currently_executing:
                frame_color = executing_color
            else:
                frame_color = edited_color

        lineedit_style = "QLineEdit { background-color: #fff; border: 1px solid #a0a0a0; border-radius: 0; padding: 3px; }"
        frame_style = f"QFrame {{ background-color: {frame_color}; }}"
            
        self.setStyleSheet(frame_style + " " + lineedit_style) 