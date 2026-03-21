"""平台图元模块：定义 UAV/UGV 图元及选中、灰显等样式行为。"""

from typing import Callable, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QPen, QColor
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsSimpleTextItem

from platform_state import PlatformState


def _fill_color(platform_type: str) -> QColor:
    if platform_type.upper() == "UAV":
        return QColor(80, 200, 255)
    return QColor(255, 170, 60)


def _stale_fill_color() -> QColor:
    return QColor(120, 120, 120)


def _outline_pen(selected: bool) -> QPen:
    if selected:
        return QPen(QColor(255, 255, 0), 2.5)
    return QPen(QColor(30, 30, 30), 1.2)


class PlatformItem(QGraphicsEllipseItem):
    """UAV 图元：圆形。"""

    NORMAL_RADIUS = 8.0
    SELECTED_RADIUS = 12.0

    def __init__(
        self,
        platform_id: str,
        platform_type: str,
        x: float,
        y: float,
        z: float,
        on_selected: Optional[Callable[[PlatformState], None]] = None,
    ) -> None:
        super().__init__()
        self.platform_id = platform_id
        self.platform_type = platform_type
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.on_selected = on_selected
        self.is_selected_flag = False
        self.is_stale_flag = False

        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

        self._setup_label()
        self._update_geometry()
        self._update_style()

    def _setup_label(self) -> None:
        self.label_item = QGraphicsSimpleTextItem(self.platform_id, self)
        self.label_item.setBrush(QBrush(QColor(230, 230, 230)))
        self.label_item.setPos(10, -22)

    def _update_geometry(self) -> None:
        radius = self.SELECTED_RADIUS if self.is_selected_flag else self.NORMAL_RADIUS
        self.setRect(QRectF(-radius, -radius, 2 * radius, 2 * radius))
        self.setPos(self.x_val, self.y_val)

    def _update_style(self) -> None:
        fill_color = _stale_fill_color() if self.is_stale_flag else _fill_color(self.platform_type)
        self.setBrush(QBrush(fill_color))
        self.setPen(_outline_pen(self.is_selected_flag))

    def set_selected(self, selected: bool) -> None:
        self.is_selected_flag = selected
        self._update_geometry()
        self._update_style()

    def set_label_visible(self, visible: bool) -> None:
        self.label_item.setVisible(visible)

    def set_stale(self, stale: bool) -> None:
        self.is_stale_flag = stale
        self._update_style()

    def update_state(self, x: float, y: float, z: float) -> None:
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.setPos(self.x_val, self.y_val)

    def get_info(self) -> PlatformState:
        return PlatformState(
            id=self.platform_id,
            type=self.platform_type,
            x=self.x_val,
            y=self.y_val,
            z=self.z_val,
        )

    def get_track_color(self) -> QColor:
        return _fill_color(self.platform_type)

    def mousePressEvent(self, event) -> None:
        if self.on_selected is not None:
            self.on_selected(self.get_info())
        super().mousePressEvent(event)


class UGVPlatformItem(QGraphicsRectItem):
    """UGV 图元：方形。"""

    NORMAL_HALF_SIZE = 8.0
    SELECTED_HALF_SIZE = 12.0

    def __init__(
        self,
        platform_id: str,
        platform_type: str,
        x: float,
        y: float,
        z: float,
        on_selected: Optional[Callable[[PlatformState], None]] = None,
    ) -> None:
        super().__init__()
        self.platform_id = platform_id
        self.platform_type = platform_type
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.on_selected = on_selected
        self.is_selected_flag = False
        self.is_stale_flag = False

        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

        self._setup_label()
        self._update_geometry()
        self._update_style()

    def _setup_label(self) -> None:
        self.label_item = QGraphicsSimpleTextItem(self.platform_id, self)
        self.label_item.setBrush(QBrush(QColor(230, 230, 230)))
        self.label_item.setPos(10, -22)

    def _update_geometry(self) -> None:
        half_size = self.SELECTED_HALF_SIZE if self.is_selected_flag else self.NORMAL_HALF_SIZE
        self.setRect(QRectF(-half_size, -half_size, 2 * half_size, 2 * half_size))
        self.setPos(self.x_val, self.y_val)

    def _update_style(self) -> None:
        fill_color = _stale_fill_color() if self.is_stale_flag else _fill_color(self.platform_type)
        self.setBrush(QBrush(fill_color))
        self.setPen(_outline_pen(self.is_selected_flag))

    def set_selected(self, selected: bool) -> None:
        self.is_selected_flag = selected
        self._update_geometry()
        self._update_style()

    def set_label_visible(self, visible: bool) -> None:
        self.label_item.setVisible(visible)

    def set_stale(self, stale: bool) -> None:
        self.is_stale_flag = stale
        self._update_style()

    def update_state(self, x: float, y: float, z: float) -> None:
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.setPos(self.x_val, self.y_val)

    def get_info(self) -> PlatformState:
        return PlatformState(
            id=self.platform_id,
            type=self.platform_type,
            x=self.x_val,
            y=self.y_val,
            z=self.z_val,
        )

    def get_track_color(self) -> QColor:
        return _fill_color(self.platform_type)

    def mousePressEvent(self, event) -> None:
        if self.on_selected is not None:
            self.on_selected(self.get_info())
        super().mousePressEvent(event)


def create_platform_item(
    platform_id: str,
    platform_type: str,
    x: float,
    y: float,
    z: float,
    on_selected: Optional[Callable[[PlatformState], None]] = None,
):
    if platform_type.upper() == "UGV":
        return UGVPlatformItem(
            platform_id=platform_id,
            platform_type=platform_type,
            x=x,
            y=y,
            z=z,
            on_selected=on_selected,
        )
    return PlatformItem(
        platform_id=platform_id,
        platform_type=platform_type,
        x=x,
        y=y,
        z=z,
        on_selected=on_selected,
    )
