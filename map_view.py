"""地图视图模块：负责平台图元、轨迹、真值层与缩放交互渲染。"""

import math
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
    QSizePolicy,
)

from platform_state import PlatformState
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
        self.track_time_history: dict[str, list[float]] = {}
        self.velocity_vector_items: dict[str, QGraphicsPathItem] = {}
        self.truth_items: dict[str, QGraphicsEllipseItem] = {}
        self.truth_track_items: dict[str, QGraphicsPathItem] = {}
        self.truth_track_history: dict[str, list[QPointF]] = {}
        self.truth_track_time_history: dict[str, list[float]] = {}
        self.stale_platform_ids: set[str] = set()
        self.selected_platform_id: str | None = None
        self.show_tracks = True
        self.show_labels = True
        self.show_truth_points = True
        self.show_truth_tracks = True
        self.show_velocity_vectors = False
        self.follow_selected = False
        self.lock_pan_when_follow = True
        self.track_duration_sec = 12.0
        self.max_track_points = 2000
        self.velocity_vector_scale = 1.8
        self.velocity_vector_min_length = 12.0
        self.velocity_vector_max_length = 65.0

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -300, 800, 600)
        self.setScene(self.scene)

        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._update_drag_mode()
        self.setBackgroundBrush(QColor(35, 35, 35))

        self._add_legend()
        self._fit_scene_to_view()

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

        truth_shape = QGraphicsEllipseItem(0, 0, 14, 14)
        truth_shape.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        truth_shape.setPen(QPen(QColor(180, 255, 120), 1.5, Qt.PenStyle.DashLine))
        truth_shape.setPos(legend_x, legend_y + 75)
        self.scene.addItem(truth_shape)

        truth_text = QGraphicsSimpleTextItem("Truth")
        truth_text.setBrush(QBrush(QColor(230, 230, 230)))
        truth_text.setPos(legend_x + 22, legend_y + 72)
        self.scene.addItem(truth_text)

        truth_track_line = QGraphicsPathItem()
        truth_track_path = QPainterPath()
        truth_track_path.moveTo(0, 0)
        truth_track_path.lineTo(16, 0)
        truth_track_line.setPath(truth_track_path)
        truth_track_line.setPen(QPen(QColor(120, 220, 120), 1.4, Qt.PenStyle.DashLine))
        truth_track_line.setPos(legend_x, legend_y + 97)
        self.scene.addItem(truth_track_line)

        truth_track_text = QGraphicsSimpleTextItem("Truth Track")
        truth_track_text.setBrush(QBrush(QColor(230, 230, 230)))
        truth_track_text.setPos(legend_x + 22, legend_y + 90)
        self.scene.addItem(truth_track_text)

        velocity_uav_line = QGraphicsPathItem()
        velocity_path = QPainterPath()
        velocity_path.moveTo(0, 0)
        velocity_path.lineTo(16, 0)
        velocity_path.moveTo(16, 0)
        velocity_path.lineTo(11, -3)
        velocity_path.moveTo(16, 0)
        velocity_path.lineTo(11, 3)
        velocity_uav_line.setPath(velocity_path)
        velocity_uav_line.setPen(QPen(QColor(80, 200, 255), 1.6, Qt.PenStyle.SolidLine))
        velocity_uav_line.setPos(legend_x, legend_y + 118)
        self.scene.addItem(velocity_uav_line)

        velocity_uav_text = QGraphicsSimpleTextItem("Velocity UAV")
        velocity_uav_text.setBrush(QBrush(QColor(230, 230, 230)))
        velocity_uav_text.setPos(legend_x + 22, legend_y + 110)
        self.scene.addItem(velocity_uav_text)

        velocity_ugv_line = QGraphicsPathItem()
        velocity_ugv_path = QPainterPath()
        velocity_ugv_path.moveTo(0, 0)
        velocity_ugv_path.lineTo(16, 0)
        velocity_ugv_path.moveTo(16, 0)
        velocity_ugv_path.lineTo(11, -3)
        velocity_ugv_path.moveTo(16, 0)
        velocity_ugv_path.lineTo(11, 3)
        velocity_ugv_line.setPath(velocity_ugv_path)
        velocity_ugv_line.setPen(QPen(QColor(255, 170, 60), 1.6, Qt.PenStyle.DashLine))
        velocity_ugv_line.setPos(legend_x, legend_y + 138)
        self.scene.addItem(velocity_ugv_line)

        velocity_ugv_text = QGraphicsSimpleTextItem("Velocity UGV")
        velocity_ugv_text.setBrush(QBrush(QColor(230, 230, 230)))
        velocity_ugv_text.setPos(legend_x + 22, legend_y + 130)
        self.scene.addItem(velocity_ugv_text)

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
        self.track_time_history[platform_info.id] = [platform_info.timestamp]
        self._trim_estimated_track(platform_info.id)
        self._refresh_estimated_track_path(platform_info.id)

        velocity_vector_item = QGraphicsPathItem()
        velocity_vector_item.setPen(self._velocity_pen_for_platform(platform_info.id, platform_info))
        velocity_vector_item.setZValue(-0.8)
        self.scene.addItem(velocity_vector_item)
        self.velocity_vector_items[platform_info.id] = velocity_vector_item
        self._update_velocity_vector(platform_info.id, platform_info)

        truth_item = QGraphicsEllipseItem(-5, -5, 10, 10)
        truth_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        truth_item.setPen(QPen(QColor(180, 255, 120), 1.5, Qt.PenStyle.DashLine))
        truth_item.setVisible(False)
        truth_item.setZValue(0.5)
        self.scene.addItem(truth_item)
        self.truth_items[platform_info.id] = truth_item
        self._update_truth_marker(platform_info.id, platform_info)

        truth_track_item = QGraphicsPathItem()
        truth_track_item.setPen(QPen(QColor(120, 220, 120), 1.4, Qt.PenStyle.DashLine))
        truth_track_item.setZValue(-1.2)
        self.scene.addItem(truth_track_item)
        self.truth_track_items[platform_info.id] = truth_track_item
        truth_history: list[QPointF] = []
        truth_time_history: list[float] = []
        if platform_info.truth_x is not None and platform_info.truth_y is not None:
            truth_history.append(QPointF(platform_info.truth_x, platform_info.truth_y))
            truth_time_history.append(platform_info.timestamp)
        self.truth_track_history[platform_info.id] = truth_history
        self.truth_track_time_history[platform_info.id] = truth_time_history
        self._trim_truth_track(platform_info.id)
        self._refresh_truth_track_path(platform_info.id)

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
        self._update_track(
            platform_id,
            platform_info.x,
            platform_info.y,
            platform_info.timestamp,
        )
        self._update_velocity_vector(platform_id, platform_info)
        self._update_truth_marker(platform_id, platform_info)
        self._update_truth_track(platform_id, platform_info)

    def _update_track(
        self,
        platform_id: str,
        x: float,
        y: float,
        timestamp: float,
    ) -> None:
        if platform_id not in self.track_history:
            self.track_history[platform_id] = []
        if platform_id not in self.track_time_history:
            self.track_time_history[platform_id] = []

        history = self.track_history[platform_id]
        time_history = self.track_time_history[platform_id]
        history.append(QPointF(x, y))
        time_history.append(timestamp)
        self._trim_estimated_track(platform_id)
        self._refresh_estimated_track_path(platform_id)

    def update_platforms(self, platform_list: list[PlatformState]) -> None:
        for platform_info in platform_list:
            self.update_platform(platform_info)
        if self.follow_selected:
            self._center_on_selected()

    def select_platform(self, platform_info: PlatformState) -> None:
        platform_id = platform_info.id
        fallback_state = platform_info

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
            platform_info = self.platform_items[platform_id].get_info()
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
        self._fit_scene_to_view()

    def set_show_tracks(self, show: bool) -> None:
        self.show_tracks = show
        self._refresh_all_estimated_track_paths()

    def set_show_labels(self, show: bool) -> None:
        self.show_labels = show
        for item in self.platform_items.values():
            item.set_label_visible(show)

    def set_show_truth_points(self, show: bool) -> None:
        self.show_truth_points = show
        for platform_id, truth_item in self.truth_items.items():
            state = self.latest_platform_info.get(platform_id)
            if state is None:
                truth_item.setVisible(False)
                continue
            has_truth = state.truth_x is not None and state.truth_y is not None
            truth_item.setVisible(self.show_truth_points and has_truth)

    def set_show_truth_tracks(self, show: bool) -> None:
        self.show_truth_tracks = show
        self._refresh_all_truth_track_paths()

    def set_show_velocity_vectors(self, show: bool) -> None:
        self.show_velocity_vectors = show
        self._refresh_all_velocity_vectors()

    def set_track_duration(self, duration_sec: float) -> None:
        self.track_duration_sec = max(0.5, duration_sec)
        for platform_id in self.track_history:
            self._trim_estimated_track(platform_id)
        for platform_id in self.truth_track_history:
            self._trim_truth_track(platform_id)
        self._refresh_all_estimated_track_paths()
        self._refresh_all_truth_track_paths()

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
        self._refresh_all_velocity_vectors()

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
            state = self.latest_platform_info.get(platform_id)
            current_ts = state.timestamp if state is not None else 0.0
            self.track_history[platform_id] = [QPointF(current_item.x_val, current_item.y_val)]
            self.track_time_history[platform_id] = [current_ts]
            self.track_items[platform_id].setPath(QPainterPath())

            truth_history: list[QPointF] = []
            truth_time_history: list[float] = []
            if state is not None and state.truth_x is not None and state.truth_y is not None:
                truth_history.append(QPointF(state.truth_x, state.truth_y))
                truth_time_history.append(state.timestamp)
            self.truth_track_history[platform_id] = truth_history
            self.truth_track_time_history[platform_id] = truth_time_history
            truth_track_item = self.truth_track_items.get(platform_id)
            if truth_track_item is not None:
                truth_track_item.setPath(QPainterPath())

    def export_snapshot(self, file_path: str) -> bool:
        snapshot = self.viewport().grab()
        return snapshot.save(file_path, "PNG")

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
            self.reset_view()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_scene_to_view()

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

    def _fit_scene_to_view(self) -> None:
        if self.viewport().width() <= 0 or self.viewport().height() <= 0:
            return
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _remove_platform(self, platform_id: str) -> None:
        platform_item = self.platform_items.pop(platform_id, None)
        if platform_item is not None:
            self.scene.removeItem(platform_item)

        track_item = self.track_items.pop(platform_id, None)
        if track_item is not None:
            self.scene.removeItem(track_item)

        velocity_item = self.velocity_vector_items.pop(platform_id, None)
        if velocity_item is not None:
            self.scene.removeItem(velocity_item)

        truth_track_item = self.truth_track_items.pop(platform_id, None)
        if truth_track_item is not None:
            self.scene.removeItem(truth_track_item)

        truth_item = self.truth_items.pop(platform_id, None)
        if truth_item is not None:
            self.scene.removeItem(truth_item)

        self.track_history.pop(platform_id, None)
        self.track_time_history.pop(platform_id, None)
        self.truth_track_history.pop(platform_id, None)
        self.truth_track_time_history.pop(platform_id, None)
        self.latest_platform_info.pop(platform_id, None)
        self.stale_platform_ids.discard(platform_id)

        if self.selected_platform_id == platform_id:
            self.selected_platform_id = None

    def _update_truth_marker(self, platform_id: str, platform_info: PlatformState) -> None:
        truth_item = self.truth_items.get(platform_id)
        if truth_item is None:
            return
        if platform_info.truth_x is None or platform_info.truth_y is None:
            truth_item.setVisible(False)
            return
        truth_item.setPos(platform_info.truth_x, platform_info.truth_y)
        truth_item.setVisible(self.show_truth_points)

    def _update_truth_track(self, platform_id: str, platform_info: PlatformState) -> None:
        history = self.truth_track_history.get(platform_id)
        time_history = self.truth_track_time_history.get(platform_id)
        track_item = self.truth_track_items.get(platform_id)
        if (
            history is None
            or time_history is None
            or track_item is None
        ):
            return

        if platform_info.truth_x is None or platform_info.truth_y is None:
            track_item.setPath(QPainterPath())
            return

        history.append(QPointF(platform_info.truth_x, platform_info.truth_y))
        time_history.append(platform_info.timestamp)
        self._trim_truth_track(platform_id)
        self._refresh_truth_track_path(platform_id)

    def _trim_estimated_track(self, platform_id: str) -> None:
        history = self.track_history.get(platform_id)
        time_history = self.track_time_history.get(platform_id)
        if history is None or time_history is None:
            return

        if not history or not time_history:
            return

        # Keep paired sequences aligned.
        if len(history) != len(time_history):
            min_len = min(len(history), len(time_history))
            history[:] = history[-min_len:]
            time_history[:] = time_history[-min_len:]

        while len(history) > self.max_track_points:
            history.pop(0)
            time_history.pop(0)

        cutoff_time = time_history[-1] - self.track_duration_sec
        while len(time_history) > 1 and time_history[1] < cutoff_time:
            history.pop(0)
            time_history.pop(0)

    def _trim_truth_track(self, platform_id: str) -> None:
        history = self.truth_track_history.get(platform_id)
        time_history = self.truth_track_time_history.get(platform_id)
        if history is None or time_history is None:
            return

        if not history or not time_history:
            return

        min_len = min(len(history), len(time_history))
        history[:] = history[-min_len:]
        time_history[:] = time_history[-min_len:]

        while len(history) > self.max_track_points:
            history.pop(0)
            time_history.pop(0)

        cutoff_time = time_history[-1] - self.track_duration_sec
        while len(time_history) > 1 and time_history[1] < cutoff_time:
            history.pop(0)
            time_history.pop(0)

    def _refresh_estimated_track_path(self, platform_id: str) -> None:
        track_item = self.track_items.get(platform_id)
        history = self.track_history.get(platform_id, [])
        if track_item is None:
            return
        if not self.show_tracks or len(history) < 2:
            track_item.setPath(QPainterPath())
            return
        path = QPainterPath()
        path.moveTo(history[0])
        for point in history[1:]:
            path.lineTo(point)
        track_item.setPath(path)

    def _refresh_truth_track_path(self, platform_id: str) -> None:
        track_item = self.truth_track_items.get(platform_id)
        history = self.truth_track_history.get(platform_id, [])
        if track_item is None:
            return
        if not self.show_truth_tracks or len(history) < 2:
            track_item.setPath(QPainterPath())
            return
        path = QPainterPath()
        path.moveTo(history[0])
        for point in history[1:]:
            path.lineTo(point)
        track_item.setPath(path)

    def _update_velocity_vector(self, platform_id: str, platform_info: PlatformState) -> None:
        vector_item = self.velocity_vector_items.get(platform_id)
        if vector_item is None:
            return

        if not self.show_velocity_vectors:
            vector_item.setPath(QPainterPath())
            return

        planar_speed = math.hypot(platform_info.vx, platform_info.vy)
        if planar_speed < 1e-6:
            vector_item.setPath(QPainterPath())
            return

        direction_x = platform_info.vx / planar_speed
        direction_y = platform_info.vy / planar_speed
        vector_length = planar_speed * self.velocity_vector_scale
        vector_length = max(
            self.velocity_vector_min_length,
            min(self.velocity_vector_max_length, vector_length),
        )

        start_x = platform_info.x
        start_y = platform_info.y
        end_x = start_x + direction_x * vector_length
        end_y = start_y + direction_y * vector_length

        head_length = max(5.0, min(10.0, vector_length * 0.26))
        head_half_width = head_length * 0.55
        left_x = end_x - direction_x * head_length - direction_y * head_half_width
        left_y = end_y - direction_y * head_length + direction_x * head_half_width
        right_x = end_x - direction_x * head_length + direction_y * head_half_width
        right_y = end_y - direction_y * head_length - direction_x * head_half_width

        path = QPainterPath()
        path.moveTo(start_x, start_y)
        path.lineTo(end_x, end_y)
        path.moveTo(end_x, end_y)
        path.lineTo(left_x, left_y)
        path.moveTo(end_x, end_y)
        path.lineTo(right_x, right_y)
        vector_item.setPath(path)

        vector_item.setPen(self._velocity_pen_for_platform(platform_id, platform_info))

    def _velocity_pen_for_platform(
        self,
        platform_id: str,
        platform_info: PlatformState,
    ) -> QPen:
        if platform_id in self.stale_platform_ids:
            return QPen(QColor(140, 140, 140), 1.5, Qt.PenStyle.DotLine)

        platform_item = self.platform_items.get(platform_id)
        if platform_item is None:
            return QPen(QColor(220, 220, 220), 1.5, Qt.PenStyle.SolidLine)

        base_color = platform_item.get_track_color()
        platform_type = platform_info.type.upper()
        if platform_type == "UGV":
            return QPen(base_color, 1.6, Qt.PenStyle.DashLine)
        return QPen(base_color, 1.8, Qt.PenStyle.SolidLine)

    def _refresh_all_estimated_track_paths(self) -> None:
        for platform_id in self.track_items:
            self._refresh_estimated_track_path(platform_id)

    def _refresh_all_truth_track_paths(self) -> None:
        for platform_id in self.truth_track_items:
            self._refresh_truth_track_path(platform_id)

    def _refresh_all_velocity_vectors(self) -> None:
        for platform_id, state in self.latest_platform_info.items():
            self._update_velocity_vector(platform_id, state)
