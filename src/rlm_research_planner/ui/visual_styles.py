from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget


MOBILE_STYLE_SHEET = """
QMainWindow {
    color: #F4F8F8;
    background-color: #07151D;
}
QDialog, QMessageBox, QProgressDialog, QFileDialog {
    color: #F4F8F8;
    background-color: #0D2530;
}
QDialog QLabel, QMessageBox QLabel, QProgressDialog QLabel, QFileDialog QLabel {
    color: #F4F8F8;
    background-color: transparent;
}
QWidget {
    color: #F4F8F8;
}
QWidget#RlmRoot {
    color: #F4F8F8;
    background-color: #07151D;
    font-family: "Yu Gothic UI", "Noto Sans JP", sans-serif;
}
QLabel, QCheckBox {
    color: #F4F8F8;
    background-color: transparent;
}
QLabel:disabled, QCheckBox:disabled {
    color: #6F858B;
}
QTabWidget::pane {
    border: 1px solid #234650;
    border-radius: 10px;
    background-color: #0D2530;
    top: -1px;
}
QTabBar::tab {
    min-width: 88px;
    min-height: 30px;
    margin-right: 4px;
    padding: 6px 12px;
    border: 1px solid #2F5F6C;
    border-bottom: 0;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    color: #F4F8F8;
    background-color: #15333E;
}
QTabBar::tab:hover {
    border-color: #66D8C2;
}
QTabBar::tab:selected {
    border-color: #F2B632;
    color: #07151D;
    background-color: #F2B632;
    font-weight: 700;
}
QPushButton, QToolButton {
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid #2F5F6C;
    border-radius: 8px;
    color: #F4F8F8;
    background-color: #15333E;
}
QPushButton:hover, QToolButton:hover {
    border-color: #66D8C2;
    background-color: #1B414E;
}
QPushButton:pressed, QToolButton:pressed {
    border-color: #F2B632;
    color: #07151D;
    background-color: #F2B632;
}
QPushButton:disabled, QToolButton:disabled {
    color: #6F858B;
    border-color: #263F48;
    background-color: #10242D;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 28px;
    padding: 3px 7px;
    border: 1px solid #2F5F6C;
    border-radius: 7px;
    color: #F4F8F8;
    selection-color: #07151D;
    selection-background-color: #66D8C2;
    background-color: #081B24;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #66D8C2;
}
QComboBox::drop-down {
    width: 24px;
    border: 0;
}
QComboBox QAbstractItemView {
    color: #F4F8F8;
    selection-color: #07151D;
    selection-background-color: #F2B632;
    background-color: #0D2530;
    border: 1px solid #2F5F6C;
}
QListWidget, QTableWidget, QTextBrowser,
QFileDialog QListView, QFileDialog QTreeView {
    color: #F4F8F8;
    alternate-background-color: #102D38;
    background-color: #0B202A;
    border: 1px solid #2C5360;
    border-radius: 9px;
    gridline-color: #284B57;
}
QTableCornerButton::section {
    border: 0;
    border-right: 1px solid #2C5360;
    border-bottom: 1px solid #2C5360;
    background-color: #123542;
}
QTableWidget::item:selected, QListWidget::item:selected {
    color: #07151D;
    background-color: #F2B632;
}
QHeaderView::section {
    padding: 5px;
    border: 0;
    border-right: 1px solid #2C5360;
    border-bottom: 1px solid #2C5360;
    color: #DCEBED;
    background-color: #123542;
    font-weight: 700;
}
QGroupBox {
    margin-top: 12px;
    padding-top: 12px;
    border: 1px solid #2C5360;
    border-radius: 10px;
    color: #F4F8F8;
    background-color: #0D2530;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #66D8C2;
    background-color: #07151D;
}
QLabel#ConstructionSelection {
    min-height: 28px;
    padding: 4px 12px;
    border: 2px solid #C58BFF;
    border-radius: 8px;
    color: #F4E8FF;
    background-color: #2B183D;
    font-weight: 800;
}
QProgressBar {
    min-height: 12px;
    border: 1px solid #456773;
    border-radius: 6px;
    color: #F4F8F8;
    text-align: center;
    background-color: #061117;
}
QProgressBar::chunk {
    border-radius: 5px;
    background-color: #F2B632;
}
QScrollBar:vertical {
    width: 12px;
    margin: 0;
    border: 0;
    background-color: #081B24;
}
QScrollBar:horizontal {
    height: 12px;
    margin: 0;
    border: 0;
    background-color: #081B24;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    min-height: 24px;
    min-width: 24px;
    border-radius: 6px;
    background-color: #2F5F6C;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background-color: #66D8C2;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QSplitter::handle {
    background-color: #234650;
}
QToolTip {
    color: #F4F8F8;
    border: 1px solid #66D8C2;
    background-color: #0D303B;
}
QMenu {
    color: #F4F8F8;
    border: 1px solid #2F5F6C;
    background-color: #0D2530;
}
QMenu::item:selected {
    color: #07151D;
    background-color: #F2B632;
}
"""


