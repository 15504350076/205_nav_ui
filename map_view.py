from typing import Callable

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene, QGraphicsView

from platform_item import PlatformItem


class MapView(QGraphicsView):
    """中间态势图显示区。"""

    def __init__(self, on_platform_selected: Callable[[dict], None]) -> None:
        super().__init__()

        self.on_platform_selected = on_platform_selected
        self.platform_items: dict[str, PlatformItem] = {}
        self.latest_platform_info: dict[str, dict] = {}
        self.track_items: dict[str, QGraphicsPathItem] = {}
        self.track_history: dict[str, list[QPointF]] = {}
        self.selected_platform_id: str | None = None
        self.show_tracks = True
        self.max_track_points = 120

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
        self.latest_platform_info[platform_info["id"]] = platform_info.copy()
        self.scene.addItem(item)

        track_item = QGraphicsPathItem()
        track_pen = QPen(item.get_track_color(), 1.8)
        track_item.setPen(track_pen)
        track_item.setZValue(-1)
        self.scene.addItem(track_item)

        self.track_items[platform_info["id"]] = track_item
        self.track_history[platform_info["id"]] = [
            QPointF(platform_info["x"], platform_info["y"])
        ]

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

        self.latest_platform_info[platform_id] = platform_info.copy()
        self._update_track(platform_id, platform_info["x"], platform_info["y"])

    def _update_track(self, platform_id: str, x: float, y: float) -> None:
        if platform_id not in self.track_history:
            self.track_history[platform_id] = []

        history = self.track_history[platform_id]
        history.append(QPointF(x, y))

        if len(history) > self.max_track_points:
            history.pop(0)

        track_item = self.track_items[platform_id]
        if not self.show_tracks or len(history) < 2:
            track_item.setPath(QPainterPath())
            return

        path = QPainterPath()
        path.moveTo(history[0])
        for point in history[1:]:
            path.lineTo(point)

        track_item.setPath(path)

    def update_platforms(self, platform_list: list[dict]) -> None:
        for platform_info in platform_list:
            self.update_platform(platform_info)

    def select_platform(self, platform_info: dict) -> None:
        self.selected_platform_id = platform_info["id"]

        for pid, item in self.platform_items.items():
            item.set_selected(pid == self.selected_platform_id)

        latest_info = self.latest_platform_info.get(platform_info["id"], platform_info)
        self.on_platform_selected(latest_info)

    def set_show_tracks(self, show: bool) -> None:
        self.show_tracks = show
        for platform_id, item in self.track_items.items():
            if not show:
                item.setPath(QPainterPath())
            else:
                history = self.track_history.get(platform_id, [])
                if len(history) >= 2:
                    path = QPainterPath()
                    path.moveTo(history[0])
                    for point in history[1:]:
                        path.lineTo(point)
                    item.setPath(path)

    def clear_tracks(self) -> None:
        for platform_id in self.track_history:
            current_item = self.platform_items[platform_id]
            self.track_history[platform_id] = [QPointF(current_item.x_val, current_item.y_val)]
            self.track_items[platform_id].setPath(QPainterPath())

    def get_selected_platform_info(self) -> dict | None:
        if self.selected_platform_id is None:
            return None
        return self.latest_platform_info.get(self.selected_platform_id)

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