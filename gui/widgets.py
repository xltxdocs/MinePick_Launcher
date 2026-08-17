"""共享小部件工具：去掉选中项文字的焦点矩形描边（1-2px 圆角框）。"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


class NoFocusDelegate(QStyledItemDelegate):
    """列表/表格委托：绘制时移除 HasFocus 状态，样式引擎不再画焦点矩形。"""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


def apply_no_focus_outline(view) -> None:
    """给 QListWidget / QTableWidget 等视图套用无焦点框委托。"""
    view.setItemDelegate(NoFocusDelegate(view))
