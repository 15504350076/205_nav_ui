from typing import Callable, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QPen, QColor
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsSimpleTextItem


class PlatformItem(QGraphicsEllipseItem):
    """界面中的单个平台亮点对象。"""

    NORMAL_RADIUS = 8.0
    SELECTED_RADIUS = 12.0

    def __init__(
        self,
        platform_id: str,
        platform_type: str,
        x: float,
        y: float,
        z: float,
        on_selected: Optional[Callable[[dict], None]] = None,
    ) -> None:
        super().__init__()
        self.platform_id = platform_id
        self.platform_type = platform_type
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.on_selected = on_selected
        self.is_selected_flag = False

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
        if self.platform_type.upper() == "UAV":
            fill_color = QColor(80, 200, 255)
        else:
            fill_color = QColor(255, 170, 60)

        if self.is_selected_flag:
            pen = QPen(QColor(255, 255, 0), 2.5)
        else:
            pen = QPen(QColor(30, 30, 30), 1.2)

        self.setBrush(QBrush(fill_color))
        self.setPen(pen)

    def set_selected(self, selected: bool) -> None:
        self.is_selected_flag = selected
        self._update_geometry()
        self._update_style()

    def update_state(self, x: float, y: float, z: float) -> None:
        self.x_val = x
        self.y_val = y
        self.z_val = z
        self.setPos(self.x_val, self.y_val)

    def get_info(self) -> dict:
        return {
            "id": self.platform_id,
            "type": self.platform_type,
            "x": self.x_val,
            "y": self.y_val,
            "z": self.z_val,
        }

    def get_track_color(self) -> QColor:
        if self.platform_type.upper() == "UAV":
            return QColor(80, 200, 255)
        return QColor(255, 170, 60)

    def mousePressEvent(self, event) -> None:
        if self.on_selected is not None:
            self.on_selected(self.get_info())
        super().mousePressEvent(event)