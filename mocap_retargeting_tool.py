'''
Name: mocap_retargeting_tool

Description: Transfer animation data between rigs or transfer raw mocap from a skeleton to a custom rig.

Original tool: Animation Retargeting Tool by Joar Engberg (MIT License)
https://github.com/joaen/animation-retargeting-tool

Modified by: AJOY

Installation:
Add mocap_retargeting_tool.py to your Maya scripts folder (Username\\Documents\\maya\\scripts).
To start the tool within Maya, run these lines of code from the Maya script editor or add them to a shelf button:

import mocap_retargeting_tool
mocap_retargeting_tool.start()

'''
from collections import OrderedDict
import os
import sys
import maya.mel
import maya.cmds as cmds
from functools import partial
import maya.OpenMayaUI as omui
import time
import re

maya_version = int(cmds.about(version=True))

if maya_version < 2025:
    from shiboken2 import wrapInstance
    from PySide2 import QtCore, QtGui, QtWidgets
else:
    from shiboken6 import wrapInstance
    from PySide6 import QtCore, QtGui, QtWidgets


def maya_main_window():
    # Return the Maya main window as QMainWindow
    main_window = omui.MQtUtil.mainWindow()
    if sys.version_info.major >= 3:
        return wrapInstance(int(main_window), QtWidgets.QWidget)
    else:
        return wrapInstance(long(main_window), QtWidgets.QWidget) # type: ignore


