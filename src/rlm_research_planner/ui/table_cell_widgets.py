from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton, QTableWidget, QWidget

from rlm_research_planner.ui.step_spin_box import (
    VisibleDoubleSpinBox,
    VisibleSpinBox,
)


TABLE_CELL_ROW_HEIGHT = 38

_TABLE_BUTTON_STYLE = """
QPushButton {
    min-height: 0px;
    padding: 1px 7px;
    margin: 3px;
    border-radius: 5px;
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
        widget.setStyleSheet(_TABLE_BUTTON_STYLE)
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


def set_table_cell_widget(
    table: QTableWidget,
    row: int,
    column: int,
    widget: QWidget,
) -> None:
    """Insert an editor/action without allowing it to overlap adjacent rows."""

    visual_style = str(table.window().property("visualStyle") or "desktop")
    configure_table_cell_widget(widget, visual_style=visual_style)
    table.verticalHeader().setMinimumSectionSize(TABLE_CELL_ROW_HEIGHT)
    table.setRowHeight(row, TABLE_CELL_ROW_HEIGHT)
    table.setCellWidget(row, column, widget)
