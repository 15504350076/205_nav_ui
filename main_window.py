from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
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
        self.speed_label = QLabel("--")
        self.timestamp_label = QLabel("--")

        self.map_view = MapView(on_platform_selected=self.on_platform_selected)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("未选中平台")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_update)
        self.timer.start(100)

        self._init_ui()
        self._load_initial_data()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        main_layout.addWidget(self.map_view, 4)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        info_group = QGroupBox("平台信息")
        form_layout = QFormLayout(info_group)
        form_layout.addRow("ID:", self.id_label)
        form_layout.addRow("类型:", self.type_label)
        form_layout.addRow("X 坐标:", self.x_label)
        form_layout.addRow("Y 坐标:", self.y_label)
        form_layout.addRow("Z 坐标:", self.z_label)
        form_layout.addRow("速度:", self.speed_label)
        form_layout.addRow("时间戳:", self.timestamp_label)

        display_group = QGroupBox("显示控制")
        display_layout = QVBoxLayout(display_group)

        self.track_checkbox = QCheckBox("显示轨迹")
        self.track_checkbox.setChecked(True)
        self.track_checkbox.toggled.connect(self.map_view.set_show_tracks)
        display_layout.addWidget(self.track_checkbox)

        clear_track_button = QPushButton("清除轨迹")
        clear_track_button.clicked.connect(self.map_view.clear_tracks)
        display_layout.addWidget(clear_track_button)

        help_group = QGroupBox("操作提示")
        help_layout = QVBoxLayout(help_group)
        help_layout.addWidget(QLabel("1. 鼠标左键点击亮点可选中平台"))
        help_layout.addWidget(QLabel("2. 鼠标滚轮可缩放视图"))
        help_layout.addWidget(QLabel("3. 按键 R 可恢复默认缩放"))
        help_layout.addWidget(QLabel("4. 可勾选显示或隐藏轨迹"))

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
        right_layout.addWidget(display_group)
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

        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info)

    def on_platform_selected(self, platform_info: dict) -> None:
        self.id_label.setText(str(platform_info["id"]))
        self.type_label.setText(str(platform_info["type"]))
        self.x_label.setText(f'{platform_info["x"]:.2f}')
        self.y_label.setText(f'{platform_info["y"]:.2f}')
        self.z_label.setText(f'{platform_info["z"]:.2f}')
        self.speed_label.setText(f'{platform_info.get("speed", 0.0):.2f}')
        self.timestamp_label.setText(f'{platform_info.get("timestamp", 0.0):.2f}')

        self.status_bar.showMessage(
            f'当前选中: {platform_info["id"]} | '
            f'类型: {platform_info["type"]} | '
            f'速度: {platform_info.get("speed", 0.0):.2f}'
        )

    def pause_updates(self) -> None:
        self.timer.stop()
        self.status_bar.showMessage("已暂停刷新")

    def resume_updates(self) -> None:
        self.timer.start(100)
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info)
        else:
            self.status_bar.showMessage("未选中平台，已恢复刷新")

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            "205_nav_ui 原型（第三步）\n\n"
            "当前功能：\n"
            "- 多个平台亮点显示\n"
            "- 鼠标点击选中高亮\n"
            "- 右侧显示平台坐标、速度、时间戳\n"
            "- 假数据定时刷新\n"
            "- 历史轨迹显示与清除\n"
            "- 底部状态栏显示当前选中平台信息",
        )