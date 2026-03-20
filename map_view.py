from typing import Callable

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from models import PlatformState
from platform_item import create_platform_item


class MapView(QGraphicsView):
    """中间态势图显示区。"""

    def __init__(self, on_platform_selected: Callable[[PlatformState], None]) -> None:
        super().__init__()

        self.on_platform_selected = on_platform_selected
        self.platform_items: dict[str, object] = {}
        self.latest_platform_info: dict[str, PlatformState] = {}
        self.track_items: dict[str, QGraphicsPathItem] = {}
        self.track_history: dict[str, list[QPointF]] = {}
        self.stale_platform_ids: set[str] = set()
        self.selected_platform_id: str | None = None
        self.show_tracks = True
        self.show_labels = True
        self.follow_selected = False
        self.lock_pan_when_follow = True
        self.max_track_points = 120

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -300, 800, 600)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._update_drag_mode()
        self.setBackgroundBrush(QColor(35, 35, 35))

        self._add_legend()

    def _add_legend(self) -> None:
        legend_x = -380
        legend_y = -280

        title = QGraphicsSimpleTextItem("图例")
        title.setBrush(QBrush(QColor(230, 230, 230)))
        title.setPos(legend_x, legend_y)
        self.scene.addItem(title)

        uav_shape = QGraphicsEllipseItem(0, 0, 14, 14)
        uav_shape.setBrush(QBrush(QColor(80, 200, 255)))
        uav_shape.setPen(QPen(QColor(30, 30, 30), 1.0))
        uav_shape.setPos(legend_x, legend_y + 25)
        self.scene.addItem(uav_shape)

        uav_text = QGraphicsSimpleTextItem("UAV")
        uav_text.setBrush(QBrush(QColor(230, 230, 230)))
        uav_text.setPos(legend_x + 22, legend_y + 22)
        self.scene.addItem(uav_text)

        ugv_shape = QGraphicsRectItem(0, 0, 14, 14)
        ugv_shape.setBrush(QBrush(QColor(255, 170, 60)))
        ugv_shape.setPen(QPen(QColor(30, 30, 30), 1.0))
        ugv_shape.setPos(legend_x, legend_y + 50)
        self.scene.addItem(ugv_shape)

        ugv_text = QGraphicsSimpleTextItem("UGV")
        ugv_text.setBrush(QBrush(QColor(230, 230, 230)))
        ugv_text.setPos(legend_x + 22, legend_y + 47)
        self.scene.addItem(ugv_text)

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

    def add_platform(self, platform_info: PlatformState) -> None:
        item = create_platform_item(
            platform_id=platform_info.id,
            platform_type=platform_info.type,
            x=platform_info.x,
            y=platform_info.y,
            z=platform_info.z,
            on_selected=self.select_platform,
        )
        item.set_label_visible(self.show_labels)

        self.platform_items[platform_info.id] = item
        self.latest_platform_info[platform_info.id] = platform_info
        self.scene.addItem(item)

        track_item = QGraphicsPathItem()
        track_pen = QPen(item.get_track_color(), 1.8)
        track_item.setPen(track_pen)
        track_item.setZValue(-1)
        self.scene.addItem(track_item)

        self.track_items[platform_info.id] = track_item
        self.track_history[platform_info.id] = [
            QPointF(platform_info.x, platform_info.y)
        ]

    def update_platform(self, platform_info: PlatformState) -> None:
        platform_id = platform_info.id
        if platform_id not in self.platform_items:
            self.add_platform(platform_info)
            return

        item = self.platform_items[platform_id]
        item.update_state(
            x=platform_info.x,
            y=platform_info.y,
            z=platform_info.z,
        )

        self.latest_platform_info[platform_id] = platform_info
        self._update_track(platform_id, platform_info.x, platform_info.y)

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

    def update_platforms(self, platform_list: list[PlatformState]) -> None:
        for platform_info in platform_list:
            self.update_platform(platform_info)
        if self.follow_selected:
            self._center_on_selected()

    def select_platform(self, platform_info: dict | PlatformState) -> None:
        if isinstance(platform_info, PlatformState):
            platform_id = platform_info.id
            fallback_state = platform_info
        else:
            platform_id = str(platform_info["id"])
            fallback_state = PlatformState(
                id=platform_id,
                type=str(platform_info.get("type", "UNKNOWN")),
                x=float(platform_info.get("x", 0.0)),
                y=float(platform_info.get("y", 0.0)),
                z=float(platform_info.get("z", 0.0)),
            )

        self.selected_platform_id = platform_id

        for pid, item in self.platform_items.items():
            item.set_selected(pid == self.selected_platform_id)

        latest_info = self.latest_platform_info.get(platform_id)
        if latest_info is None:
            latest_info = fallback_state
        self.on_platform_selected(latest_info)
        if self.follow_selected:
            self._center_on_selected()

    def select_platform_by_id(self, platform_id: str) -> bool:
        if platform_id not in self.platform_items:
            return False
        platform_info = self.latest_platform_info.get(platform_id)
        if platform_info is None:
            info = self.platform_items[platform_id].get_info()
            platform_info = PlatformState(
                id=info["id"],
                type=info["type"],
                x=float(info["x"]),
                y=float(info["y"]),
                z=float(info["z"]),
            )
        self.select_platform(platform_info)
        return True

    def center_on_selected(self) -> None:
        self._center_on_selected()

    def focus_selected_platform(self) -> bool:
        if self.selected_platform_id is None:
            return False
        item = self.platform_items.get(self.selected_platform_id)
        if item is None:
            return False
        self.centerOn(item)
        return True

    def fit_all_platforms(self, padding: float = 30.0) -> bool:
        if not self.platform_items:
            return False
        bounds: QRectF | None = None
        for item in self.platform_items.values():
            item_rect = item.sceneBoundingRect()
            if bounds is None:
                bounds = item_rect
            else:
                bounds = bounds.united(item_rect)
        if bounds is None:
            return False
        bounds.adjust(-padding, -padding, padding, padding)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def reset_view(self) -> None:
        self.resetTransform()

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

    def set_show_labels(self, show: bool) -> None:
        self.show_labels = show
        for item in self.platform_items.values():
            item.set_label_visible(show)

    def set_follow_selected(self, follow: bool) -> None:
        self.follow_selected = follow
        self._update_drag_mode()
        if self.follow_selected:
            self._center_on_selected()

    def set_lock_pan_when_follow(self, lock: bool) -> None:
        self.lock_pan_when_follow = lock
        self._update_drag_mode()

    def set_stale_platforms(self, stale_platform_ids: set[str]) -> None:
        self.stale_platform_ids = set(stale_platform_ids)
        for platform_id, item in self.platform_items.items():
            item.set_stale(platform_id in self.stale_platform_ids)

    def remove_platforms(self, platform_ids: list[str]) -> None:
        for platform_id in platform_ids:
            self._remove_platform(platform_id)

    def is_platform_stale(self, platform_id: str) -> bool:
        return platform_id in self.stale_platform_ids

    def get_stale_platform_ids(self) -> set[str]:
        return set(self.stale_platform_ids)

    def get_all_platform_infos(self) -> list[PlatformState]:
        return list(self.latest_platform_info.values())

    def clear_tracks(self) -> None:
        for platform_id in self.track_history:
            current_item = self.platform_items[platform_id]
            self.track_history[platform_id] = [QPointF(current_item.x_val, current_item.y_val)]
            self.track_items[platform_id].setPath(QPainterPath())

    def get_selected_platform_info(self) -> PlatformState | None:
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

    def _center_on_selected(self) -> None:
        if self.selected_platform_id is None:
            return
        item = self.platform_items.get(self.selected_platform_id)
        if item is None:
            return
        self.centerOn(item)

    def _update_drag_mode(self) -> None:
        if self.follow_selected and self.lock_pan_when_follow:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def _remove_platform(self, platform_id: str) -> None:
        platform_item = self.platform_items.pop(platform_id, None)
        if platform_item is not None:
            self.scene.removeItem(platform_item)

        track_item = self.track_items.pop(platform_id, None)
        if track_item is not None:
            self.scene.removeItem(track_item)

        self.track_history.pop(platform_id, None)
        self.latest_platform_info.pop(platform_id, None)
        self.stale_platform_ids.discard(platform_id)

        if self.selected_platform_id == platform_id:
            self.selected_platform_id = None