DESKTOP_DATASET_STYLE = (
    "QListWidget::item { border: 2px solid transparent; }"
    "QListWidget::item:selected {"
    " background-color: #176B87; color: #FFFFFF;"
    " border: 2px solid #59C9F1; font-weight: 700;"
    "}"
    "QListWidget::item:selected:!active {"
    " background-color: #176B87; color: #FFFFFF;"
    " border: 2px solid #59C9F1;"
    "}"
)


MOBILE_DATASET_STYLE = (
    "QListWidget { color: #F4F8F8; background-color: #0B202A;"
    " border: 1px solid #2C5360; border-radius: 9px; }"
    "QListWidget::item { border: 2px solid transparent; border-radius: 7px; }"
    "QListWidget::item:hover { border-color: #66D8C2; }"
    "QListWidget::item:selected, QListWidget::item:selected:!active {"
    " background-color: #F2B632; color: #07151D;"
    " border: 2px solid #F2B632; font-weight: 700;"
    "}"
)


def window_style_sheet(visual_style: str) -> str:
    return MOBILE_STYLE_SHEET if visual_style == "mobile" else ""


def apply_window_visual_surface(
    window: QMainWindow, visual_style: str
) -> None:
    """Prepare the Qt surface before Windows creates the native window.

    RLMResearchPlanner uses the normal Windows frame, not a frameless window.
    Keep Qt's normal background fill enabled and set its palette before the
    first ``show()``. Disabling the system background here would leave the
    first client pixels unpainted, while translucent backgrounds are a
    frameless-window technique on Windows.
    """

    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    palette = QPalette(QApplication.palette())
    if visual_style == "mobile":
        palette.setColor(QPalette.ColorRole.Window, QColor("#07151D"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F4F8F8"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#081B24"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0D2530"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#F4F8F8"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#15333E"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F4F8F8"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#F2B632"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#07151D"))

    window.setPalette(palette)
    window.setStyleSheet(window_style_sheet(visual_style))
    # Setting a style sheet can disable autoFillBackground on the receiver.
    # Re-enable it afterwards so the normal decorated window always owns an
    # opaque first surface even before child widgets paint.
    window.setAutoFillBackground(True)
    central = window.centralWidget()
    if central is not None:
        central.setPalette(palette)
        central.setAutoFillBackground(True)


def apply_dialog_visual_style(dialog: QWidget, visual_style: str) -> None:
    """Apply the selected appearance directly to a top-level dialog.

    Top-level native dialogs do not reliably inherit a style sheet from their
    parent window on Windows.  Set both the palette and the style sheet on the
    dialog itself so its panel and child text always use the same theme.
    """
    dialog.setProperty("visualStyle", visual_style)
    if visual_style != "mobile":
        dialog.setStyleSheet("")
        dialog.setAutoFillBackground(False)
        return

    palette = dialog.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0D2530"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#F4F8F8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#081B24"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0D2530"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#F4F8F8"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#15333E"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F4F8F8"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#F2B632"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#07151D"))
    dialog.setPalette(palette)
    dialog.setAutoFillBackground(True)
    dialog.setStyleSheet(MOBILE_STYLE_SHEET)


def dataset_style_sheet(visual_style: str) -> str:
    return (
        MOBILE_DATASET_STYLE
        if visual_style == "mobile"
        else DESKTOP_DATASET_STYLE
    )


def table_link_color(visual_style: str) -> str:
    return "#8BD5FF" if visual_style == "mobile" else "#1565C0"
