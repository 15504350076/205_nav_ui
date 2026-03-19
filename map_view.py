from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from platform_item import PlatformItem


class MapView(QGraphicsView):
    """中间态势图显示区。"""

    def __init__(self, on_platform_selected: Callable[[dict], None]) -> None:
        super().__init__()

        self.on_platform_selected = on_platform_selected
        self.platform_items: dict[str, PlatformItem] = {}
        self.selected_platform_id: str | None = None

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -300, 800, 600)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor(35, 35, 35))

    def drawBackground(self, painter: QPainter, rect) -> None:
        super().drawBackground(painter, rect)

        grid_pen = QPen(QColor(60, 60, 60), 1)
        axis_pen = QPen(QColor(120, 120, 120), 1.5)

        left = int(self.sceneRect().left())
        right = int(self.sceneRect().right())
        top = int(self.sceneRect().top())
        bottom = int(self.sceneRect().bottom())

        step = 50

        painter.setPen(grid_pen)
        for x in range(left, right + 1, step):
            painter.drawLine(x, top, x, bottom)

        for y in range(top, bottom + 1, step):
            painter.drawLine(left, y, right, y)

        painter.setPen(axis_pen)
        painter.drawLine(0, top, 0, bottom)
        painter.drawLine(left, 0, right, 0)

    def add_platform(self, platform_info: dict) -> None:
        item = PlatformItem(
            platform_id=platform_info["id"],
            platform_type=platform_info["type"],
            x=platform_info["x"],
            y=platform_info["y"],
            z=platform_info["z"],
            on_selected=self.select_platform,
        )
        self.platform_items[platform_info["id"]] = item
        self.scene.addItem(item)

    def update_platform(self, platform_info: dict) -> None:
        platform_id = platform_info["id"]
        if platform_id not in self.platform_items:
            self.add_platform(platform_info)
            return

        item = self.platform_items[platform_id]
        item.update_state(
            x=platform_info["x"],
            y=platform_info["y"],
            z=platform_info["z"],
        )

    def update_platforms(self, platform_list: list[dict]) -> None:
        for platform_info in platform_list:
            self.update_platform(platform_info)

    def select_platform(self, platform_info: dict) -> None:
        self.selected_platform_id = platform_info["id"]

        for pid, item in self.platform_items.items():
            item.set_selected(pid == self.selected_platform_id)

        self.on_platform_selected(platform_info)

    def wheelEvent(self, event) -> None:
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1 / zoom_factor, 1 / zoom_factor)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_R:
            self.resetTransform()
            event.accept()
            return
        super().keyPressEvent(event)