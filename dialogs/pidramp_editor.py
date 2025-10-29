# -*- coding: utf-8 -*-
import os
import json
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
                             QLineEdit, QPushButton, QMessageBox, QScrollArea, QGroupBox, QGridLayout)
from PyQt5.QtCore import Qt


class PidRampEditorDialog(QDialog):
    """A structured editor for PIDRAMP: shows sections and editable fields instead of raw JSON.

    It displays top-level keys from PIDRAMP. For list-of-dict entries, each item is shown with
    editable fields. On Save & Load the dialog validates and writes back to config/PIDRAMP.json
    and calls model.load_pidramp(cfg_path).
    """
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("Edit PIDRAMP Configuration")
        self.resize(800, 600)
        self._widgets = {}  # mapping key -> list of item widgets or simple widget
        self._load_data()
        self._setup_ui()

    def _load_data(self):
        # Load initial data from model or file
        data = getattr(self.model, 'pidramp', None)
        if data is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(base_dir)
            cfg_path = os.path.join(base_dir, 'config', 'PIDRAMP.json')
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
        self._data = data or {}

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Scroll area for structured fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6,6,6,6)
        v.setSpacing(6)

        # For each top-level key in pidramp, render a section
        for key, value in self._data.items():
            grp = QGroupBox(key)
            g_layout = QVBoxLayout(grp)

            if isinstance(value, list):
                # list of entries; each entry may be dict
                self._widgets[key] = []
                for idx, item in enumerate(value):
                    # Do not show per-entry titles (e.g., '#1'); make entries compact
                    item_box = QWidget()
                    grid = QGridLayout(item_box)
                    grid.setContentsMargins(2, 2, 2, 2)
                    grid.setHorizontalSpacing(8)
                    grid.setVerticalSpacing(4)
                    # Render all fields in a single horizontal row: label+widget pairs across columns
                    if isinstance(item, dict):
                        # use friendly title internally but do not display it
                        field_widgets = {}
                        col = 0
                        for fname, fval in item.items():
                            lbl = QLabel(f"{fname}:")
                            # label width reduced to half (was 80)
                            lbl.setFixedWidth(40)
                            le = QLineEdit(str(fval))
                            le.setFixedWidth(60)
                            grid.addWidget(lbl, 0, col)
                            grid.addWidget(le, 0, col+1)
                            field_widgets[fname] = le
                            col += 2
                        self._widgets[key].append(field_widgets)
                    else:
                        # primitive list -> show as single line
                        le = QLineEdit(str(item))
                        le.setFixedWidth(100)
                        lbl = QLabel('value:')
                        lbl.setFixedWidth(40)
                        grid.addWidget(lbl, 0, 0)
                        grid.addWidget(le, 0, 1)
                        self._widgets[key].append({'_value': le})
                    g_layout.addWidget(item_box)
            elif isinstance(value, dict):
                # single dict -> show fields
                field_widgets = {}
                grid = QGridLayout()
                row = 0
                for fname, fval in value.items():
                    lbl = QLabel(f"{fname}:")
                    lbl.setFixedWidth(40)
                    grid.addWidget(lbl, row, 0)
                    le = QLineEdit(str(fval))
                    le.setFixedWidth(60)
                    grid.addWidget(le, row, 1)
                    field_widgets[fname] = le
                    row += 1
                g_layout.addLayout(grid)
                self._widgets[key] = field_widgets
            else:
                # primitive -> single QLineEdit
                le = QLineEdit(str(value))
                g_layout.addWidget(le)
                self._widgets[key] = {'_value': le}

            v.addWidget(grp)

        v.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.discard_btn = QPushButton('Discard')
        self.discard_btn.setStyleSheet('background-color: #95a5a6; color: white;')
        self.save_load_btn = QPushButton('Save & Load')
        self.save_load_btn.setStyleSheet('background-color: #2ecc71; color: white; font-weight: bold;')
        btn_row.addWidget(self.discard_btn)
        btn_row.addWidget(self.save_load_btn)
        layout.addLayout(btn_row)

        self.discard_btn.clicked.connect(self.reject)
        self.save_load_btn.clicked.connect(self._on_save_and_load)

    def _gather_data(self):
        # Reconstruct data structure from widget values
        out = {}
        for key, original in self._data.items():
            widgets = self._widgets.get(key)
            if isinstance(original, list):
                entries = []
                for w in widgets:
                    if '_value' in w:
                        txt = w['_value'].text()
                        entries.append(self._convert_text(txt))
                    else:
                        d = {}
                        for fname, le in w.items():
                            d[fname] = self._convert_text(le.text())
                        entries.append(d)
                out[key] = entries
            elif isinstance(original, dict):
                d = {}
                for fname, le in widgets.items():
                    d[fname] = self._convert_text(le.text())
                out[key] = d
            else:
                le = widgets.get('_value') if isinstance(widgets, dict) else None
                if le is not None:
                    out[key] = self._convert_text(le.text())
                else:
                    out[key] = original
        return out

    def _convert_text(self, txt):
        # try int, then float, else keep string
        txt = txt.strip()
        if txt == '':
            return txt
        for conv in (int, float):
            try:
                return conv(txt)
            except Exception:
                pass
        # boolean
        if txt.lower() in ('true', 'false'):
            return txt.lower() == 'true'
        return txt

    def _on_save_and_load(self):
        data = self._gather_data()
        # write to config path
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(base_dir)
            cfg_path = os.path.join(base_dir, 'config', 'PIDRAMP.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            # ask model to load
            if hasattr(self.model, 'load_pidramp'):
                try:
                    self.model.load_pidramp(cfg_path)
                except Exception as e:
                    QMessageBox.critical(self, 'Load Error', f'Saved but failed to load into model: {e}')
                    return

            QMessageBox.information(self, 'Saved', f'PIDRAMP saved and loaded from:\n{cfg_path}')
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', f'Failed to save PIDRAMP: {e}')
