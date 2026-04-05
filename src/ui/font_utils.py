from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QComboBox


def get_stable_ui_font(fallback_family: str = "Microsoft YaHei", fallback_point_size: int = 10) -> QFont:
    """返回一个带有效 point size 的 UI 字体副本。"""
    app = QApplication.instance()
    base_font = QFont(app.font()) if app is not None else QFont(fallback_family, fallback_point_size)

    family = base_font.family() or fallback_family
    point_size = base_font.pointSize()
    if point_size <= 0:
        point_size = fallback_point_size

    stable_font = QFont(family, point_size, base_font.weight(), base_font.italic())
    stable_font.setUnderline(base_font.underline())
    stable_font.setStrikeOut(base_font.strikeOut())
    stable_font.setKerning(base_font.kerning())
    return stable_font


def stabilize_combo_box_font(combo_box: QComboBox, fallback_family: str = "Microsoft YaHei", fallback_point_size: int = 10) -> None:
    """给 QComboBox 及其弹出视图应用稳定的 point-size 字体。"""
    stable_font = get_stable_ui_font(fallback_family, fallback_point_size)
    combo_box.setFont(stable_font)

    view = combo_box.view()
    if view is not None:
        view.setFont(stable_font)
