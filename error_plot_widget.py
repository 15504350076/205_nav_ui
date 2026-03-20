from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ErrorPlotWidget(QWidget):
    """显示误差序列的轻量级曲线图控件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[float] = []
        self.setMinimumHeight(140)

    def set_series(self, series: list[float]) -> None:
        self._series = list(series)
        self.update()

    def clear(self) -> None:
        self._series = []
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(28, 28, 28))

        margin = 12
        chart_rect = self.rect().adjusted(margin, margin, -margin, -margin)
        if chart_rect.width() <= 1 or chart_rect.height() <= 1:
            return

        grid_pen = QPen(QColor(56, 56, 56), 1)
        painter.setPen(grid_pen)
        for i in range(1, 4):
            y = chart_rect.top() + chart_rect.height() * i / 4
            painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)

        border_pen = QPen(QColor(120, 120, 120), 1.0)
        painter.setPen(border_pen)
        painter.drawRect(chart_rect)

        if len(self._series) < 2:
            painter.setPen(QPen(QColor(170, 170, 170), 1))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter, "暂无误差曲线")
            return

        min_val = min(self._series)
        max_val = max(self._series)
        if max_val - min_val < 1e-6:
            min_val -= 0.5
            max_val += 0.5

        x_span = max(len(self._series) - 1, 1)
        y_span = max_val - min_val
        points: list[QPointF] = []
        for index, value in enumerate(self._series):
            x = chart_rect.left() + chart_rect.width() * index / x_span
            y_ratio = (value - min_val) / y_span
            y = chart_rect.bottom() - chart_rect.height() * y_ratio
            points.append(QPointF(x, y))

        curve_pen = QPen(QColor(255, 210, 90), 2.0)
        painter.setPen(curve_pen)
        for start, end in zip(points[:-1], points[1:]):
            painter.drawLine(start, end)

        value_pen = QPen(QColor(220, 220, 220), 1.0)
        painter.setPen(value_pen)
        painter.drawText(
            chart_rect.adjusted(6, 4, -6, -4),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            f"min {min_val:.2f}  max {max_val:.2f}  latest {self._series[-1]:.2f}",
        )
