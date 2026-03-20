from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fake_data import FakeDataGenerator
from map_view import MapView
from data_source import PlatformDataSource
from error_plot_widget import ErrorPlotWidget
from models import PlatformState
from platform_manager import PlatformManager


class MainWindow(QMainWindow):
    """主窗口：中间地图，右侧信息栏。"""

    def __init__(self, data_source: PlatformDataSource | None = None) -> None:
        super().__init__()

        self.setWindowTitle("205_nav_ui - PySide6 原型")
        self.resize(1200, 700)

        self.data_source = data_source if data_source is not None else FakeDataGenerator()
        self.platform_manager = PlatformManager(stale_timeout_sec=0.6, remove_timeout_sec=3.0)

        self.id_label = QLabel("--")
        self.type_label = QLabel("--")
        self.x_label = QLabel("--")
        self.y_label = QLabel("--")
        self.z_label = QLabel("--")
        self.speed_label = QLabel("--")
        self.truth_error_label = QLabel("--")
        self.truth_rms_error_label = QLabel("--")
        self.timestamp_label = QLabel("--")
        self.error_plot_widget = ErrorPlotWidget()
        self.platform_row_by_id: dict[str, int] = {}
        self._syncing_table_selection = False
        self.base_timer_interval_ms = 100
        self.playback_speed = 1.0
        self.packet_loss_controls_supported = all(
            hasattr(self.data_source, name)
            for name in ("set_packet_loss_enabled", "set_packet_loss_rate")
        )

        self.map_view = MapView(on_platform_selected=self.on_platform_selected)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("未选中平台")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_update)
        self.timer.start(self._current_timer_interval_ms())

        self._init_ui()
        self.refresh_export_index()
        self._load_initial_data()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setMinimumWidth(300)

        info_group = QGroupBox("平台信息")
        form_layout = QFormLayout(info_group)
        form_layout.addRow("ID:", self.id_label)
        form_layout.addRow("类型:", self.type_label)
        form_layout.addRow("X 坐标:", self.x_label)
        form_layout.addRow("Y 坐标:", self.y_label)
        form_layout.addRow("Z 坐标:", self.z_label)
        form_layout.addRow("速度:", self.speed_label)
        form_layout.addRow("平面误差:", self.truth_error_label)
        form_layout.addRow("轨迹RMS误差:", self.truth_rms_error_label)
        form_layout.addRow("时间戳:", self.timestamp_label)

        error_group = QGroupBox("误差曲线（选中平台）")
        error_layout = QVBoxLayout(error_group)
        error_layout.addWidget(self.error_plot_widget)

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

        self.truth_checkbox = QCheckBox("显示真值点")
        self.truth_checkbox.setChecked(True)
        self.truth_checkbox.toggled.connect(self.map_view.set_show_truth_points)
        display_layout.addWidget(self.truth_checkbox)

        self.truth_track_checkbox = QCheckBox("显示真值轨迹")
        self.truth_track_checkbox.setChecked(True)
        self.truth_track_checkbox.toggled.connect(self.map_view.set_show_truth_tracks)
        display_layout.addWidget(self.truth_track_checkbox)

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
        self.stale_timeout_spin.setValue(self.platform_manager.stale_timeout_sec)
        self.stale_timeout_spin.valueChanged.connect(self.on_stale_timeout_changed)
        threshold_layout.addRow("超时告警阈值:", self.stale_timeout_spin)

        self.remove_timeout_spin = QDoubleSpinBox()
        self.remove_timeout_spin.setDecimals(1)
        self.remove_timeout_spin.setRange(self.stale_timeout_spin.value(), 60.0)
        self.remove_timeout_spin.setSingleStep(0.5)
        self.remove_timeout_spin.setSuffix(" s")
        self.remove_timeout_spin.setValue(self.platform_manager.remove_timeout_sec)
        self.remove_timeout_spin.valueChanged.connect(self.on_remove_timeout_changed)
        threshold_layout.addRow("下线移除阈值:", self.remove_timeout_spin)

        sim_group = QGroupBox("链路仿真")
        sim_layout = QFormLayout(sim_group)

        self.packet_loss_checkbox = QCheckBox("启用掉帧仿真")
        self.packet_loss_checkbox.setChecked(False)
        self.packet_loss_checkbox.setEnabled(self.packet_loss_controls_supported)
        if not self.packet_loss_controls_supported:
            self.packet_loss_checkbox.setToolTip("当前数据源不支持掉帧仿真控制")
        self.packet_loss_checkbox.toggled.connect(self.on_packet_loss_toggled)
        sim_layout.addRow(self.packet_loss_checkbox)

        self.packet_loss_rate_spin = QDoubleSpinBox()
        self.packet_loss_rate_spin.setDecimals(0)
        self.packet_loss_rate_spin.setRange(0.0, 95.0)
        self.packet_loss_rate_spin.setSingleStep(5.0)
        self.packet_loss_rate_spin.setSuffix(" %")
        self.packet_loss_rate_spin.setValue(30.0)
        self.packet_loss_rate_spin.setEnabled(False)
        self.packet_loss_rate_spin.valueChanged.connect(self.on_packet_loss_rate_changed)
        sim_layout.addRow("丢包率:", self.packet_loss_rate_spin)

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
        help_layout.addWidget(QLabel("12. 支持全局视图/定位选中/复位视图"))
        help_layout.addWidget(QLabel("13. 支持链路掉帧仿真（用于告警联调）"))
        help_layout.addWidget(QLabel("14. 平台状态统一为dataclass并集中管理"))
        help_layout.addWidget(QLabel("15. 支持真值点/真值轨迹与误差统计"))
        help_layout.addWidget(QLabel("16. 可一键导出当前态势图截图"))
        help_layout.addWidget(QLabel("17. 选中平台可查看平面误差曲线"))
        help_layout.addWidget(QLabel("18. 可导出选中平台误差CSV与曲线PNG"))
        help_layout.addWidget(QLabel("19. 左右分栏支持鼠标拖拽调宽"))
        help_layout.addWidget(QLabel("20. 导出索引支持最近文件查看与一键打开"))
        help_layout.addWidget(QLabel("21. 导出索引支持类型与时间筛选"))
        help_layout.addWidget(QLabel("22. 右侧功能按选项卡分类切换"))
        help_layout.addWidget(QLabel("23. 导出索引支持关键字搜索与路径复制"))

        export_index_group = QGroupBox("导出索引")
        export_index_layout = QVBoxLayout(export_index_group)

        export_filter_row = QHBoxLayout()
        export_filter_row.addWidget(QLabel("类型"))
        self.export_type_filter_combo = QComboBox()
        self.export_type_filter_combo.addItem("全部", "all")
        self.export_type_filter_combo.addItem("态势截图", "snapshot")
        self.export_type_filter_combo.addItem("误差CSV", "error_csv")
        self.export_type_filter_combo.addItem("误差曲线PNG", "error_plot")
        self.export_type_filter_combo.currentIndexChanged.connect(self.refresh_export_index)
        export_filter_row.addWidget(self.export_type_filter_combo)

        export_filter_row.addWidget(QLabel("时间"))
        self.export_time_filter_combo = QComboBox()
        self.export_time_filter_combo.addItem("全部", None)
        self.export_time_filter_combo.addItem("最近1小时", 60 * 60)
        self.export_time_filter_combo.addItem("最近24小时", 24 * 60 * 60)
        self.export_time_filter_combo.addItem("最近7天", 7 * 24 * 60 * 60)
        self.export_time_filter_combo.currentIndexChanged.connect(self.refresh_export_index)
        export_filter_row.addWidget(self.export_time_filter_combo)
        export_index_layout.addLayout(export_filter_row)

        export_search_row = QHBoxLayout()
        export_search_row.addWidget(QLabel("搜索"))
        self.export_keyword_edit = QLineEdit()
        self.export_keyword_edit.setPlaceholderText("按文件名关键字筛选")
        self.export_keyword_edit.setClearButtonEnabled(True)
        self.export_keyword_edit.textChanged.connect(self.refresh_export_index)
        export_search_row.addWidget(self.export_keyword_edit)
        export_index_layout.addLayout(export_search_row)

        self.export_index_table = QTableWidget(0, 3)
        self.export_index_table.setHorizontalHeaderLabels(["文件名", "类型", "时间"])
        self.export_index_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.export_index_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.export_index_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.export_index_table.setAlternatingRowColors(True)
        self.export_index_table.verticalHeader().setVisible(False)
        self.export_index_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.export_index_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.export_index_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.export_index_table.cellDoubleClicked.connect(self.on_export_index_double_clicked)
        export_index_layout.addWidget(self.export_index_table)

        export_index_button_row = QHBoxLayout()
        open_file_button = QPushButton("打开选中文件")
        open_file_button.clicked.connect(self.on_open_selected_export)
        export_index_button_row.addWidget(open_file_button)

        copy_path_button = QPushButton("复制文件路径")
        copy_path_button.clicked.connect(self.on_copy_selected_export_path)
        export_index_button_row.addWidget(copy_path_button)

        open_dir_button = QPushButton("打开导出目录")
        open_dir_button.clicked.connect(self.on_open_export_directory)
        export_index_button_row.addWidget(open_dir_button)

        refresh_export_index_button = QPushButton("刷新索引")
        refresh_export_index_button.clicked.connect(self.refresh_export_index)
        export_index_button_row.addWidget(refresh_export_index_button)
        export_index_layout.addLayout(export_index_button_row)

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

        fit_all_button = QPushButton("全局视图")
        fit_all_button.clicked.connect(self.on_fit_all_view)
        button_layout.addWidget(fit_all_button)

        focus_selected_button = QPushButton("定位选中")
        focus_selected_button.clicked.connect(self.on_focus_selected_view)
        button_layout.addWidget(focus_selected_button)

        reset_view_button = QPushButton("复位视图")
        reset_view_button.clicked.connect(self.on_reset_view)
        button_layout.addWidget(reset_view_button)

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

        export_button = QPushButton("导出截图")
        export_button.clicked.connect(self.on_export_snapshot)
        button_layout.addWidget(export_button)

        export_error_csv_button = QPushButton("导出误差CSV")
        export_error_csv_button.clicked.connect(self.on_export_error_csv)
        button_layout.addWidget(export_error_csv_button)

        export_error_plot_button = QPushButton("导出误差曲线PNG")
        export_error_plot_button.clicked.connect(self.on_export_error_plot)
        button_layout.addWidget(export_error_plot_button)

        self.right_tabs = QTabWidget()
        self.right_tabs.setDocumentMode(True)

        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        monitor_layout.setContentsMargins(6, 6, 6, 6)
        monitor_layout.addWidget(info_group)
        monitor_layout.addWidget(error_group)
        monitor_layout.addWidget(list_group)
        monitor_layout.addStretch()
        self.right_tabs.addTab(monitor_tab, "监控")

        display_tab = QWidget()
        display_layout_tab = QVBoxLayout(display_tab)
        display_layout_tab.setContentsMargins(6, 6, 6, 6)
        display_layout_tab.addWidget(display_group)
        display_layout_tab.addWidget(threshold_group)
        display_layout_tab.addWidget(sim_group)
        display_layout_tab.addStretch()
        self.right_tabs.addTab(display_tab, "显示")

        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setContentsMargins(6, 6, 6, 6)
        control_layout.addWidget(button_group)
        control_layout.addStretch()
        self.right_tabs.addTab(control_tab, "控制")

        export_tab = QWidget()
        export_layout = QVBoxLayout(export_tab)
        export_layout.setContentsMargins(6, 6, 6, 6)
        export_layout.addWidget(export_index_group)
        export_layout.addStretch()
        self.right_tabs.addTab(export_tab, "导出")

        help_tab = QWidget()
        help_tab_layout = QVBoxLayout(help_tab)
        help_tab_layout.setContentsMargins(6, 6, 6, 6)
        help_tab_layout.addWidget(help_group)
        help_tab_layout.addStretch()
        self.right_tabs.addTab(help_tab, "说明")

        right_scroll.setWidget(self.right_tabs)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.map_view)
        self.main_splitter.addWidget(right_scroll)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([900, 300])
        main_layout.addWidget(self.main_splitter)

    def _load_initial_data(self) -> None:
        initial_data = self.data_source.get_initial_data()
        removed_ids = self.platform_manager.apply_updates(initial_data)
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
        self.map_view.update_platforms(self.platform_manager.get_all_platforms())
        self.map_view.set_stale_platforms(self.platform_manager.get_stale_platform_ids())
        self.update_platform_table(self.platform_manager.get_all_platforms())
        self.map_view.fit_all_platforms()

    def on_timer_update(self) -> None:
        platform_data = self.data_source.get_next_frame()
        self._apply_frame_update(platform_data)

    def _apply_frame_update(self, platform_data: list[PlatformState], status_prefix: str = "") -> None:
        removed_ids = self.platform_manager.apply_updates(platform_data)
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
        self.map_view.update_platforms(self.platform_manager.get_all_platforms())
        self.map_view.set_stale_platforms(self.platform_manager.get_stale_platform_ids())
        self.update_platform_table(self.platform_manager.get_all_platforms())

        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix=status_prefix)
            return

        if removed_ids:
            self.clear_selected_platform_info()
            self.platform_table.clearSelection()

        stale_count = len(self.platform_manager.get_stale_platform_ids())
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

    def on_platform_selected(self, platform_info: PlatformState, status_prefix: str = "") -> None:
        self.id_label.setText(str(platform_info.id))
        self.type_label.setText(str(platform_info.type))
        self.x_label.setText(f"{platform_info.x:.2f}")
        self.y_label.setText(f"{platform_info.y:.2f}")
        self.z_label.setText(f"{platform_info.z:.2f}")
        self.speed_label.setText(f"{platform_info.speed:.2f}")
        self.timestamp_label.setText(f"{platform_info.timestamp:.2f}")

        error_metrics = self.map_view.get_platform_error_metrics(str(platform_info.id))
        if error_metrics is not None and error_metrics.get("planar_error") is not None:
            self.truth_error_label.setText(f'{float(error_metrics["planar_error"]):.2f}')
        else:
            self.truth_error_label.setText("--")
        if error_metrics is not None and error_metrics.get("rms_planar_error") is not None:
            self.truth_rms_error_label.setText(f'{float(error_metrics["rms_planar_error"]):.2f}')
        else:
            self.truth_rms_error_label.setText("--")

        selected_id = str(platform_info.id)
        self.error_plot_widget.set_series(self.map_view.get_platform_error_series(selected_id))
        stale_count = len(self.platform_manager.get_stale_platform_ids())
        selected_stale = self.platform_manager.is_platform_stale(selected_id)
        selected_state_text = "超时" if selected_stale else "正常"

        message = (
            f'当前选中: {selected_id} | '
            f'类型: {platform_info.type} | '
            f'速度: {platform_info.speed:.2f} | '
            f'状态: {selected_state_text}'
        )
        if stale_count > 0:
            message += f" | 超时平台: {stale_count}"
        if self.truth_error_label.text() != "--":
            message += f" | 平面误差: {self.truth_error_label.text()}"
        if self.truth_rms_error_label.text() != "--":
            message += f" | RMS: {self.truth_rms_error_label.text()}"
        if status_prefix:
            message = f"{status_prefix} | {message}"
        self.status_bar.showMessage(message)
        self.platform_manager.set_selected_platform(selected_id)
        self.sync_table_selection(selected_id)

    def pause_updates(self) -> None:
        self.timer.stop()
        self.status_bar.showMessage("已暂停刷新")

    def step_once(self) -> None:
        if self.timer.isActive():
            self.status_bar.showMessage("当前为自动刷新模式，请先暂停后再单步刷新")
            return
        platform_data = self.data_source.get_next_frame()
        self._apply_frame_update(platform_data, status_prefix="单步刷新完成")

    def on_follow_toggled(self, enabled: bool) -> None:
        self.map_view.set_follow_selected(enabled)
        self.follow_lock_checkbox.setEnabled(enabled)

    def on_stale_timeout_changed(self, value: float) -> None:
        self.platform_manager.set_stale_timeout(value)
        self.map_view.set_stale_platforms(self.platform_manager.get_stale_platform_ids())
        self.remove_timeout_spin.setMinimum(value)
        if self.remove_timeout_spin.value() < value:
            self.remove_timeout_spin.setValue(value)

    def on_remove_timeout_changed(self, value: float) -> None:
        removed_ids = self.platform_manager.set_remove_timeout(value)
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
            self.clear_selected_platform_info()
            self.platform_table.clearSelection()
        self.map_view.set_stale_platforms(self.platform_manager.get_stale_platform_ids())
        self.update_platform_table(self.platform_manager.get_all_platforms())

    def on_packet_loss_toggled(self, enabled: bool) -> None:
        if not self.packet_loss_controls_supported:
            self.status_bar.showMessage("当前数据源不支持掉帧仿真")
            return
        self.data_source.set_packet_loss_enabled(enabled)  # type: ignore[attr-defined]
        self.packet_loss_rate_spin.setEnabled(enabled)
        self.data_source.set_packet_loss_rate(self.packet_loss_rate_spin.value() / 100.0)  # type: ignore[attr-defined]
        if enabled:
            self.status_bar.showMessage(
                f"已启用掉帧仿真 | 丢包率: {self.packet_loss_rate_spin.value():.0f}%"
            )
        else:
            self.status_bar.showMessage("已关闭掉帧仿真")

    def on_packet_loss_rate_changed(self, value: float) -> None:
        if not self.packet_loss_controls_supported:
            return
        self.data_source.set_packet_loss_rate(value / 100.0)  # type: ignore[attr-defined]
        if self.packet_loss_checkbox.isChecked():
            self.status_bar.showMessage(f"已调整掉帧仿真丢包率: {value:.0f}%")

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

    def on_fit_all_view(self) -> None:
        if self.map_view.fit_all_platforms():
            self.status_bar.showMessage("已切换到全局视图")
        else:
            self.status_bar.showMessage("暂无平台可执行全局视图")

    def on_focus_selected_view(self) -> None:
        if self.map_view.focus_selected_platform():
            self.status_bar.showMessage("已定位到当前选中平台")
        else:
            self.status_bar.showMessage("未选中平台，无法定位")

    def on_reset_view(self) -> None:
        self.map_view.reset_view()
        self.status_bar.showMessage("已复位视图缩放")

    def resume_updates(self) -> None:
        self.timer.start(self._current_timer_interval_ms())
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix="已恢复自动刷新")
        else:
            self.status_bar.showMessage("未选中平台，已恢复刷新")

    def on_export_snapshot(self) -> None:
        export_dir = Path.cwd() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"nav_snapshot_{timestamp}.png"
        if self.map_view.export_snapshot(str(file_path)):
            self.refresh_export_index(focus_path=file_path)
            self.status_bar.showMessage(f"截图已导出: {file_path}")
        else:
            self.status_bar.showMessage("截图导出失败")

    def on_export_error_csv(self) -> None:
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is None:
            self.status_bar.showMessage("未选中平台，无法导出误差CSV")
            return

        platform_id = str(selected_info.id)
        series = self.map_view.get_platform_error_series(platform_id)
        if not series:
            self.status_bar.showMessage("当前平台暂无误差数据")
            return

        export_dir = Path.cwd() / "exports" / "errors"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"{platform_id}_planar_error_{timestamp}.csv"
        try:
            with file_path.open("w", encoding="utf-8") as file:
                file.write("index,planar_error\n")
                for index, value in enumerate(series):
                    file.write(f"{index},{value:.6f}\n")
        except OSError:
            self.status_bar.showMessage("误差CSV导出失败")
            return

        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"误差CSV已导出: {file_path}")

    def on_export_error_plot(self) -> None:
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is None:
            self.status_bar.showMessage("未选中平台，无法导出误差曲线图")
            return

        platform_id = str(selected_info.id)
        series = self.map_view.get_platform_error_series(platform_id)
        if len(series) < 2:
            self.status_bar.showMessage("误差数据不足，无法导出曲线图")
            return

        export_dir = Path.cwd() / "exports" / "errors"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"{platform_id}_planar_error_{timestamp}.png"
        if self.error_plot_widget.grab().save(str(file_path), "PNG"):
            self.refresh_export_index(focus_path=file_path)
            self.status_bar.showMessage(f"误差曲线图已导出: {file_path}")
        else:
            self.status_bar.showMessage("误差曲线图导出失败")

    def refresh_export_index(
        self,
        _signal_value: object | None = None,
        focus_path: Path | None = None,
    ) -> None:
        export_root = Path.cwd() / "exports"
        entries: list[tuple[Path, float]] = []
        selected_type = self.export_type_filter_combo.currentData()
        selected_time_window_sec = self.export_time_filter_combo.currentData()
        keyword = self.export_keyword_edit.text().strip().lower()
        now_ts = datetime.now().timestamp()

        if export_root.exists():
            for path in export_root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if (
                    selected_time_window_sec is not None
                    and now_ts - mtime > float(selected_time_window_sec)
                ):
                    continue
                export_type_key = self._infer_export_type_key(path)
                if selected_type not in (None, "all") and export_type_key != selected_type:
                    continue
                if keyword and keyword not in path.name.lower():
                    continue
                entries.append((path, mtime))

        entries.sort(key=lambda item: item[1], reverse=True)
        entries = entries[:80]

        focus_row: int | None = None
        blocker = QSignalBlocker(self.export_index_table)
        try:
            self.export_index_table.setRowCount(0)
            for row, (path, mtime) in enumerate(entries):
                if focus_path is not None and path == focus_path:
                    focus_row = row
                self.export_index_table.insertRow(row)

                name_item = QTableWidgetItem(path.name)
                name_item.setData(Qt.ItemDataRole.UserRole, str(path))
                name_item.setToolTip(str(path))
                self.export_index_table.setItem(row, 0, name_item)

                type_item = QTableWidgetItem(self._infer_export_type_label(path))
                self.export_index_table.setItem(row, 1, type_item)

                time_item = QTableWidgetItem(
                    datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                )
                self.export_index_table.setItem(row, 2, time_item)
        finally:
            del blocker

        if self.export_index_table.rowCount() == 0:
            return
        if focus_row is None:
            focus_row = 0
        self.export_index_table.selectRow(focus_row)

    def _infer_export_type_key(self, path: Path) -> str:
        file_name = path.name
        suffix = path.suffix.lower()
        if file_name.startswith("nav_snapshot_") and suffix == ".png":
            return "snapshot"
        if suffix == ".csv":
            return "error_csv"
        if suffix == ".png" and "_planar_error_" in file_name:
            return "error_plot"
        return "other"

    def _infer_export_type_label(self, path: Path) -> str:
        type_key = self._infer_export_type_key(path)
        if type_key == "snapshot":
            return "态势截图"
        if type_key == "error_csv":
            return "误差CSV"
        if type_key == "error_plot":
            return "误差曲线PNG"
        return "其他文件"

    def on_export_index_double_clicked(self, row: int, _col: int) -> None:
        self.export_index_table.selectRow(row)
        self.on_open_selected_export()

    def _get_selected_export_path(self) -> Path | None:
        selected_rows = self.export_index_table.selectionModel().selectedRows()
        if not selected_rows:
            self.status_bar.showMessage("未选中导出文件")
            return None

        row = selected_rows[0].row()
        name_item = self.export_index_table.item(row, 0)
        if name_item is None:
            self.status_bar.showMessage("导出文件信息无效")
            return None

        file_path_raw = name_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(file_path_raw, str):
            self.status_bar.showMessage("导出文件路径无效")
            return None

        return Path(file_path_raw)

    def on_open_selected_export(self) -> None:
        file_path = self._get_selected_export_path()
        if file_path is None:
            return
        if not file_path.exists():
            self.refresh_export_index()
            self.status_bar.showMessage("文件不存在，已刷新导出索引")
            return

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path))):
            self.status_bar.showMessage(f"已打开文件: {file_path}")
            return
        self.status_bar.showMessage("打开文件失败")

    def on_copy_selected_export_path(self) -> None:
        file_path = self._get_selected_export_path()
        if file_path is None:
            return
        QApplication.clipboard().setText(str(file_path))
        self.status_bar.showMessage(f"已复制路径: {file_path}")

    def on_open_export_directory(self) -> None:
        export_dir = Path.cwd() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(export_dir))):
            self.status_bar.showMessage(f"已打开导出目录: {export_dir}")
            return
        self.status_bar.showMessage("打开导出目录失败")

    def _current_timer_interval_ms(self) -> int:
        speed = max(self.playback_speed, 0.1)
        return max(10, int(self.base_timer_interval_ms / speed))

    def update_platform_table(self, platform_list: list[PlatformState]) -> None:
        incoming_ids = {str(platform_info.id) for platform_info in platform_list}
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
            platform_id = str(platform_info.id)
            row = self.platform_row_by_id.get(platform_id)
            if row is None:
                row = self.platform_table.rowCount()
                self.platform_table.insertRow(row)
                self.platform_row_by_id[platform_id] = row
                self._set_table_text(row, 0, platform_id)
                self._set_table_text(row, 1, str(platform_info.type))

            self._set_table_text(row, 2, f"{platform_info.speed:.2f}")
            self._set_table_text(row, 3, f"{platform_info.timestamp:.2f}")
            is_stale = self.platform_manager.is_platform_stale(platform_id)
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
        self.truth_error_label.setText("--")
        self.truth_rms_error_label.setText("--")
        self.timestamp_label.setText("--")
        self.error_plot_widget.clear()

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
            self.platform_manager.set_selected_platform(platform_id)
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
            "205_nav_ui 原型（第二十四步）\n\n"
            "当前功能：\n"
            "- UAV/UGV 不同图形显示\n"
            "- 平台状态统一dataclass（含在线与真值预留字段）\n"
            "- PlatformManager 集中管理状态/告警/移除\n"
            "- 数据源接口抽象，可替换接入\n"
            "- 真值点/真值轨迹显示与误差可视化（当前+RMS）\n"
            "- 选中平台误差曲线面板\n"
            "- 误差CSV与误差曲线PNG导出\n"
            "- 导出索引面板（筛选 + 关键字搜索 + 一键打开）\n"
            "- 一键复制选中导出文件路径\n"
            "- 平台列表联动选中与定位\n"
            "- 数据新鲜度告警（超时灰显）\n"
            "- 下线平台自动移除（图元/轨迹/列表）\n"
            "- 超时告警与移除阈值在线可调\n"
            "- 暂停后支持单步刷新一帧\n"
            "- 支持0.5x/1.0x/2.0x回放倍速\n"
            "- 支持全局视图/定位选中/复位视图\n"
            "- 支持链路掉帧仿真（告警联调）\n"
            "- 支持一键导出当前态势图截图\n"
            "- 左右分栏支持拖拽调宽\n"
            "- 右侧功能按选项卡分类切换\n"
            "- 平台编号显示/隐藏\n"
            "- 跟随选中目标\n"
            "- 跟随时禁用手动拖拽\n"
            "- 鼠标点击选中高亮\n"
            "- 轨迹显示与清除\n"
            "- 坐标、速度、时间戳显示\n"
            "- 底部状态栏显示当前选中平台信息",
        )
