from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton, QTableWidget, QWidget

from rlm_research_planner.ui.step_spin_box import (
    VisibleDoubleSpinBox,
    VisibleSpinBox,
)


TABLE_CELL_ROW_HEIGHT = 38

_TABLE_BUTTON_BASE_STYLE = """
QPushButton {
    min-height: 0px;
    padding: 2px 9px;
    margin: 3px;
    border-radius: 5px;
    font-weight: 700;
}
"""

_TABLE_BUTTON_DESKTOP_STYLE = """
QPushButton {
    border: 1px solid #1769AA;
    color: #FFFFFF;
    background-color: #1976B9;
}
QPushButton:hover {
    border-color: #0D4F82;
    background-color: #125F99;
}
QPushButton:pressed {
    border-color: #08395F;
    background-color: #0B4B78;
}
QPushButton:disabled {
    border-color: #B7C1C8;
    color: #69757D;
    background-color: #E4E8EB;
}
"""

_TABLE_BUTTON_MOBILE_STYLE = """
QPushButton {
    border: 1px solid #F2B632;
    color: #07151D;
    background-color: #F2B632;
}
QPushButton:hover {
    border-color: #FFD86A;
    background-color: #FFD05A;
}
QPushButton:pressed {
    border-color: #C98B08;
    background-color: #D79A14;
}
QPushButton:disabled {
    border-color: #52616A;
    color: #78909A;
    background-color: #26343B;
}
"""

_TABLE_COMBO_STYLE = """
QComboBox {
    min-height: 0px;
    padding: 1px 24px 1px 6px;
    margin: 3px;
    border-radius: 5px;
}
"""


def _configure_table_child(widget: QWidget, visual_style: str) -> None:
    if isinstance(widget, (VisibleSpinBox, VisibleDoubleSpinBox)):
        widget.set_table_cell_mode()
        widget.set_visual_style(visual_style)
    elif isinstance(widget, QPushButton):
        widget.setProperty("tableCellAction", True)
        theme = (
            _TABLE_BUTTON_MOBILE_STYLE
            if visual_style == "mobile"
            else _TABLE_BUTTON_DESKTOP_STYLE
        )
        widget.setStyleSheet(_TABLE_BUTTON_BASE_STYLE + theme)
    elif isinstance(widget, QComboBox):
        widget.setProperty("tableCellSelector", True)
        widget.setStyleSheet(_TABLE_COMBO_STYLE)


def configure_table_cell_widget(
    widget: QWidget,
    *,
    visual_style: str = "desktop",
) -> QWidget:
    """Apply the same compact geometry to every widget embedded in a table."""

    widget.setProperty("tableCellWidget", True)
    _configure_table_child(widget, visual_style)
    for child in widget.findChildren(QWidget):
        _configure_table_child(child, visual_style)
    return widget


def update_table_cell_widget_visual_styles(
    widget: QWidget,
    visual_style: str,
) -> None:
    """Refresh table action colors after the application theme changes."""

    for child in widget.findChildren(QWidget):
        if bool(child.property("tableCellWidget")) or bool(
            child.property("tableCellAction")
        ):
            _configure_table_child(child, visual_style)


def set_table_cell_widget(
    table: QTableWidget,
    row: int,
    column: int,
    widget: QWidget,
) -> None:
    """Insert an editor/action without allowing it to overlap adjacent rows."""

    visual_style = str(table.window().property("visualStyle") or "desktop")
    widget.setFont(table.font())
    for child in widget.findChildren(QWidget):
        child.setFont(table.font())
    configure_table_cell_widget(widget, visual_style=visual_style)
    table.verticalHeader().setMinimumSectionSize(TABLE_CELL_ROW_HEIGHT)
    table.setRowHeight(row, TABLE_CELL_ROW_HEIGHT)
    table.setCellWidget(row, column, widget)
