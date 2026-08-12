from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QToolButton


_BUTTON_BASE_STYLE = """
QToolButton {
    min-width: 0px;
    max-width: 16777215px;
    min-height: 0px;
    max-height: 16777215px;
    padding: 0;
    margin: 0;
    border-radius: 0;
    font-size: 16px;
    font-weight: 900;
}
QToolButton[stepEdge="decrease"] {
    border-top-left-radius: 5px;
    border-bottom-left-radius: 5px;
}
QToolButton[stepEdge="increase"] {
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}
"""

_DESKTOP_BUTTON_STYLE = """
QToolButton {
    border: 1px solid #9A9A9A;
    color: #202124;
    background-color: #F3F3F3;
}
QToolButton:hover {
    border-color: #2377B9;
    background-color: #E5F1FB;
}
QToolButton:pressed {
    border-color: #185A8D;
    background-color: #CCE4F7;
}
QToolButton:disabled {
    border-color: #C8C8C8;
    color: #8A8A8A;
    background-color: #ECECEC;
}
"""

_MOBILE_BUTTON_STYLE = """
QToolButton {
    border: 1px solid #3B7180;
    color: #F4F8F8;
    background-color: #15333E;
}
QToolButton:hover {
    border-color: #66D8C2;
    color: #07151D;
    background-color: #66D8C2;
}
QToolButton:pressed {
    border-color: #F2B632;
    color: #07151D;
    background-color: #F2B632;
}
QToolButton:disabled {
    border-color: #263F48;
    color: #78909A;
    background-color: #10242D;
}
"""


def set_step_button_visual_style(
    button: QToolButton, visual_style: str
) -> None:
    theme = (
        _MOBILE_BUTTON_STYLE
        if visual_style == "mobile"
        else _DESKTOP_BUTTON_STYLE
    )
    button.setStyleSheet(_BUTTON_BASE_STYLE + theme)


def update_step_button_visual_styles(widget, visual_style: str) -> None:
    for button in widget.findChildren(QToolButton):
        if bool(button.property("stepControl")):
            set_step_button_visual_style(button, visual_style)


def configure_step_button(
    button: QToolButton, *, decrease: bool, visual_style: str = "desktop"
) -> QToolButton:
    """Apply the shared, compact step-button appearance."""

    button.setText("−" if decrease else "+")
    button.setObjectName(
        "SpinDecreaseButton" if decrease else "SpinIncreaseButton"
    )
    button.setProperty("stepEdge", "decrease" if decrease else "increase")
    button.setProperty("stepControl", True)
    button.setAccessibleName(
        "Decrease value" if decrease else "Increase value"
    )
    button.setFocusPolicy(Qt.NoFocus)
    button.setAutoRepeat(True)
    set_step_button_visual_style(button, visual_style)
    return button


class _VisibleStepButtons:
    """Give spin boxes readable minus/plus buttons in every visual style."""

    _BUTTON_WIDTH = 24
    _MINIMUM_WIDTH = 104
    _TABLE_CELL_MARGIN_X = 3
    _TABLE_CELL_MARGIN_Y = 3

    def _install_step_buttons(self) -> None:
        self._table_cell_mode = False
        self.setButtonSymbols(self.ButtonSymbols.NoButtons)
        self.setMinimumWidth(self._MINIMUM_WIDTH)
        self._decrease_button = configure_step_button(
            QToolButton(self), decrease=True
        )
        self._increase_button = configure_step_button(
            QToolButton(self), decrease=False
        )
        self._decrease_button.clicked.connect(self.stepDown)
        self._increase_button.clicked.connect(self.stepUp)
        self.valueChanged.connect(self._update_step_buttons)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setAlignment(Qt.AlignCenter)
            line_edit.setTextMargins(
                self._BUTTON_WIDTH + 3, 0, self._BUTTON_WIDTH + 3, 0
            )
        self._layout_step_buttons()
        self._update_step_buttons()

    def _update_step_buttons(self, *_args) -> None:
        if not hasattr(self, "_decrease_button"):
            return
        value = self.value()
        self._decrease_button.setEnabled(self.isEnabled() and value > self.minimum())
        self._increase_button.setEnabled(self.isEnabled() and value < self.maximum())

    def setRange(self, minimum, maximum) -> None:
        super().setRange(minimum, maximum)
        self._update_step_buttons()

    def setMinimum(self, minimum) -> None:
        super().setMinimum(minimum)
        self._update_step_buttons()

    def setMaximum(self, maximum) -> None:
        super().setMaximum(maximum)
        self._update_step_buttons()

    def set_visual_style(self, visual_style: str) -> None:
        set_step_button_visual_style(self._decrease_button, visual_style)
        set_step_button_visual_style(self._increase_button, visual_style)

    def set_table_cell_mode(self, enabled: bool = True) -> None:
        """Inset the editor so repeated table rows do not form button columns."""

        self._table_cell_mode = bool(enabled)
        self.setProperty("tableCellEditor", self._table_cell_mode)
        self.setStyleSheet(
            "QSpinBox, QDoubleSpinBox {"
            " min-height: 0px; padding: 0px; margin: 3px;"
            "}"
            if self._table_cell_mode
            else ""
        )
        self._layout_step_buttons()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "_decrease_button"):
            return
        self._layout_step_buttons()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(max(self._MINIMUM_WIDTH, hint.width()), hint.height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(max(self._MINIMUM_WIDTH, hint.width()), hint.height())

    def _layout_step_buttons(self) -> None:
        horizontal_inset = (
            self._TABLE_CELL_MARGIN_X if self._table_cell_mode else 1
        )
        vertical_inset = (
            self._TABLE_CELL_MARGIN_Y if self._table_cell_mode else 1
        )
        button_width = min(
            self._BUTTON_WIDTH,
            max(0, (self.width() - (horizontal_inset * 2)) // 2),
        )
        button_height = max(0, self.height() - (vertical_inset * 2))
        self._decrease_button.setGeometry(
            horizontal_inset,
            vertical_inset,
            button_width,
            button_height,
        )
        self._increase_button.setGeometry(
            max(
                horizontal_inset,
                self.width() - button_width - horizontal_inset,
            ),
            vertical_inset,
            button_width,
            button_height,
        )
        self._decrease_button.raise_()
        self._increase_button.raise_()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        self._update_step_buttons()


class VisibleSpinBox(_VisibleStepButtons, QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._install_step_buttons()


class VisibleDoubleSpinBox(_VisibleStepButtons, QDoubleSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._install_step_buttons()