class CollapsibleSection(QtWidgets.QWidget):
    '''
    A small collapsible panel: a clickable header (with an arrow) that
    shows/hides a content area. Used to group related controls the way
    "Naming & Location" / "Log" sections behave in the reference UI.
    '''
    def __init__(self, title, expanded=True, parent=None):
        super(CollapsibleSection, self).__init__(parent)

        self.toggle_button = QtWidgets.QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.toggle_button.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #d0d0d0;
                font-weight: 600;
                font-size: 11px;
                padding: 6px 2px;
                text-align: left;
            }
            QToolButton:hover {
                color: #ffffff;
            }
        """)
        self.toggle_button.clicked.connect(self.on_toggle)

        self.content_area = QtWidgets.QWidget()
        self.content_area.setVisible(expanded)
        self.content_area.setStyleSheet("""
            QWidget {
                background: #1b1b1b;
                border: 1px solid #333333;
                border-radius: 10px;
            }
        """)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(2)
        outer_layout.addWidget(self.toggle_button)
        outer_layout.addWidget(self.content_area)

    def set_content_layout(self, content_layout):
        content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_area.setLayout(content_layout)

    def on_toggle(self):
        expanded = self.toggle_button.isChecked()
        self.content_area.setVisible(expanded)
        self.toggle_button.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)


class MocapRetargetingTool(QtWidgets.QDialog):
    '''
    Main retargeting tool window.
    '''
    WINDOW_TITLE = "Mocap Retargeting Tool"

    def __init__(self):
        super(MocapRetargetingTool, self).__init__(maya_main_window())

        self.script_job_ids = []
        self.connection_ui_widgets = []
        self.color_counter = 0
        self.maya_color_index = OrderedDict([(13, "red"), (18, "cyan"), (14, "lime"), (17, "yellow")])
        self.cached_connect_nodes = []
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowFlags(
            (self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
            | QtCore.Qt.WindowMinimizeButtonHint
        )
        self.resize(460, 560)
        self.setup_ui_styling()
        self.create_ui_widgets()
        self.create_ui_layout()
        self.create_ui_connections()
        self.create_script_jobs()

        if cmds.about(macOS=True):
            self.setWindowFlags(QtCore.Qt.Tool)

    def setup_ui_styling(self):
        """Dark, rounded-corner UI styling."""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1c1c1c, stop:1 #101010);
                border: 1px solid #2f2f2f;
                border-radius: 10px;
                font-family: 'Segoe UI', Arial, sans-serif;
                color: #e6e6e6;
            }

            QLabel {
                color: #bdbdbd;
                font-size: 11px;
            }

            QPushButton {
                background: #262626;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                font-weight: 600;
                font-size: 10px;
                padding: 7px 14px;
                min-height: 20px;
            }

            QPushButton:hover {
                background: #333333;
                border: 1px solid #4a4a4a;
                color: #ffffff;
            }

            QPushButton:pressed {
                background: #1a1a1a;
                border: 1px solid #2a2a2a;
            }

            QCheckBox {
                color: #cccccc;
                font-weight: 600;
                font-size: 10px;
                spacing: 6px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #3a3a3a;
                border-radius: 4px;
                background: #1a1a1a;
            }

            QCheckBox::indicator:checked {
                background: #546e7a;
                border: 2px solid #546e7a;
            }

            QCheckBox::indicator:hover {
                border: 2px solid #607d8b;
            }

            QComboBox {
                background: #202020;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                font-weight: 600;
                padding: 5px 8px;
                min-height: 20px;
            }

            QComboBox:hover {
                background: #2a2a2a;
                border: 1px solid #4a4a4a;
            }

            QComboBox::drop-down {
                border: none;
                width: 20px;
            }

            QLineEdit {
                background: #202020;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                padding: 5px 8px;
            }

            QLineEdit:hover, QLineEdit:focus {
                border: 1px solid #546e7a;
            }

            QPlainTextEdit {
                background: #141414;
                border: none;
                color: #9fd19f;
                font-family: Consolas, monospace;
                font-size: 9px;
            }

            QScrollArea {
                background: transparent;
                border: 1px solid #2f2f2f;
                border-radius: 10px;
            }
        """)

    def create_ui_widgets(self):
        # Header
        self.title_label = QtWidgets.QLabel("MOCAP RETARGETING TOOL")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 700;
                color: #ffffff;
                background: transparent;
                border: none;
            }
        """)

        self.subtitle_label = QtWidgets.QLabel(
            "Transfer animation between rigs, or apply raw mocap to a custom rig."
        )
        self.subtitle_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #8a8a8a;
                background: transparent;
                border: none;
            }
        """)
        self.subtitle_label.setWordWrap(True)

        # Main action buttons
        self.simple_conn_button = QtWidgets.QPushButton("Create Connection")
        self.simple_conn_button.setStyleSheet(self.get_action_button_style("#546e7a"))

        self.ik_conn_button = QtWidgets.QPushButton("Create IK Connection")
        self.ik_conn_button.setStyleSheet(self.get_action_button_style("#546e7a"))

        self.bake_button = QtWidgets.QPushButton("Bake Animation")
        self.bake_button.setStyleSheet(self.get_action_button_style("#546e7a"))

        self.batch_bake_button = QtWidgets.QPushButton("Batch Bake && Export")
        self.batch_bake_button.setStyleSheet(self.get_action_button_style("#546e7a"))

        # Checkboxes
        self.rot_checkbox = QtWidgets.QCheckBox("Rotation")
        self.pos_checkbox = QtWidgets.QCheckBox("Translation")
        self.snap_checkbox = QtWidgets.QCheckBox("Align To Position")

        # Status + log
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { color: #7a7a7a; font-size: 9px; background: transparent; border: none; }")

        self.log_text_edit = QtWidgets.QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setFixedHeight(90)

        # Footer credit
        self.footer_label = QtWidgets.QLabel("Original: Joar Engberg  ·  Modified by: AJOY")
        self.footer_label.setStyleSheet("QLabel { color: #5a5a5a; font-size: 9px; background: transparent; border: none; }")

        # ============================================================
        # AJOY EXTENSIONS — added on top of Joar Engberg's original
        # tool. Not part of the original Animation Retargeting Tool.
        # ============================================================
        self.search_line_edit = QtWidgets.QLineEdit()
        self.search_line_edit.setPlaceholderText("Search connections...")

        self.joint_suffix_line = QtWidgets.QLineEdit("_JNT")
        self.joint_suffix_line.setFixedWidth(64)
        self.ctrl_suffix_line = QtWidgets.QLineEdit("_CTRL")
        self.ctrl_suffix_line.setFixedWidth(64)

        self.auto_connect_button = QtWidgets.QPushButton("Auto-Connect By Name")
        self.auto_connect_button.setStyleSheet(self.get_action_button_style("#546e7a"))
        self.auto_connect_button.setToolTip(
            "Batch-connects every joint ending in the joint suffix to a controller\n"
            "with the same base name ending in the controller suffix, e.g.\n"
            "'Arm_JNT' -> 'Arm_CTRL'. Uses the current Rotation/Translation/Align\n"
            "settings above."
        )

        self.mirror_button = QtWidgets.QPushButton("Mirror Connections (L \u2194 R)")
        self.mirror_button.setStyleSheet(self.get_action_button_style("#546e7a"))
        self.mirror_button.setToolTip(
            "Duplicates every existing connection onto the opposite side of the\n"
            "rig, matching common L/R naming patterns (_L_/_R_, Left/Right, etc).\n"
            "FK connections only; IK connections are skipped."
        )
        # ============================================================

    def get_action_button_style(self, color):
        """Rounded, flat action button style in the given accent color."""
        return f"""
            QPushButton {{
                background: {color};
                border: 1px solid {self.darken_color(color)};
                border-radius: 8px;
                color: #ffffff;
                font-weight: 600;
                font-size: 10px;
                padding: 8px 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background: {self.lighten_color(color)};
                border: 1px solid {color};
            }}
            QPushButton:pressed {{
                background: {self.darken_color(color)};
            }}
        """

    def lighten_color(self, color, factor=0.2):
        """Lighten a hex color (lookup table, matches the tool's accent palette)."""
        color_map = {
            "#546e7a": "#607d8b",
        }
        return color_map.get(color, color)

    def darken_color(self, color, factor=0.2):
        """Darken a hex color (lookup table, matches the tool's accent palette)."""
        color_map = {
            "#546e7a": "#455a64",
        }
        return color_map.get(color, color)

    def create_ui_layout(self):
        # Header
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(2)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)

        # Connection list
        connection_list_widget = QtWidgets.QWidget()
        self.connection_layout = QtWidgets.QVBoxLayout(connection_list_widget)
        self.connection_layout.setContentsMargins(6, 6, 6, 6)
        self.connection_layout.setSpacing(4)
        self.connection_layout.setAlignment(QtCore.Qt.AlignTop)

        list_scroll_area = QtWidgets.QScrollArea()
        list_scroll_area.setWidgetResizable(True)
        list_scroll_area.setWidget(connection_list_widget)
        list_scroll_area.setMinimumHeight(130)

        # Connection Setup section (options + creation buttons)
        setup_section = CollapsibleSection("▾  Connection Setup", expanded=True)
        setup_layout = QtWidgets.QVBoxLayout()
        setup_layout.setSpacing(8)

        options_row = QtWidgets.QHBoxLayout()
        options_row.addWidget(self.pos_checkbox)
        options_row.addWidget(self.rot_checkbox)
        options_row.addWidget(self.snap_checkbox)
        options_row.addStretch()

        buttons_row = QtWidgets.QHBoxLayout()
        buttons_row.addWidget(self.simple_conn_button)
        buttons_row.addWidget(self.ik_conn_button)
        buttons_row.setSpacing(8)

        setup_layout.addLayout(options_row)
        setup_layout.addLayout(buttons_row)
        setup_section.set_content_layout(setup_layout)

        # AJOY Extensions section — added on top of Joar Engberg's original tool
        extensions_section = CollapsibleSection("\u25b8  AJOY Extensions", expanded=False)
        extensions_layout = QtWidgets.QVBoxLayout()
        extensions_layout.setSpacing(8)

        auto_connect_row = QtWidgets.QHBoxLayout()
        auto_connect_row.addWidget(QtWidgets.QLabel("Joint suffix:"))
        auto_connect_row.addWidget(self.joint_suffix_line)
        auto_connect_row.addWidget(QtWidgets.QLabel("\u2192 Ctrl suffix:"))
        auto_connect_row.addWidget(self.ctrl_suffix_line)
        auto_connect_row.addStretch()

        extensions_layout.addLayout(auto_connect_row)
        extensions_layout.addWidget(self.auto_connect_button)
        extensions_layout.addWidget(self.mirror_button)
        extensions_section.set_content_layout(extensions_layout)

        # Log section
        log_section = CollapsibleSection("▸  Log", expanded=False)
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.addWidget(self.log_text_edit)
        log_section.set_content_layout(log_layout)

        # Action buttons
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.addWidget(self.batch_bake_button)
        action_layout.addWidget(self.bake_button)
        action_layout.setSpacing(8)

        # Footer
        footer_layout = QtWidgets.QHBoxLayout()
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.footer_label)

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 12)
        main_layout.setSpacing(10)
        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.search_line_edit)  # AJOY: connection search/filter
        main_layout.addWidget(list_scroll_area)
        main_layout.addWidget(setup_section)
        main_layout.addWidget(extensions_section)  # AJOY: mirror + auto-connect
        main_layout.addLayout(action_layout)
        main_layout.addWidget(log_section)
        main_layout.addLayout(footer_layout)

    def create_ui_connections(self):
        self.simple_conn_button.clicked.connect(self.create_connection_node)
        self.ik_conn_button.clicked.connect(self.create_ik_connection_node)
        self.bake_button.clicked.connect(self.bake_animation_confirm)
        self.batch_bake_button.clicked.connect(self.open_batch_window)

        self.rot_checkbox.setChecked(True)
        self.pos_checkbox.setChecked(True)
        self.snap_checkbox.setChecked(True)

        # AJOY Extensions wiring
        self.search_line_edit.textChanged.connect(self.filter_connection_list)
        self.auto_connect_button.clicked.connect(self.auto_connect_by_pattern)
        self.mirror_button.clicked.connect(self.mirror_connections)

    def log(self, message):
        """Append a timestamped line to the Log panel and update the status label."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text_edit.appendPlainText("[{}] {}".format(timestamp, message))
        self.status_label.setText(message)

    def create_script_jobs(self):
        self.script_job_ids.append(cmds.scriptJob(event=["SelectionChanged", partial(self.refresh_ui_list)]))
        self.script_job_ids.append(cmds.scriptJob(event=["NameChanged", partial(self.refresh_ui_list)]))

    def kill_script_jobs(self):
        for id in self.script_job_ids:
            if cmds.scriptJob(exists=id):
                cmds.scriptJob(kill=id)
            else:
                pass

    def refresh_ui_list(self):
        self.clear_list()

        connect_nodes_in_scene = MocapRetargetingTool.get_connect_nodes()
        self.cached_connect_nodes = connect_nodes_in_scene
        for node in connect_nodes_in_scene:
            connection_ui_item = ListItemWidget(parent_instance=self, connection_node=node)
            self.connection_layout.addWidget(connection_ui_item)
            self.connection_ui_widgets.append(connection_ui_item)

        self.filter_connection_list(self.search_line_edit.text())  # AJOY: keep active search applied

    def clear_list(self):
        self.connection_ui_widgets = []

        while self.connection_layout.count() > 0:
            connection_ui_item = self.connection_layout.takeAt(0)
            if connection_ui_item.widget():
                connection_ui_item.widget().deleteLater()

    def showEvent(self, event):
        self.refresh_ui_list()

    def closeEvent(self, event):
        self.kill_script_jobs()
        self.clear_list()

    def create_connection_node(self):
        try:
            selected_joint = cmds.ls(selection=True)[0]
            selected_ctrl = cmds.ls(selection=True)[1]
        except:
            return cmds.warning("No selections!")

        if self.snap_checkbox.isChecked() == True:
            cmds.matchTransform(selected_ctrl, selected_joint, pos=True)
        else:
            pass

        if self.rot_checkbox.isChecked() == True and self.pos_checkbox.isChecked() == False:
            suffix = "_ROT"

        elif self.pos_checkbox.isChecked() == True and self.rot_checkbox.isChecked() == False:
            suffix = "_TRAN"

        else:
            suffix = "_TRAN_ROT"

        locator = self.create_ctrl_sphere(selected_joint+suffix)

        # Add message attr
        cmds.addAttr(locator, longName="ConnectNode", attributeType="message")
        cmds.addAttr(selected_ctrl, longName="ConnectedCtrl", attributeType="message")
        cmds.connectAttr(locator+".ConnectNode",selected_ctrl+".ConnectedCtrl")

        cmds.parent(locator, selected_joint)
        cmds.xform(locator, rotation=(0, 0, 0))
        cmds.xform(locator, translation=(0, 0, 0))

        # Select the type of constraint based on the ui checkboxes
        if self.rot_checkbox.isChecked() == True and self.pos_checkbox.isChecked() == True:
            cmds.parentConstraint(locator, selected_ctrl, maintainOffset=True)

        elif self.rot_checkbox.isChecked() == True and self.pos_checkbox.isChecked() == False:
            cmds.orientConstraint(locator, selected_ctrl, maintainOffset=True)

        elif self.pos_checkbox.isChecked() == True and self.rot_checkbox.isChecked() == False:
            cmds.pointConstraint(locator, selected_ctrl, maintainOffset=True)
        else:
            cmds.warning("Select translation and/or rotation!")
            cmds.delete(locator)
            cmds.deleteAttr(selected_ctrl, at="ConnectedCtrl")
            return

        self.log("Connected {} -> {}".format(selected_joint, selected_ctrl))
        self.refresh_ui_list()

    def create_ik_connection_node(self):
        try:
            selected_joint = cmds.ls(selection=True)[0]
            selected_ctrl = cmds.ls(selection=True)[1]
        except:
            return cmds.warning("No selections!")

        self.rot_checkbox.setChecked(True)
        self.pos_checkbox.setChecked(True)

        if self.snap_checkbox.isChecked() == True:
            cmds.matchTransform(selected_ctrl, selected_joint, pos=True)
        else:
            pass

        tran_locator = self.create_ctrl_sphere(selected_joint+"_TRAN")

        cmds.parent(tran_locator, selected_joint)
        cmds.xform(tran_locator, rotation=(0, 0, 0))
        cmds.xform(tran_locator, translation=(0, 0, 0))

        rot_locator = self.create_ctrl_locator(selected_joint+"_ROT")

        # Add message attributes and connect them
        cmds.addAttr(tran_locator, longName="ConnectNode", attributeType="message")
        cmds.addAttr(rot_locator, longName="ConnectNode", attributeType="message")
        cmds.addAttr(selected_ctrl, longName="ConnectedCtrl", attributeType="message")
        cmds.connectAttr(tran_locator+".ConnectNode",selected_ctrl+".ConnectedCtrl")

        cmds.parent(rot_locator, tran_locator)
        cmds.xform(rot_locator, rotation=(0, 0, 0))
        cmds.xform(rot_locator, translation=(0, 0, 0))

        joint_parent = cmds.listRelatives(selected_joint, parent=True)[0]
        cmds.parent(tran_locator, joint_parent)
        cmds.makeIdentity(tran_locator, apply=True, translate=True)

        cmds.orientConstraint(selected_joint, tran_locator, maintainOffset=False)
        cmds.parentConstraint(rot_locator, selected_ctrl, maintainOffset=True)

        # Lock and hide attributes
        cmds.setAttr(rot_locator+".tx", lock=True, keyable=False)
        cmds.setAttr(rot_locator+".ty", lock=True, keyable=False)
        cmds.setAttr(rot_locator+".tz", lock=True, keyable=False)
        cmds.setAttr(tran_locator+".rx", lock=True, keyable=False)
        cmds.setAttr(tran_locator+".ry", lock=True, keyable=False)
        cmds.setAttr(tran_locator+".rz", lock=True, keyable=False)

        self.log("IK connected {} -> {}".format(selected_joint, selected_ctrl))
        self.refresh_ui_list()

    def scale_ctrl_shape(self, controller, size):
        cmds.select(self.get_cvs(controller), replace=True)
        cmds.scale(size, size, size)
        cmds.select(clear=True)

    def get_cvs(self, object):
        children = cmds.listRelatives(object, type="shape", children=True)
        ctrl_vertices = []
        for c in children:
            spans = int(cmds.getAttr(c+".spans")) + 1
            vertices = "{shape}.cv[0:{count}]".format(shape=c, count=spans)
            ctrl_vertices.append(vertices)
        return ctrl_vertices

    def create_ctrl_locator(self, ctrl_shape_name):
        curves = []
        curves.append(cmds.curve(degree=1, p=[(0, 0, 1), (0, 0, -1)], k=[0,1]))
        curves.append(cmds.curve(degree=1, p=[(1, 0, 0), (-1, 0, 0)], k=[0,1]))
        curves.append(cmds.curve(degree=1, p=[(0, 1, 0), (0, -1, 0)], k=[0,1]))

        locator = self.combine_shapes(curves, ctrl_shape_name)
        cmds.setAttr(locator+".overrideEnabled", 1)
        cmds.setAttr(locator+".overrideColor", list(self.maya_color_index.keys())[self.color_counter])
        return locator

    def create_ctrl_sphere(self, ctrl_shape_name):
        circles = []
        for n in range(0, 5):
            circles.append(cmds.circle(normal=(0,0,0), center=(0,0,0))[0])

        cmds.rotate(0, 45, 0, circles[0])
        cmds.rotate(0, -45, 0, circles[1])
        cmds.rotate(0, -90, 0, circles[2])
        cmds.rotate(90, 0, 0, circles[3])
        sphere = self.combine_shapes(circles, ctrl_shape_name)
        cmds.setAttr(sphere+".overrideEnabled", 1)
        cmds.setAttr(sphere+".overrideColor", list(self.maya_color_index.keys())[self.color_counter])
        self.scale_ctrl_shape(sphere, 0.5)
        return sphere

    def combine_shapes(self, shapes, ctrl_shape_name):
        shape_nodes = cmds.listRelatives(shapes, shapes=True)
        output_node = cmds.group(empty=True, name=ctrl_shape_name)
        cmds.makeIdentity(shapes, apply=True, translate=True, rotate=True, scale=True)
        cmds.parent(shape_nodes, output_node, shape=True, relative=True)
        cmds.delete(shape_nodes, constructionHistory=True)
        cmds.delete(shapes)
        return output_node

    def bake_animation_confirm(self):
        # AJOY: pre-bake validation pass
        connect_nodes = MocapRetargetingTool.get_connect_nodes()
        if not connect_nodes:
            cmds.warning("No connections found in scene!")
            return

        issues = self.validate_connections()
        if issues:
            issue_text = "\n".join(issues[:10])
            if len(issues) > 10:
                issue_text += "\n...and {} more issue(s)".format(len(issues) - 10)
            proceed = cmds.confirmDialog(
                title="Validation Issues Found",
                message="{} issue(s) found before baking:\n\n{}\n\nBake anyway?".format(len(issues), issue_text),
                button=["Bake Anyway", "Cancel"],
                defaultButton="Cancel",
                cancelButton="Cancel")
            if proceed != "Bake Anyway":
                self.log("Bake cancelled — {} validation issue(s) found".format(len(issues)))
                return

        confirm = cmds.confirmDialog(title="Confirm", message="Baking the animation will delete all the connection nodes. Do you wish to proceed?", button=["Yes","No"], defaultButton="Yes", cancelButton="No")
        if confirm == "Yes":
            progress_dialog = QtWidgets.QProgressDialog("Baking animation", None, 0, -1, self)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() ^ QtCore.Qt.WindowCloseButtonHint)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
            progress_dialog.setWindowTitle("Progress...")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            progress_dialog.show()
            QtCore.QCoreApplication.processEvents()
            # Bake animation
            self.bake_animation()
            progress_dialog.close()
            self.log("Animation baked and connection nodes removed")
        if confirm == "No":
            pass
        self.refresh_ui_list()

    def open_batch_window(self):
        try:
            self.settings_window.close()
            self.settings_window.deleteLater()
        except:
            pass
        self.settings_window = BatchExport()
        self.settings_window.show()

    @classmethod
    def bake_animation(cls):
        if len(cls.get_connected_ctrls()) == 0:
            cmds.warning("No connections found in scene!")
        if len(cls.get_connected_ctrls()) != 0:
            time_min = cmds.playbackOptions(query=True, min=True)
            time_max = cmds.playbackOptions(query=True, max=True)

            # Bake the animation
            cmds.refresh(suspend=True)
            cmds.bakeResults(cls.get_connected_ctrls(), t=(time_min, time_max), sb=1, at=["rx","ry","rz","tx","ty","tz"], hi="none")
            cmds.refresh(suspend=False)

            # Delete the connect nodes
            for node in cls.get_connect_nodes():
                try:
                    cmds.delete(node)
                except:
                    pass

            # Remove the message attribute from the controllers
            for ctrl in cls.get_connected_ctrls():
                try:
                    cmds.deleteAttr(ctrl, attribute="ConnectedCtrl")
                except:
                    pass

    @classmethod
    def get_connect_nodes(cls):
        connect_nodes_in_scene = []
        for i in cmds.ls():
            if cmds.attributeQuery("ConnectNode", node=i, exists=True) == True:
                connect_nodes_in_scene.append(i)
            else:
                pass
        return connect_nodes_in_scene

    @classmethod
    def get_connected_ctrls(cls):
        connected_ctrls_in_scene = []
        for i in cmds.ls():
            if cmds.attributeQuery("ConnectedCtrl", node=i, exists=True) == True:
                connected_ctrls_in_scene.append(i)
            else:
                pass
        return connected_ctrls_in_scene

    # ================================================================
    # AJOY EXTENSIONS
    # Everything below was added by AJOY on top of Joar Engberg's
    # original Animation Retargeting Tool (MIT License). It is not
    # part of the original tool.
    # https://github.com/joaen/animation-retargeting-tool
    # ================================================================

    # ---- UX polish: connection list search/filter ----

    def filter_connection_list(self, text):
        """Show only connection list items whose node name matches the search text."""
        query = text.strip().lower()
        for widget in self.connection_ui_widgets:
            widget.setVisible(query in widget.connection_node.lower())

    # ---- Validation/safety: pre-bake checks ----

    def validate_connections(self):
        """
        Check every connect node in the scene for problems that would
        cause a silent/partial bake: a missing parent joint, a broken
        link to its controller, or a controller that no longer exists.
        Returns a list of human-readable issue strings (empty if clean).
        """
        issues = []
        for node in MocapRetargetingTool.get_connect_nodes():
            if not cmds.objExists(node):
                issues.append("{}: node no longer exists".format(node))
                continue

            parent = cmds.listRelatives(node, parent=True)
            if not parent or not cmds.objExists(parent[0]):
                issues.append("{}: missing parent joint".format(node))

            connected = cmds.listConnections(node + ".ConnectNode", destination=True, plugs=True)
            if not connected:
                issues.append("{}: not linked to a controller".format(node))
                continue

            controller = connected[0].split(".")[0]
            if not cmds.objExists(controller):
                issues.append("{}: controller '{}' no longer exists".format(node, controller))

        return issues

    # ---- Workflow: auto-connect by naming pattern ----

    def auto_connect_by_pattern(self):
        """
        Batch-create connections by matching joints to controllers via a
        naming suffix, e.g. 'Arm_JNT' -> 'Arm_CTRL'. Uses whichever
        Rotation/Translation/Align settings are currently checked in the
        Connection Setup section. Skips joints that already have a
        connected controller.
        """
        joint_suffix = self.joint_suffix_line.text().strip()
        ctrl_suffix = self.ctrl_suffix_line.text().strip()

        if not joint_suffix or not ctrl_suffix:
            cmds.warning("Enter both a joint suffix and a controller suffix!")
            return

        already_connected = set()
        for node in MocapRetargetingTool.get_connect_nodes():
            connected = cmds.listConnections(node + ".ConnectNode", destination=True, plugs=True)
            if connected:
                already_connected.add(connected[0].split(".")[0])

        matched = 0
        skipped = 0

        for joint in cmds.ls(type="joint"):
            if not joint.endswith(joint_suffix):
                continue

            controller = joint[:-len(joint_suffix)] + ctrl_suffix

            if not cmds.objExists(controller):
                skipped += 1
                continue
            if controller in already_connected:
                continue

            cmds.select([joint, controller], replace=True)
            self.create_connection_node()
            matched += 1

        cmds.select(clear=True)
        self.log("Auto-connected {} pair(s), {} joint(s) had no matching controller".format(matched, skipped))

    # ---- Workflow: mirror connections L <-> R ----

    MIRROR_PATTERNS = [
        (r'(^|_)L(_|$)', r'\1R\2'),
        (r'(^|_)R(_|$)', r'\1L\2'),
        (r'(^|_)l(_|$)', r'\1r\2'),
        (r'(^|_)r(_|$)', r'\1l\2'),
        (r'Left', 'Right'),
        (r'Right', 'Left'),
    ]

    def mirror_name(self, name):
        """Return the opposite-side name for a common L/R naming convention, or None."""
        for pattern, repl in self.MIRROR_PATTERNS:
            mirrored = re.sub(pattern, repl, name, count=1)
            if mirrored != name:
                return mirrored
        return None

    def mirror_connections(self):
        """
        Duplicate every existing FK connection onto the opposite side of
        the rig by mirroring the joint and controller names. IK
        connections and center/unmirrorable names (e.g. spine, no L/R
        token) are safely skipped, not guessed at.
        """
        connect_nodes = MocapRetargetingTool.get_connect_nodes()
        if not connect_nodes:
            cmds.warning("No connections found to mirror!")
            return

        mirrored_count = 0
        skipped_count = 0

        prev_rot = self.rot_checkbox.isChecked()
        prev_pos = self.pos_checkbox.isChecked()

        for node in connect_nodes:
            parent = cmds.listRelatives(node, parent=True)
            if not parent:
                skipped_count += 1
                continue
            joint = parent[0]

            # Determine rotation/translation from the suffix, and filter
            # out IK connect nodes (their _TRAN locator is parented to the
            # joint's parent, not the joint itself) - IK mirroring isn't
            # supported yet, so skip those safely.
            if node.endswith("_TRAN_ROT"):
                rotation, translation = True, True
            elif node.endswith("_ROT"):
                rotation, translation = True, False
            elif node.endswith("_TRAN"):
                expected_joint = node[:-len("_TRAN")]
                if joint != expected_joint:
                    skipped_count += 1  # IK tran locator, not supported yet
                    continue
                rotation, translation = False, True
            else:
                skipped_count += 1
                continue

            connected = cmds.listConnections(node + ".ConnectNode", destination=True, plugs=True)
            if not connected:
                skipped_count += 1
                continue
            controller = connected[0].split(".")[0]

            mirrored_joint = self.mirror_name(joint)
            mirrored_ctrl = self.mirror_name(controller)

            if not mirrored_joint or not mirrored_ctrl:
                skipped_count += 1  # no L/R token found, e.g. a center joint
                continue
            if mirrored_joint == joint or mirrored_ctrl == controller:
                continue
            if not cmds.objExists(mirrored_joint) or not cmds.objExists(mirrored_ctrl):
                skipped_count += 1
                continue
            if cmds.attributeQuery("ConnectedCtrl", node=mirrored_ctrl, exists=True):
                continue  # already connected

            self.rot_checkbox.setChecked(rotation)
            self.pos_checkbox.setChecked(translation)

            cmds.select([mirrored_joint, mirrored_ctrl], replace=True)
            self.create_connection_node()
            mirrored_count += 1

        self.rot_checkbox.setChecked(prev_rot)
        self.pos_checkbox.setChecked(prev_pos)
        cmds.select(clear=True)
        self.log("Mirrored {} connection(s), skipped {} (IK/unmatched/already connected)".format(
            mirrored_count, skipped_count))


class ListItemWidget(QtWidgets.QWidget):
    '''
    UI list item class.
    When a new List Item is created it gets added to the connection_list_widget in the MocapRetargetingTool class.
    '''
    def __init__(self, connection_node, parent_instance):
        super(ListItemWidget, self).__init__()
        self.connection_node = connection_node
        self.main = parent_instance

        self.setFixedHeight(36)
        self.setup_item_styling()
        self.create_ui_widgets()
        self.create_ui_layout()
        self.create_ui_connections()

        # If there is already connection nodes in the scene update the color counter
        try:
            current_override = cmds.getAttr(self.connection_node+".overrideColor")
            self.main.color_counter = list(self.main.maya_color_index.keys()).index(current_override)
        except:
            pass

    def setup_item_styling(self):
        """Setup styling for list item widget"""
        self.setStyleSheet("""
            QWidget {
                background: #232323;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                margin: 2px;
            }

            QWidget:hover {
                background: #2a2a2a;
                border: 1px solid #546e7a;
            }
        """)

    def create_ui_widgets(self):
        self.color_button = QtWidgets.QPushButton()
        self.color_button.setFixedSize(22, 22)
        self.color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.get_current_color()};
                border: 1px solid #404040;
                border-radius: 11px;
            }}
            QPushButton:hover {{
                border: 1px solid #607d8b;
            }}
        """)

        self.sel_button = QtWidgets.QPushButton("Select")
        self.sel_button.setFixedWidth(70)
        self.sel_button.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 6px;
                color: #cccccc;
                font-weight: 600;
                font-size: 9px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: #383838;
                border: 1px solid #555555;
                color: #ffffff;
            }
        """)

        self.del_button = QtWidgets.QPushButton("Delete")
        self.del_button.setFixedWidth(70)
        self.del_button.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 6px;
                color: #cccccc;
                font-weight: 600;
                font-size: 9px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: #3a2323;
                border: 1px solid #e74c3c;
                color: #ffffff;
            }
        """)

        self.transform_name_label = QtWidgets.QLabel(self.connection_node)
        self.transform_name_label.setAlignment(QtCore.Qt.AlignCenter)
        self.transform_name_label.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-weight: 600;
                font-size: 10px;
                background: transparent;
                border: none;
                padding: 2px;
            }
        """)

        # Check if currently selected and update styling
        for selected in cmds.ls(selection=True):
            if selected == self.connection_node:
                self.transform_name_label.setStyleSheet("""
                    QLabel {
                        color: #ffffff;
                        font-weight: 700;
                        font-size: 10px;
                        background: transparent;
                        border: none;
                        padding: 2px;
                    }
                """)

    def create_ui_layout(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(6, 5, 10, 5)
        main_layout.addWidget(self.color_button)
        main_layout.addWidget(self.transform_name_label)
        main_layout.addWidget(self.sel_button)
        main_layout.addWidget(self.del_button)

    def create_ui_connections(self):
        self.sel_button.clicked.connect(self.select_connection_node)
        self.del_button.clicked.connect(self.delete_connection_node)
        self.color_button.clicked.connect(self.set_color)

    def select_connection_node(self):
        cmds.select(self.connection_node)
        for widget in self.main.connection_ui_widgets:
            widget.transform_name_label.setStyleSheet("""
                QLabel {
                    color: #cccccc;
                    font-weight: 600;
                    font-size: 10px;
                    background: transparent;
                    border: none;
                    padding: 2px;
                }
            """)
        self.transform_name_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: 700;
                font-size: 10px;
                background: transparent;
                border: none;
                padding: 2px;
            }
        """)

    def delete_connection_node(self):
        try:
            for attr in cmds.listConnections(self.connection_node, destination=True):
                if cmds.attributeQuery("ConnectedCtrl", node=attr, exists=True):
                    cmds.deleteAttr(attr, at="ConnectedCtrl")
        except:
            pass

        cmds.delete(self.connection_node)
        self.main.refresh_ui_list()

    def set_color(self):
        # Set the color on the connection node and button
        connection_nodes = self.main.cached_connect_nodes
        color = list(self.main.maya_color_index.keys())

        if self.main.color_counter < 3:
            self.main.color_counter += 1
        else:
            self.main.color_counter = 0

        for node in connection_nodes:
            cmds.setAttr(node+".overrideEnabled", 1)
            cmds.setAttr(node+".overrideColor", color[self.main.color_counter])

        for widget in self.main.connection_ui_widgets:
            widget.color_button.setStyleSheet("background-color:"+self.get_current_color()+"; border-radius: 11px;")

    def get_current_color(self):
        current_color_index = cmds.getAttr(self.connection_node+".overrideColor")
        color_name = self.main.maya_color_index.get(current_color_index, "grey")
        return color_name


