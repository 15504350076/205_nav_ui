from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
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
        self.platform_row_by_id: dict[str, int] = {}
        self._syncing_table_selection = False
        self.base_timer_interval_ms = 100
        self.playback_speed = 1.0

        self.map_view = MapView(on_platform_selected=self.on_platform_selected)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("未选中平台")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_update)
        self.timer.start(self._current_timer_interval_ms())

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

        list_group = QGroupBox("平台列表")
        list_layout = QVBoxLayout(list_group)
        self.platform_table = QTableWidget(0, 5)
        self.platform_table.setHorizontalHeaderLabels(["ID", "类型", "速度", "时间戳", "状态"])
        self.platform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.platform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.platform_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.platform_table.setAlternatingRowColors(True)
        self.platform_table.verticalHeader().setVisible(False)
        self.platform_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.platform_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.platform_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.platform_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.platform_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.platform_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        list_layout.addWidget(self.platform_table)

        display_group = QGroupBox("显示控制")
        display_layout = QVBoxLayout(display_group)

        self.follow_checkbox = QCheckBox("跟随选中目标")
        self.follow_checkbox.setChecked(False)
        self.follow_checkbox.toggled.connect(self.on_follow_toggled)
        display_layout.addWidget(self.follow_checkbox)

        self.follow_lock_checkbox = QCheckBox("跟随时禁用拖拽")
        self.follow_lock_checkbox.setChecked(True)
        self.follow_lock_checkbox.setEnabled(False)
        self.follow_lock_checkbox.toggled.connect(self.map_view.set_lock_pan_when_follow)
        display_layout.addWidget(self.follow_lock_checkbox)

        self.track_checkbox = QCheckBox("显示轨迹")
        self.track_checkbox.setChecked(True)
        self.track_checkbox.toggled.connect(self.map_view.set_show_tracks)
        display_layout.addWidget(self.track_checkbox)

        self.label_checkbox = QCheckBox("显示编号")
        self.label_checkbox.setChecked(True)
        self.label_checkbox.toggled.connect(self.map_view.set_show_labels)
        display_layout.addWidget(self.label_checkbox)

        clear_track_button = QPushButton("清除轨迹")
        clear_track_button.clicked.connect(self.map_view.clear_tracks)
        display_layout.addWidget(clear_track_button)

        threshold_group = QGroupBox("阈值配置")
        threshold_layout = QFormLayout(threshold_group)

        self.stale_timeout_spin = QDoubleSpinBox()
        self.stale_timeout_spin.setDecimals(1)
        self.stale_timeout_spin.setRange(0.1, 30.0)
        self.stale_timeout_spin.setSingleStep(0.1)
        self.stale_timeout_spin.setSuffix(" s")
        self.stale_timeout_spin.setValue(self.map_view.stale_timeout_sec)
        self.stale_timeout_spin.valueChanged.connect(self.on_stale_timeout_changed)
        threshold_layout.addRow("超时告警阈值:", self.stale_timeout_spin)

        self.remove_timeout_spin = QDoubleSpinBox()
        self.remove_timeout_spin.setDecimals(1)
        self.remove_timeout_spin.setRange(self.stale_timeout_spin.value(), 60.0)
        self.remove_timeout_spin.setSingleStep(0.5)
        self.remove_timeout_spin.setSuffix(" s")
        self.remove_timeout_spin.setValue(self.map_view.remove_timeout_sec)
        self.remove_timeout_spin.valueChanged.connect(self.on_remove_timeout_changed)
        threshold_layout.addRow("下线移除阈值:", self.remove_timeout_spin)

        help_group = QGroupBox("操作提示")
        help_layout = QVBoxLayout(help_group)
        help_layout.addWidget(QLabel("1. 鼠标左键点击平台可选中"))
        help_layout.addWidget(QLabel("2. UAV 用圆点表示"))
        help_layout.addWidget(QLabel("3. UGV 用方块表示"))
        help_layout.addWidget(QLabel("4. 鼠标滚轮可缩放，按 R 复位"))
        help_layout.addWidget(QLabel("5. 可开启跟随选中目标"))
        help_layout.addWidget(QLabel("6. 跟随时可禁用手动拖拽"))
        help_layout.addWidget(QLabel("7. 列表点击平台可联动选中与定位"))
        help_layout.addWidget(QLabel("8. 超时平台会灰显并告警"))
        help_layout.addWidget(QLabel("9. 告警阈值与移除阈值可在线调整"))
        help_layout.addWidget(QLabel("10. 暂停后可单步刷新一帧"))
        help_layout.addWidget(QLabel("11. 支持0.5x/1.0x/2.0x回放倍速"))

        button_group = QGroupBox("控制")
        button_layout = QVBoxLayout(button_group)

        self.playback_speed_combo = QComboBox()
        self.playback_speed_combo.addItem("0.5x", 0.5)
        self.playback_speed_combo.addItem("1.0x", 1.0)
        self.playback_speed_combo.addItem("2.0x", 2.0)
        self.playback_speed_combo.setCurrentIndex(1)
        self.playback_speed_combo.currentIndexChanged.connect(self.on_playback_speed_changed)
        button_layout.addWidget(QLabel("回放倍速"))
        button_layout.addWidget(self.playback_speed_combo)

        pause_button = QPushButton("暂停刷新")
        pause_button.clicked.connect(self.pause_updates)
        button_layout.addWidget(pause_button)

        step_button = QPushButton("单步刷新")
        step_button.clicked.connect(self.step_once)
        button_layout.addWidget(step_button)

        resume_button = QPushButton("恢复刷新")
        resume_button.clicked.connect(self.resume_updates)
        button_layout.addWidget(resume_button)

        about_button = QPushButton("关于")
        about_button.clicked.connect(self.show_about)
        button_layout.addWidget(about_button)

        right_layout.addWidget(info_group)
        right_layout.addWidget(list_group)
        right_layout.addWidget(display_group)
        right_layout.addWidget(threshold_group)
        right_layout.addWidget(help_group)
        right_layout.addWidget(button_group)
        right_layout.addStretch()

        main_layout.addWidget(right_panel, 1)

    def _load_initial_data(self) -> None:
        initial_data = self.data_generator.get_initial_data()
        self.map_view.update_platforms(initial_data)
        self.update_platform_table(self.map_view.get_all_platform_infos())

    def on_timer_update(self) -> None:
        platform_data = self.data_generator.get_next_frame()
        self._apply_frame_update(platform_data)

    def _apply_frame_update(self, platform_data: list[dict], status_prefix: str = "") -> None:
        removed_ids = self.map_view.update_platforms(platform_data)
        self.update_platform_table(self.map_view.get_all_platform_infos())

        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix=status_prefix)
            return

        if removed_ids:
            self.clear_selected_platform_info()
            self.platform_table.clearSelection()

        stale_count = len(self.map_view.get_stale_platform_ids())
        removed_count = len(removed_ids)
        if stale_count > 0:
            message = (
                f"未选中平台 | 超时平台: {stale_count} | 本帧移除: {removed_count}"
            )
        elif removed_count > 0:
            message = f"未选中平台 | 本帧移除: {removed_count}"
        else:
            message = "未选中平台"
        if status_prefix:
            message = f"{status_prefix} | {message}"
        self.status_bar.showMessage(message)

    def on_platform_selected(self, platform_info: dict, status_prefix: str = "") -> None:
        self.id_label.setText(str(platform_info["id"]))
        self.type_label.setText(str(platform_info["type"]))
        self.x_label.setText(f'{platform_info["x"]:.2f}')
        self.y_label.setText(f'{platform_info["y"]:.2f}')
        self.z_label.setText(f'{platform_info["z"]:.2f}')
        self.speed_label.setText(f'{platform_info.get("speed", 0.0):.2f}')
        self.timestamp_label.setText(f'{platform_info.get("timestamp", 0.0):.2f}')

        selected_id = str(platform_info["id"])
        stale_count = len(self.map_view.get_stale_platform_ids())
        selected_stale = self.map_view.is_platform_stale(selected_id)
        selected_state_text = "超时" if selected_stale else "正常"

        message = (
            f'当前选中: {selected_id} | '
            f'类型: {platform_info["type"]} | '
            f'速度: {platform_info.get("speed", 0.0):.2f} | '
            f'状态: {selected_state_text}'
        )
        if stale_count > 0:
            message += f" | 超时平台: {stale_count}"
        if status_prefix:
            message = f"{status_prefix} | {message}"
        self.status_bar.showMessage(message)
        self.sync_table_selection(platform_info["id"])

    def pause_updates(self) -> None:
        self.timer.stop()
        self.status_bar.showMessage("已暂停刷新")

    def step_once(self) -> None:
        if self.timer.isActive():
            self.status_bar.showMessage("当前为自动刷新模式，请先暂停后再单步刷新")
            return
        platform_data = self.data_generator.get_next_frame()
        self._apply_frame_update(platform_data, status_prefix="单步刷新完成")

    def on_follow_toggled(self, enabled: bool) -> None:
        self.map_view.set_follow_selected(enabled)
        self.follow_lock_checkbox.setEnabled(enabled)

    def on_stale_timeout_changed(self, value: float) -> None:
        self.map_view.set_stale_timeout(value)
        self.remove_timeout_spin.setMinimum(value)
        if self.remove_timeout_spin.value() < value:
            self.remove_timeout_spin.setValue(value)

    def on_remove_timeout_changed(self, value: float) -> None:
        self.map_view.set_remove_timeout(value)

    def on_playback_speed_changed(self, index: int) -> None:
        speed = self.playback_speed_combo.itemData(index)
        if speed is None:
            return
        self.playback_speed = float(speed)
        if self.timer.isActive():
            self.timer.start(self._current_timer_interval_ms())
            self.status_bar.showMessage(f"已切换回放倍速: {self.playback_speed:.1f}x")
        else:
            self.status_bar.showMessage(
                f"已设置回放倍速: {self.playback_speed:.1f}x（当前为暂停状态）"
            )

    def resume_updates(self) -> None:
        self.timer.start(self._current_timer_interval_ms())
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix="已恢复自动刷新")
        else:
            self.status_bar.showMessage("未选中平台，已恢复刷新")

    def _current_timer_interval_ms(self) -> int:
        speed = max(self.playback_speed, 0.1)
        return max(10, int(self.base_timer_interval_ms / speed))

    def update_platform_table(self, platform_list: list[dict]) -> None:
        incoming_ids = {str(platform_info["id"]) for platform_info in platform_list}
        removed_ids = [pid for pid in self.platform_row_by_id if pid not in incoming_ids]
        if removed_ids:
            blocker = QSignalBlocker(self.platform_table)
            try:
                rows_to_remove = sorted(
                    (self.platform_row_by_id[pid] for pid in removed_ids),
                    reverse=True,
                )
                for row in rows_to_remove:
                    self.platform_table.removeRow(row)
                self._rebuild_platform_row_mapping()
            finally:
                del blocker

        for platform_info in platform_list:
            platform_id = str(platform_info["id"])
            row = self.platform_row_by_id.get(platform_id)
            if row is None:
                row = self.platform_table.rowCount()
                self.platform_table.insertRow(row)
                self.platform_row_by_id[platform_id] = row
                self._set_table_text(row, 0, platform_id)
                self._set_table_text(row, 1, str(platform_info.get("type", "--")))

            self._set_table_text(row, 2, f'{platform_info.get("speed", 0.0):.2f}')
            self._set_table_text(row, 3, f'{platform_info.get("timestamp", 0.0):.2f}')
            is_stale = self.map_view.is_platform_stale(platform_id)
            self._set_table_text(row, 4, "超时" if is_stale else "正常")
            self._set_row_style(row, is_stale)

    def _set_table_text(self, row: int, col: int, text: str) -> None:
        item = self.platform_table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.platform_table.setItem(row, col, item)
        item.setText(text)

    def _set_row_style(self, row: int, is_stale: bool) -> None:
        if is_stale:
            foreground = QBrush(QColor(255, 120, 120))
        else:
            foreground = QBrush(QColor(230, 230, 230))
        for col in range(self.platform_table.columnCount()):
            item = self.platform_table.item(row, col)
            if item is not None:
                item.setForeground(foreground)

    def _rebuild_platform_row_mapping(self) -> None:
        self.platform_row_by_id.clear()
        for row in range(self.platform_table.rowCount()):
            id_item = self.platform_table.item(row, 0)
            if id_item is not None:
                self.platform_row_by_id[id_item.text()] = row

    def clear_selected_platform_info(self) -> None:
        self.id_label.setText("--")
        self.type_label.setText("--")
        self.x_label.setText("--")
        self.y_label.setText("--")
        self.z_label.setText("--")
        self.speed_label.setText("--")
        self.timestamp_label.setText("--")

    def on_table_selection_changed(self) -> None:
        if self._syncing_table_selection:
            return
        selected_rows = self.platform_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        id_item = self.platform_table.item(row, 0)
        if id_item is None:
            return

        platform_id = id_item.text()
        if self.map_view.select_platform_by_id(platform_id):
            self.map_view.center_on_selected()

    def sync_table_selection(self, platform_id: str) -> None:
        row = self.platform_row_by_id.get(platform_id)
        if row is None:
            return
        self._syncing_table_selection = True
        blocker = QSignalBlocker(self.platform_table)
        try:
            self.platform_table.selectRow(row)
        finally:
            del blocker
            self._syncing_table_selection = False

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            "205_nav_ui 原型（第十二步）\n\n"
            "当前功能：\n"
            "- UAV/UGV 不同图形显示\n"
            "- 平台列表联动选中与定位\n"
            "- 数据新鲜度告警（超时灰显）\n"
            "- 下线平台自动移除（图元/轨迹/列表）\n"
            "- 超时告警与移除阈值在线可调\n"
            "- 暂停后支持单步刷新一帧\n"
            "- 支持0.5x/1.0x/2.0x回放倍速\n"
            "- 平台编号显示/隐藏\n"
            "- 跟随选中目标\n"
            "- 跟随时禁用手动拖拽\n"
            "- 鼠标点击选中高亮\n"
            "- 轨迹显示与清除\n"
            "- 坐标、速度、时间戳显示\n"
            "- 底部状态栏显示当前选中平台信息",
        )
