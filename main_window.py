from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fake_data import FakeDataGenerator
from map_view import MapView


class MainWindow(QMainWindow):
    """主窗口：中间地图，右侧信息栏。"""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("205_nav_ui - PySide6 原型")
        self.resize(1200, 700)

        self.data_generator = FakeDataGenerator()

        self.id_label = QLabel("--")
        self.type_label = QLabel("--")
        self.x_label = QLabel("--")
        self.y_label = QLabel("--")
        self.z_label = QLabel("--")

        self.map_view = MapView(on_platform_selected=self.on_platform_selected)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_update)
        self.timer.start(100)  # 100 ms 刷新一次

        self._init_ui()
        self._load_initial_data()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # 中间态势图
        main_layout.addWidget(self.map_view, 4)

        # 右侧信息区
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        info_group = QGroupBox("平台信息")
        form_layout = QFormLayout(info_group)
        form_layout.addRow("ID:", self.id_label)
        form_layout.addRow("类型:", self.type_label)
        form_layout.addRow("X 坐标:", self.x_label)
        form_layout.addRow("Y 坐标:", self.y_label)
        form_layout.addRow("Z 坐标:", self.z_label)

        help_group = QGroupBox("操作提示")
        help_layout = QVBoxLayout(help_group)
        help_layout.addWidget(QLabel("1. 鼠标左键点击亮点可选中平台"))
        help_layout.addWidget(QLabel("2. 鼠标滚轮可缩放视图"))
        help_layout.addWidget(QLabel("3. 按键 R 可恢复默认缩放"))

        button_group = QGroupBox("控制")
        button_layout = QVBoxLayout(button_group)

        pause_button = QPushButton("暂停刷新")
        pause_button.clicked.connect(self.pause_updates)
        button_layout.addWidget(pause_button)

        resume_button = QPushButton("恢复刷新")
        resume_button.clicked.connect(self.resume_updates)
        button_layout.addWidget(resume_button)

        about_button = QPushButton("关于")
        about_button.clicked.connect(self.show_about)
        button_layout.addWidget(about_button)

        right_layout.addWidget(info_group)
        right_layout.addWidget(help_group)
        right_layout.addWidget(button_group)
        right_layout.addStretch()

        main_layout.addWidget(right_panel, 1)

    def _load_initial_data(self) -> None:
        initial_data = self.data_generator.get_initial_data()
        self.map_view.update_platforms(initial_data)

    def on_timer_update(self) -> None:
        platform_data = self.data_generator.get_next_frame()
        self.map_view.update_platforms(platform_data)

        # 如果当前有选中目标，则同步刷新右侧坐标
        if self.map_view.selected_platform_id is not None:
            selected_id = self.map_view.selected_platform_id
            for platform in platform_data:
                if platform["id"] == selected_id:
                    self.on_platform_selected(platform)
                    break

    def on_platform_selected(self, platform_info: dict) -> None:
        self.id_label.setText(str(platform_info["id"]))
        self.type_label.setText(str(platform_info["type"]))
        self.x_label.setText(f'{platform_info["x"]:.2f}')
        self.y_label.setText(f'{platform_info["y"]:.2f}')
        self.z_label.setText(f'{platform_info["z"]:.2f}')

    def pause_updates(self) -> None:
        self.timer.stop()

    def resume_updates(self) -> None:
        self.timer.start(100)

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            "205_nav_ui 最小可运行原型\n\n"
            "功能：\n"
            "- 多个平台亮点显示\n"
            "- 鼠标点击选中高亮\n"
            "- 右侧显示平台坐标\n"
            "- 假数据定时刷新",
        )