class BatchExport(QtWidgets.QDialog):
    '''
    Batch exporter class
    '''
    WINDOW_TITLE = "Batch Bake & Export"

    def __init__(self):
        super(BatchExport, self).__init__(maya_main_window())
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowFlags(
            (self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
            | QtCore.Qt.WindowMinimizeButtonHint
        )
        self.resize(420, 260)
        self.animation_clip_paths = []
        self.output_folder = ""

        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1c1c1c, stop:1 #101010);
                border: 1px solid #2f2f2f;
                border-radius: 10px;
                color: #e6e6e6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #bdbdbd;
                font-size: 10px;
            }
            QLineEdit {
                background: #202020;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                padding: 4px 8px;
            }
            QListWidget {
                background: #161616;
                border: 1px solid #333333;
                border-radius: 10px;
                color: #d6d6d6;
            }
            QComboBox {
                background: #202020;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                padding: 4px 8px;
            }
            QPushButton {
                background: #262626;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                color: #d6d6d6;
                font-weight: 600;
                font-size: 10px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #333333;
                border: 1px solid #4a4a4a;
                color: #ffffff;
            }
        """)

        if cmds.about(macOS=True):
            self.setWindowFlags(QtCore.Qt.Tool)

        self.create_ui()
        self.create_connections()

    def create_ui(self):
        self.file_list_widget = QtWidgets.QListWidget()
        self.remove_selected_button = QtWidgets.QPushButton("Remove Selected")
        self.remove_selected_button.setFixedHeight(26)
        self.load_anim_button = QtWidgets.QPushButton("Load Animations")
        self.load_anim_button.setFixedHeight(26)
        self.export_button = QtWidgets.QPushButton("Batch Export Animations")
        self.export_button.setStyleSheet("""
            QPushButton {
                background: #546e7a;
                border: 1px solid #455a64;
                border-radius: 8px;
                color: #ffffff;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #607d8b;
            }
        """)
        self.connection_file_line = QtWidgets.QLineEdit()
        self.connection_file_line.setToolTip("Enter the file path to the connection rig file. A file which contains a rig with connections.")
        self.connection_filepath_button = QtWidgets.QPushButton()
        self.connection_filepath_button.setIcon(QtGui.QIcon(":fileOpen.png"))
        self.connection_filepath_button.setFixedSize(26, 26)

        self.export_selected_label = QtWidgets.QLabel("Export Selected (Optional):")
        self.export_selected_line = QtWidgets.QLineEdit()
        self.export_selected_line.setToolTip("Enter the name(s) of the nodes that should be exported. Leave blank to export all.")
        self.export_selected_button = QtWidgets.QPushButton()
        self.export_selected_button.setIcon(QtGui.QIcon(":addClip.png"))
        self.export_selected_button.setFixedSize(26, 26)

        self.output_filepath_button = QtWidgets.QPushButton()
        self.output_filepath_button.setIcon(QtGui.QIcon(":fileOpen.png"))

        self.file_type_combo = QtWidgets.QComboBox()
        self.file_type_combo.addItems([".fbx", ".ma"])

        horizontal_layout_1 = QtWidgets.QHBoxLayout()
        horizontal_layout_1.addWidget(QtWidgets.QLabel("Connection Rig File:"))
        horizontal_layout_1.addWidget(self.connection_file_line)
        horizontal_layout_1.addWidget(self.connection_filepath_button)

        horizontal_layout_2 = QtWidgets.QHBoxLayout()
        horizontal_layout_2.addWidget(self.load_anim_button)
        horizontal_layout_2.addWidget(self.remove_selected_button)

        horizontal_layout_3 = QtWidgets.QHBoxLayout()
        horizontal_layout_3.addWidget(QtWidgets.QLabel("Output File Type:"))
        horizontal_layout_3.addWidget(self.file_type_combo)
        horizontal_layout_3.addWidget(self.export_button)

        horizontal_layout_4 = QtWidgets.QHBoxLayout()
        horizontal_layout_4.addWidget(self.export_selected_label)
        horizontal_layout_4.addWidget(self.export_selected_line)
        horizontal_layout_4.addWidget(self.export_selected_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(8)
        main_layout.addWidget(self.file_list_widget)
        main_layout.addLayout(horizontal_layout_2)
        main_layout.addLayout(horizontal_layout_1)
        main_layout.addLayout(horizontal_layout_4)
        main_layout.addLayout(horizontal_layout_3)

    def create_connections(self):
        self.connection_filepath_button.clicked.connect(self.connection_filepath_dialog)
        self.load_anim_button.clicked.connect(self.animation_filepath_dialog)
        self.export_button.clicked.connect(self.batch_action)
        self.export_selected_button.clicked.connect(self.add_selected_action)
        self.remove_selected_button.clicked.connect(self.remove_selected_item)

    def connection_filepath_dialog(self):
        file_path = QtWidgets.QFileDialog.getOpenFileName(self, "Select Connection Rig File", "", "Maya ACSII (*.ma);;All files (*.*)")
        if file_path[0]:
            self.connection_file_line.setText(file_path[0])

    def output_filepath_dialog(self):
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select export folder path", "")
        if folder_path:
            self.output_folder = folder_path
            return True
        else:
            return False

    def animation_filepath_dialog(self):
        file_paths = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Animation Clips", "", "FBX (*.fbx);;All files (*.*)")
        file_path_list = file_paths[0]

        if file_path_list[0]:
            for i in file_path_list:
                self.file_list_widget.addItem(i)

        for i in range(0, self.file_list_widget.count()):
            self.file_list_widget.item(i).setTextColor(QtGui.QColor("white"))

    def add_selected_action(self):
        selection = cmds.ls(selection=True)
        if len(selection) > 1:
            text_string = "["
            for i in selection:
                text_string += '"{}", '.format(i)
            text_string = text_string[:-2]
            text_string += "]"
        elif selection[0]:
            text_string = "{}".format(selection[0])
        else:
            pass

        self.export_selected_line.setText(text_string)

    def remove_selected_item(self):
        try:
            selected_items = self.file_list_widget.selectedItems()
            for item in selected_items:
                self.file_list_widget.takeItem(self.file_list_widget.row(item))
        except:
            pass

    def batch_action(self):
        if self.connection_file_line.text() == "":
            cmds.warning("Connection file textfield is empty. Add a connection rig file to be able to export. This file should contain the rig and connections to a skeleton.")
        elif self.file_list_widget.count() == 0:
            cmds.warning("Animation clip list is empty. Add animation clips to the list to be able to export!")
        else:
            confirm_dialog = self.output_filepath_dialog()
            if confirm_dialog == True:
                self.bake_export()
            else:
                pass

    def bake_export(self):
        self.animation_clip_paths = []
        for i in range(self.file_list_widget.count()):
            self.animation_clip_paths.append(self.file_list_widget.item(i).text())

        number_of_operations = len(self.animation_clip_paths) * 3
        current_operation = 0
        progress_dialog = QtWidgets.QProgressDialog("Preparing", "Cancel", 0, number_of_operations, self)
        progress_dialog.setWindowFlags(progress_dialog.windowFlags() ^ QtCore.Qt.WindowCloseButtonHint)
        progress_dialog.setWindowFlags(progress_dialog.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        progress_dialog.setValue(0)
        progress_dialog.setWindowTitle("Progress...")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.show()
        QtCore.QCoreApplication.processEvents()
        export_result = []

        for i, path in enumerate(self.animation_clip_paths):
            # Import connection file and animation clip
            progress_dialog.setLabelText("Baking and exporting {} of {}".format(i + 1, len(self.animation_clip_paths)))
            self.file_list_widget.item(i).setTextColor(QtGui.QColor("yellow"))
            cmds.file(new=True, force=True)
            cmds.file(self.connection_file_line.text(), open=True)
            maya.mel.eval('FBXImportMode -v "exmerge";')
            maya.mel.eval('FBXImport -file "{}";'.format(path))
            current_operation += 1
            progress_dialog.setValue(current_operation)

            # Bake animation
            MocapRetargetingTool.bake_animation()
            current_operation += 1
            progress_dialog.setValue(current_operation)

            # Export animation
            output_path = self.output_folder + "/" + os.path.splitext(os.path.basename(path))[0]
            if self.file_type_combo.currentText() == ".fbx":
                output_path += ".fbx"
                cmds.file(rename=output_path)
                if self.export_selected_line.text() != "":
                    cmds.select(self.export_selected_line.text(), replace=True)
                    maya.mel.eval('FBXExport -f "{}" -s'.format(output_path))
                else:
                    maya.mel.eval('FBXExport -f "{}"'.format(output_path))
            elif self.file_type_combo.currentText() == ".ma":
                output_path += ".ma"
                cmds.file(rename=output_path)
                if self.export_selected_line.text() != "":
                    cmds.select(self.export_selected_line.text(), replace=True)
                    cmds.file(exportSelected=True, type="mayaAscii")
                else:
                    cmds.file(exportAll=True, type="mayaAscii")

            current_operation += 1
            progress_dialog.setValue(current_operation)

            if os.path.exists(output_path):
                self.file_list_widget.item(i).setTextColor(QtGui.QColor("lime"))
                export_result.append("Sucessfully exported: "+output_path)

            else:
                self.file_list_widget.item(i).setTextColor(QtGui.QColor("red"))
                export_result.append("Failed exporting: "+output_path)

        print("------")
        for i in export_result:
            print(i)
        print("------")

        progress_dialog.setValue(number_of_operations)
        progress_dialog.close()


def start():
    global retarget_tool_ui
    try:
        retarget_tool_ui.close()
        retarget_tool_ui.deleteLater()
    except:
        pass
    retarget_tool_ui = MocapRetargetingTool()
    retarget_tool_ui.show()

def start_dockable():
    """Start the tool as a dockable workspace control"""
    workspace_control_name = "MocapRetargetingToolWorkspaceControl"

    # Delete existing workspace control if it exists
    if cmds.workspaceControl(workspace_control_name, exists=True):
        cmds.deleteUI(workspace_control_name)

    # Create the workspace control
    workspace_control = cmds.workspaceControl(
        workspace_control_name,
        label="Mocap Retargeting Tool",
        tabToControl=("Outliner", -1),  # Dock next to Outliner
        initialWidth=460,
        initialHeight=560,
        widthProperty="preferred",
        heightProperty="preferred",
        retain=True,  # Keep it when Maya restarts
        floating=False,  # Start docked
        uiScript="mocap_retargeting_tool.create_workspace_control_ui()"
    )

    return workspace_control

def create_workspace_control_ui():
    """Create the UI for the workspace control"""
    global retarget_tool_ui

    try:
        retarget_tool_ui.close()
        retarget_tool_ui.deleteLater()
    except:
        pass

    # Create the tool UI
    retarget_tool_ui = MocapRetargetingTool()

    # Remove window flags to make it embeddable
    retarget_tool_ui.setWindowFlags(QtCore.Qt.Widget)

    return retarget_tool_ui

if __name__ == "__main__":
    start()
