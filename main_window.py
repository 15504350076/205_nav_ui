import csv
import json
import time
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
    QFileDialog,
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
    QSlider,
    QSpinBox,
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
from data_adapter import DataAdapter, ReplayDataAdapter
from data_source import PlatformDataSource
from live_data_source import LiveDataSourceAdapter
from replay_data_source import ReplayDataSource
from error_plot_widget import ErrorPlotWidget
from platform_state import PlatformState
from platform_manager import PlatformManager
from alert_rules import (
    AlertThresholdConfig,
    AlertThresholdConfigFileMeta,
    AlertThresholdPreset,
    diff_alert_threshold_configs,
    load_alert_threshold_config_with_meta,
    save_alert_threshold_config,
    get_default_alert_threshold_presets,
    resolve_error_threshold,
)
from alert_history import (
    AlertRecord,
)
from alert_center import AlertRow, should_show_alert, summarize_alert_rows
from evaluation_service import EvaluationService
from alert_history_service import AlertHistoryService
from alert_runtime import RuntimeAlertEngine
from ui_state import UiState, load_ui_state, save_ui_state


class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格单元格。"""

    def __init__(self, text: str, numeric_value: float) -> None:
        super().__init__(text)
        self.numeric_value = float(numeric_value)

    def set_numeric(self, text: str, numeric_value: float) -> None:
        self.numeric_value = float(numeric_value)
        self.setText(text)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self.numeric_value < other.numeric_value
        try:
            return self.numeric_value < float(other.text())
        except (TypeError, ValueError):
            return super().__lt__(other)


class MainWindow(QMainWindow):
    """主窗口：中间地图，右侧信息栏。"""

    def __init__(self, data_source: PlatformDataSource | DataAdapter | None = None) -> None:
        super().__init__()

        self.setWindowTitle("205_nav_ui - PySide6 原型")
        self.resize(1200, 700)

        if data_source is None:
            live_source: PlatformDataSource | None = FakeDataGenerator()
            live_adapter = LiveDataSourceAdapter(live_source)
            self.data_source: ReplayDataAdapter = ReplayDataSource(live_adapter)
        elif all(
            hasattr(data_source, attr)
            for attr in (
                "is_recording",
                "is_replay_mode",
                "connect",
                "disconnect",
                "poll",
                "next_frame",
            )
        ):
            live_source = None
            self.data_source = data_source  # type: ignore[assignment]
        elif all(
            hasattr(data_source, attr)
            for attr in ("connect", "disconnect", "poll", "next_frame", "get_status")
        ):
            live_source = None
            self.data_source = ReplayDataSource(data_source)
        else:
            live_source = data_source  # type: ignore[assignment]
            live_adapter = LiveDataSourceAdapter(live_source)
            self.data_source = ReplayDataSource(live_adapter)
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
        self.pinned_export_paths: set[str] = set()
        self._syncing_replay_slider = False
        self.alert_max_rows = 400
        self.runtime_alert_engine = RuntimeAlertEngine()
        self.evaluation_service = EvaluationService(history_duration_sec=12.0)
        self.alert_id_threshold_overrides: dict[str, float] = {}
        self.last_alert_threshold_import_meta: AlertThresholdConfigFileMeta | None = None
        self._is_restoring_alert_history = False
        self.alert_history_service = AlertHistoryService(Path.cwd() / "exports" / "alerts")
        self.alert_threshold_presets: list[AlertThresholdPreset] = (
            get_default_alert_threshold_presets()
        )
        self.base_timer_interval_ms = 100
        self.playback_speed = 1.0
        self._is_loading_ui_state = False
        self._ui_state_ready = False
        self._ui_tick_count = 0
        self._ui_tick_window_start_sec = time.monotonic()
        self._ui_tick_rate_hz = 0.0
        self.packet_loss_controls_supported = all(
            live_source is not None and hasattr(live_source, name)
            for name in ("set_packet_loss_enabled", "set_packet_loss_rate")
        )

        self.map_view = MapView(on_platform_selected=self.on_platform_selected)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("未选中平台")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_update)
        self.timer.start(self._current_timer_interval_ms())

        self._load_pinned_exports()
        self._init_ui()
        self._load_ui_state()
        self._ui_state_ready = True
        self.refresh_export_index()
        self._load_initial_data()
        self._auto_restore_alert_history()

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

        self.platform_summary_label = QLabel("统计: 可见0/总0 | UAV 0 | UGV 0 | 正常 0 | 超时 0")
        list_layout.addWidget(self.platform_summary_label)

        platform_filter_row = QHBoxLayout()
        platform_filter_row.addWidget(QLabel("类型"))
        self.platform_type_filter_combo = QComboBox()
        self.platform_type_filter_combo.addItem("全部", "all")
        self.platform_type_filter_combo.addItem("UAV", "UAV")
        self.platform_type_filter_combo.addItem("UGV", "UGV")
        self.platform_type_filter_combo.currentIndexChanged.connect(self.apply_platform_table_filters)
        platform_filter_row.addWidget(self.platform_type_filter_combo)

        platform_filter_row.addWidget(QLabel("状态"))
        self.platform_status_filter_combo = QComboBox()
        self.platform_status_filter_combo.addItem("全部", "all")
        self.platform_status_filter_combo.addItem("正常", "正常")
        self.platform_status_filter_combo.addItem("超时", "超时")
        self.platform_status_filter_combo.currentIndexChanged.connect(self.apply_platform_table_filters)
        platform_filter_row.addWidget(self.platform_status_filter_combo)
        list_layout.addLayout(platform_filter_row)

        platform_search_row = QHBoxLayout()
        platform_search_row.addWidget(QLabel("搜索"))
        self.platform_keyword_edit = QLineEdit()
        self.platform_keyword_edit.setPlaceholderText("按ID筛选平台")
        self.platform_keyword_edit.setClearButtonEnabled(True)
        self.platform_keyword_edit.textChanged.connect(self.apply_platform_table_filters)
        platform_search_row.addWidget(self.platform_keyword_edit)

        reset_platform_filter_button = QPushButton("重置筛选")
        reset_platform_filter_button.clicked.connect(self.on_reset_platform_filters)
        platform_search_row.addWidget(reset_platform_filter_button)
        list_layout.addLayout(platform_search_row)

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
        self.platform_table.horizontalHeader().setSortIndicatorShown(True)
        self.platform_table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.platform_table.horizontalHeader().sortIndicatorChanged.connect(
            self.on_platform_table_sort_changed
        )
        self.platform_table.setSortingEnabled(True)
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

        self.velocity_vector_checkbox = QCheckBox("显示速度矢量")
        self.velocity_vector_checkbox.setChecked(False)
        self.velocity_vector_checkbox.toggled.connect(self.map_view.set_show_velocity_vectors)
        display_layout.addWidget(self.velocity_vector_checkbox)

        track_duration_row = QHBoxLayout()
        track_duration_row.addWidget(QLabel("轨迹时间窗(s)"))
        self.track_duration_spin = QDoubleSpinBox()
        self.track_duration_spin.setDecimals(1)
        self.track_duration_spin.setRange(1.0, 120.0)
        self.track_duration_spin.setSingleStep(1.0)
        self.track_duration_spin.setValue(self.map_view.track_duration_sec)
        self.track_duration_spin.valueChanged.connect(self.on_track_duration_changed)
        track_duration_row.addWidget(self.track_duration_spin)
        display_layout.addLayout(track_duration_row)

        clear_track_button = QPushButton("清除轨迹")
        clear_track_button.clicked.connect(self.on_clear_tracks)
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
        help_layout.addWidget(QLabel("24. 支持导出文件置顶与排序"))
        help_layout.addWidget(QLabel("25. 支持多选导出文件批量打开与清理"))
        help_layout.addWidget(QLabel("26. 支持录制实时数据并加载文件回放"))
        help_layout.addWidget(QLabel("27. 支持告警中心与告警确认/清理"))
        help_layout.addWidget(QLabel("28. 轨迹时间窗可在线调节"))
        help_layout.addWidget(QLabel("29. 回放支持时间轴拖动定位"))
        help_layout.addWidget(QLabel("30. 告警中心支持级别/状态/关键字筛选"))
        help_layout.addWidget(QLabel("31. 告警列表支持CSV导出"))
        help_layout.addWidget(QLabel("32. 告警中心支持来源分组统计与统计导出"))
        help_layout.addWidget(QLabel("33. 双击告警可快速定位到对应平台"))
        help_layout.addWidget(QLabel("34. 平台列表支持类型/状态/关键字筛选"))
        help_layout.addWidget(QLabel("35. 双击告警统计来源可快速筛选告警"))
        help_layout.addWidget(QLabel("36. 平台列表支持点击表头排序"))
        help_layout.addWidget(QLabel("37. 可开启速度矢量显示方向与速度大小"))
        help_layout.addWidget(QLabel("38. 平台筛选条件可在重启后自动恢复"))
        help_layout.addWidget(QLabel("39. 告警误差阈值支持按UAV/UGV类型分别配置"))
        help_layout.addWidget(QLabel("40. 告警误差阈值支持按平台ID覆盖"))
        help_layout.addWidget(QLabel("41. 告警阈值支持预设方案一键切换"))
        help_layout.addWidget(QLabel("42. 告警阈值配置支持JSON导入/导出"))
        help_layout.addWidget(QLabel("43. 告警阈值生效来源可实时预览"))
        help_layout.addWidget(QLabel("44. 导出索引支持筛选告警配置JSON"))
        help_layout.addWidget(QLabel("45. 可查看导入阈值配置的版本与来源信息"))
        help_layout.addWidget(QLabel("46. 可对比当前配置与参考预设差异"))
        help_layout.addWidget(QLabel("47. 阈值JSON支持旧格式兼容导入"))
        help_layout.addWidget(QLabel("48. 支持按规则开关控制告警触发"))
        help_layout.addWidget(QLabel("49. 误差告警支持间隔与连续次数升级策略"))
        help_layout.addWidget(QLabel("50. 告警支持一键确认可见未确认与清空可见"))
        help_layout.addWidget(QLabel("51. 告警记录支持JSON导出"))
        help_layout.addWidget(QLabel("52. 告警支持时间窗筛选"))
        help_layout.addWidget(QLabel("53. 告警历史支持保存/加载与JSONL导出"))
        help_layout.addWidget(QLabel("54. 告警历史支持按保留天数清理"))
        help_layout.addWidget(QLabel("55. 可设置启动自动恢复告警历史"))

        export_index_group = QGroupBox("导出索引")
        export_index_layout = QVBoxLayout(export_index_group)

        export_filter_row = QHBoxLayout()
        export_filter_row.addWidget(QLabel("类型"))
        self.export_type_filter_combo = QComboBox()
        self.export_type_filter_combo.addItem("全部", "all")
        self.export_type_filter_combo.addItem("态势截图", "snapshot")
        self.export_type_filter_combo.addItem("误差CSV", "error_csv")
        self.export_type_filter_combo.addItem("误差曲线PNG", "error_plot")
        self.export_type_filter_combo.addItem("告警配置JSON", "alert_cfg")
        self.export_type_filter_combo.addItem("告警记录JSON", "alerts_json")
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

        export_filter_row.addWidget(QLabel("排序"))
        self.export_sort_combo = QComboBox()
        self.export_sort_combo.addItem("时间新->旧", "mtime_desc")
        self.export_sort_combo.addItem("时间旧->新", "mtime_asc")
        self.export_sort_combo.addItem("名称A->Z", "name_asc")
        self.export_sort_combo.addItem("名称Z->A", "name_desc")
        self.export_sort_combo.currentIndexChanged.connect(self.refresh_export_index)
        export_filter_row.addWidget(self.export_sort_combo)
        export_index_layout.addLayout(export_filter_row)

        export_search_row = QHBoxLayout()
        export_search_row.addWidget(QLabel("搜索"))
        self.export_keyword_edit = QLineEdit()
        self.export_keyword_edit.setPlaceholderText("按文件名关键字筛选")
        self.export_keyword_edit.setClearButtonEnabled(True)
        self.export_keyword_edit.textChanged.connect(self.refresh_export_index)
        export_search_row.addWidget(self.export_keyword_edit)
        export_index_layout.addLayout(export_search_row)

        self.export_index_table = QTableWidget(0, 4)
        self.export_index_table.setHorizontalHeaderLabels(["置顶", "文件名", "类型", "时间"])
        self.export_index_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.export_index_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.export_index_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.export_index_table.setAlternatingRowColors(True)
        self.export_index_table.verticalHeader().setVisible(False)
        self.export_index_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.export_index_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.export_index_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.export_index_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.export_index_table.cellDoubleClicked.connect(self.on_export_index_double_clicked)
        export_index_layout.addWidget(self.export_index_table)

        export_index_button_row = QHBoxLayout()
        open_file_button = QPushButton("打开选中文件")
        open_file_button.clicked.connect(self.on_open_selected_export)
        export_index_button_row.addWidget(open_file_button)

        copy_path_button = QPushButton("复制文件路径")
        copy_path_button.clicked.connect(self.on_copy_selected_export_path)
        export_index_button_row.addWidget(copy_path_button)

        pin_button = QPushButton("置顶选中文件")
        pin_button.clicked.connect(self.on_pin_selected_export)
        export_index_button_row.addWidget(pin_button)

        unpin_button = QPushButton("取消置顶")
        unpin_button.clicked.connect(self.on_unpin_selected_export)
        export_index_button_row.addWidget(unpin_button)

        open_dir_button = QPushButton("打开导出目录")
        open_dir_button.clicked.connect(self.on_open_export_directory)
        export_index_button_row.addWidget(open_dir_button)

        refresh_export_index_button = QPushButton("刷新索引")
        refresh_export_index_button.clicked.connect(self.refresh_export_index)
        export_index_button_row.addWidget(refresh_export_index_button)
        export_index_layout.addLayout(export_index_button_row)

        export_batch_button_row = QHBoxLayout()
        select_all_visible_button = QPushButton("全选可见")
        select_all_visible_button.clicked.connect(self.on_select_all_visible_exports)
        export_batch_button_row.addWidget(select_all_visible_button)

        open_batch_button = QPushButton("批量打开")
        open_batch_button.clicked.connect(self.on_open_selected_exports_batch)
        export_batch_button_row.addWidget(open_batch_button)

        cleanup_batch_button = QPushButton("批量清理")
        cleanup_batch_button.clicked.connect(self.on_cleanup_selected_exports)
        export_batch_button_row.addWidget(cleanup_batch_button)
        export_index_layout.addLayout(export_batch_button_row)

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

        replay_group = QGroupBox("录制与回放")
        replay_layout = QVBoxLayout(replay_group)
        self.replay_status_label = QLabel("模式: 实时")
        replay_layout.addWidget(self.replay_status_label)
        self.source_status_label = QLabel("数据源: --")
        replay_layout.addWidget(self.source_status_label)

        self.replay_file_label = QLabel("文件: --")
        replay_layout.addWidget(self.replay_file_label)

        self.replay_frame_label = QLabel("帧: --/--")
        replay_layout.addWidget(self.replay_frame_label)

        self.replay_slider = QSlider(Qt.Orientation.Horizontal)
        self.replay_slider.setEnabled(False)
        self.replay_slider.setMinimum(0)
        self.replay_slider.setMaximum(0)
        self.replay_slider.valueChanged.connect(self.on_replay_slider_changed)
        replay_layout.addWidget(self.replay_slider)

        start_record_button = QPushButton("开始录制")
        start_record_button.clicked.connect(self.on_start_recording)
        replay_layout.addWidget(start_record_button)

        stop_record_button = QPushButton("停止并保存录制")
        stop_record_button.clicked.connect(self.on_stop_recording_and_save)
        replay_layout.addWidget(stop_record_button)

        load_replay_button = QPushButton("加载回放文件")
        load_replay_button.clicked.connect(self.on_load_replay_file)
        replay_layout.addWidget(load_replay_button)

        replay_prev_button = QPushButton("回放上一帧")
        replay_prev_button.clicked.connect(self.on_replay_prev_frame)
        replay_layout.addWidget(replay_prev_button)

        replay_next_button = QPushButton("回放下一帧")
        replay_next_button.clicked.connect(self.on_replay_next_frame)
        replay_layout.addWidget(replay_next_button)

        exit_replay_button = QPushButton("退出回放模式")
        exit_replay_button.clicked.connect(self.on_exit_replay_mode)
        replay_layout.addWidget(exit_replay_button)

        alert_group = QGroupBox("告警中心")
        alert_layout = QVBoxLayout(alert_group)

        alert_rule_row_top = QHBoxLayout()
        self.alert_trigger_enabled_checkbox = QCheckBox("启用告警触发")
        self.alert_trigger_enabled_checkbox.setChecked(True)
        self.alert_trigger_enabled_checkbox.toggled.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_top.addWidget(self.alert_trigger_enabled_checkbox)

        self.alert_enable_planar_error_checkbox = QCheckBox("误差告警")
        self.alert_enable_planar_error_checkbox.setChecked(True)
        self.alert_enable_planar_error_checkbox.toggled.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_top.addWidget(self.alert_enable_planar_error_checkbox)

        self.alert_enable_stale_checkbox = QCheckBox("超时告警")
        self.alert_enable_stale_checkbox.setChecked(True)
        self.alert_enable_stale_checkbox.toggled.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_top.addWidget(self.alert_enable_stale_checkbox)

        self.alert_enable_recover_checkbox = QCheckBox("恢复告警")
        self.alert_enable_recover_checkbox.setChecked(True)
        self.alert_enable_recover_checkbox.toggled.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_top.addWidget(self.alert_enable_recover_checkbox)

        self.alert_enable_offline_checkbox = QCheckBox("下线告警")
        self.alert_enable_offline_checkbox.setChecked(True)
        self.alert_enable_offline_checkbox.toggled.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_top.addWidget(self.alert_enable_offline_checkbox)
        alert_layout.addLayout(alert_rule_row_top)

        alert_rule_row_bottom = QHBoxLayout()
        alert_rule_row_bottom.addWidget(QLabel("误差告警间隔(s)"))
        self.alert_error_cooldown_spin = QDoubleSpinBox()
        self.alert_error_cooldown_spin.setDecimals(1)
        self.alert_error_cooldown_spin.setRange(0.0, 30.0)
        self.alert_error_cooldown_spin.setSingleStep(0.1)
        self.alert_error_cooldown_spin.setValue(1.5)
        self.alert_error_cooldown_spin.valueChanged.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_bottom.addWidget(self.alert_error_cooldown_spin)

        alert_rule_row_bottom.addWidget(QLabel("误差升级阈值(次)"))
        self.alert_error_escalate_count_spin = QSpinBox()
        self.alert_error_escalate_count_spin.setRange(1, 20)
        self.alert_error_escalate_count_spin.setValue(3)
        self.alert_error_escalate_count_spin.valueChanged.connect(self.on_alert_rule_controls_changed)
        alert_rule_row_bottom.addWidget(self.alert_error_escalate_count_spin)
        alert_layout.addLayout(alert_rule_row_bottom)
        alert_threshold_row = QHBoxLayout()
        alert_threshold_row.addWidget(QLabel("统一误差阈值(m)"))
        self.alert_error_threshold_spin = QDoubleSpinBox()
        self.alert_error_threshold_spin.setDecimals(1)
        self.alert_error_threshold_spin.setRange(0.1, 50.0)
        self.alert_error_threshold_spin.setSingleStep(0.5)
        self.alert_error_threshold_spin.setValue(4.0)
        self.alert_error_threshold_spin.valueChanged.connect(self.on_alert_threshold_value_changed)
        alert_threshold_row.addWidget(self.alert_error_threshold_spin)
        alert_layout.addLayout(alert_threshold_row)

        alert_type_threshold_row = QHBoxLayout()
        self.alert_use_type_threshold_checkbox = QCheckBox("按类型阈值")
        self.alert_use_type_threshold_checkbox.setChecked(False)
        self.alert_use_type_threshold_checkbox.toggled.connect(self.on_alert_threshold_mode_toggled)
        alert_type_threshold_row.addWidget(self.alert_use_type_threshold_checkbox)

        alert_type_threshold_row.addWidget(QLabel("UAV"))
        self.alert_error_threshold_uav_spin = QDoubleSpinBox()
        self.alert_error_threshold_uav_spin.setDecimals(1)
        self.alert_error_threshold_uav_spin.setRange(0.1, 50.0)
        self.alert_error_threshold_uav_spin.setSingleStep(0.5)
        self.alert_error_threshold_uav_spin.setValue(4.0)
        self.alert_error_threshold_uav_spin.setEnabled(False)
        self.alert_error_threshold_uav_spin.valueChanged.connect(self.on_alert_threshold_value_changed)
        alert_type_threshold_row.addWidget(self.alert_error_threshold_uav_spin)

        alert_type_threshold_row.addWidget(QLabel("UGV"))
        self.alert_error_threshold_ugv_spin = QDoubleSpinBox()
        self.alert_error_threshold_ugv_spin.setDecimals(1)
        self.alert_error_threshold_ugv_spin.setRange(0.1, 50.0)
        self.alert_error_threshold_ugv_spin.setSingleStep(0.5)
        self.alert_error_threshold_ugv_spin.setValue(4.0)
        self.alert_error_threshold_ugv_spin.setEnabled(False)
        self.alert_error_threshold_ugv_spin.valueChanged.connect(self.on_alert_threshold_value_changed)
        alert_type_threshold_row.addWidget(self.alert_error_threshold_ugv_spin)
        alert_layout.addLayout(alert_type_threshold_row)

        alert_preset_row = QHBoxLayout()
        alert_preset_row.addWidget(QLabel("阈值预设"))
        self.alert_threshold_preset_combo = QComboBox()
        for preset in self.alert_threshold_presets:
            self.alert_threshold_preset_combo.addItem(preset.label, preset.key)
        self.alert_threshold_preset_combo.currentIndexChanged.connect(
            self.on_alert_threshold_preset_changed
        )
        alert_preset_row.addWidget(self.alert_threshold_preset_combo)

        apply_alert_preset_button = QPushButton("应用预设")
        apply_alert_preset_button.clicked.connect(self.on_apply_alert_threshold_preset)
        alert_preset_row.addWidget(apply_alert_preset_button)

        export_alert_preset_button = QPushButton("导出JSON")
        export_alert_preset_button.clicked.connect(self.on_export_alert_threshold_config_json)
        alert_preset_row.addWidget(export_alert_preset_button)

        import_alert_preset_button = QPushButton("导入JSON")
        import_alert_preset_button.clicked.connect(self.on_import_alert_threshold_config_json)
        alert_preset_row.addWidget(import_alert_preset_button)

        reset_balanced_preset_button = QPushButton("恢复均衡预设")
        reset_balanced_preset_button.clicked.connect(self.on_reset_alert_threshold_to_balanced)
        alert_preset_row.addWidget(reset_balanced_preset_button)
        alert_layout.addLayout(alert_preset_row)

        self.alert_threshold_preset_desc_label = QLabel("")
        self.alert_threshold_preset_desc_label.setWordWrap(True)
        alert_layout.addWidget(self.alert_threshold_preset_desc_label)

        alert_id_threshold_row = QHBoxLayout()
        self.alert_use_id_threshold_checkbox = QCheckBox("按平台ID阈值覆盖")
        self.alert_use_id_threshold_checkbox.setChecked(False)
        self.alert_use_id_threshold_checkbox.toggled.connect(self.on_alert_id_threshold_mode_toggled)
        alert_id_threshold_row.addWidget(self.alert_use_id_threshold_checkbox)
        alert_layout.addLayout(alert_id_threshold_row)

        alert_id_threshold_editor_row = QHBoxLayout()
        alert_id_threshold_editor_row.addWidget(QLabel("平台ID"))
        self.alert_id_threshold_id_edit = QLineEdit()
        self.alert_id_threshold_id_edit.setPlaceholderText("例如 UAV1")
        self.alert_id_threshold_id_edit.setClearButtonEnabled(True)
        self.alert_id_threshold_id_edit.setEnabled(False)
        alert_id_threshold_editor_row.addWidget(self.alert_id_threshold_id_edit)

        alert_id_threshold_editor_row.addWidget(QLabel("阈值(m)"))
        self.alert_id_threshold_value_spin = QDoubleSpinBox()
        self.alert_id_threshold_value_spin.setDecimals(1)
        self.alert_id_threshold_value_spin.setRange(0.1, 50.0)
        self.alert_id_threshold_value_spin.setSingleStep(0.5)
        self.alert_id_threshold_value_spin.setValue(4.0)
        self.alert_id_threshold_value_spin.setEnabled(False)
        alert_id_threshold_editor_row.addWidget(self.alert_id_threshold_value_spin)

        set_alert_id_threshold_button = QPushButton("设置/更新")
        set_alert_id_threshold_button.clicked.connect(self.on_set_alert_id_threshold)
        set_alert_id_threshold_button.setEnabled(False)
        self.set_alert_id_threshold_button = set_alert_id_threshold_button
        alert_id_threshold_editor_row.addWidget(set_alert_id_threshold_button)

        remove_alert_id_threshold_button = QPushButton("删除选中")
        remove_alert_id_threshold_button.clicked.connect(self.on_remove_selected_alert_id_threshold)
        remove_alert_id_threshold_button.setEnabled(False)
        self.remove_alert_id_threshold_button = remove_alert_id_threshold_button
        alert_id_threshold_editor_row.addWidget(remove_alert_id_threshold_button)
        alert_layout.addLayout(alert_id_threshold_editor_row)

        self.alert_id_threshold_table = QTableWidget(0, 2)
        self.alert_id_threshold_table.setHorizontalHeaderLabels(["平台ID", "阈值(m)"])
        self.alert_id_threshold_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.alert_id_threshold_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.alert_id_threshold_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alert_id_threshold_table.verticalHeader().setVisible(False)
        self.alert_id_threshold_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.alert_id_threshold_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_id_threshold_table.cellClicked.connect(self.on_alert_id_threshold_row_clicked)
        self.alert_id_threshold_table.setVisible(False)
        alert_layout.addWidget(self.alert_id_threshold_table)

        alert_id_threshold_button_row = QHBoxLayout()
        apply_selected_platform_threshold_button = QPushButton("填入当前选中平台")
        apply_selected_platform_threshold_button.clicked.connect(self.on_fill_selected_platform_id_for_threshold)
        apply_selected_platform_threshold_button.setEnabled(False)
        self.apply_selected_platform_threshold_button = apply_selected_platform_threshold_button
        alert_id_threshold_button_row.addWidget(apply_selected_platform_threshold_button)

        clear_alert_id_threshold_button = QPushButton("清空ID阈值")
        clear_alert_id_threshold_button.clicked.connect(self.on_clear_alert_id_thresholds)
        clear_alert_id_threshold_button.setEnabled(False)
        self.clear_alert_id_threshold_button = clear_alert_id_threshold_button
        alert_id_threshold_button_row.addWidget(clear_alert_id_threshold_button)
        alert_layout.addLayout(alert_id_threshold_button_row)

        self.alert_threshold_preview_label = QLabel("生效阈值预览: 0个平台")
        alert_layout.addWidget(self.alert_threshold_preview_label)

        self.alert_threshold_preview_table = QTableWidget(0, 3)
        self.alert_threshold_preview_table.setHorizontalHeaderLabels(["平台ID", "生效阈值(m)", "来源"])
        self.alert_threshold_preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.alert_threshold_preview_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.alert_threshold_preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alert_threshold_preview_table.verticalHeader().setVisible(False)
        self.alert_threshold_preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_threshold_preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_threshold_preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.alert_threshold_preview_table.cellDoubleClicked.connect(
            self.on_alert_threshold_preview_row_double_clicked
        )
        alert_layout.addWidget(self.alert_threshold_preview_table)

        self.alert_threshold_import_meta_label = QLabel("阈值配置文件: 未导入")
        alert_layout.addWidget(self.alert_threshold_import_meta_label)

        self.alert_threshold_diff_label = QLabel("与参考预设差异: 0项")
        alert_layout.addWidget(self.alert_threshold_diff_label)

        self.alert_threshold_diff_table = QTableWidget(0, 3)
        self.alert_threshold_diff_table.setHorizontalHeaderLabels(["字段", "当前值", "参考值"])
        self.alert_threshold_diff_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.alert_threshold_diff_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.alert_threshold_diff_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alert_threshold_diff_table.verticalHeader().setVisible(False)
        self.alert_threshold_diff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_threshold_diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_threshold_diff_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        alert_layout.addWidget(self.alert_threshold_diff_table)

        alert_filter_row = QHBoxLayout()
        alert_filter_row.addWidget(QLabel("级别"))
        self.alert_level_filter_combo = QComboBox()
        self.alert_level_filter_combo.addItem("全部", "all")
        self.alert_level_filter_combo.addItem("INFO", "INFO")
        self.alert_level_filter_combo.addItem("WARN", "WARN")
        self.alert_level_filter_combo.addItem("ERROR", "ERROR")
        self.alert_level_filter_combo.currentIndexChanged.connect(self.apply_alert_filters)
        alert_filter_row.addWidget(self.alert_level_filter_combo)

        alert_filter_row.addWidget(QLabel("状态"))
        self.alert_status_filter_combo = QComboBox()
        self.alert_status_filter_combo.addItem("全部", "all")
        self.alert_status_filter_combo.addItem("未确认", "未确认")
        self.alert_status_filter_combo.addItem("已确认", "已确认")
        self.alert_status_filter_combo.currentIndexChanged.connect(self.apply_alert_filters)
        alert_filter_row.addWidget(self.alert_status_filter_combo)

        reset_alert_filter_button = QPushButton("重置筛选")
        reset_alert_filter_button.clicked.connect(self.on_reset_alert_filters)
        alert_filter_row.addWidget(reset_alert_filter_button)
        alert_layout.addLayout(alert_filter_row)

        alert_time_filter_row = QHBoxLayout()
        alert_time_filter_row.addWidget(QLabel("时间窗"))
        self.alert_time_filter_combo = QComboBox()
        self.alert_time_filter_combo.addItem("全部", None)
        self.alert_time_filter_combo.addItem("最近10分钟", 10 * 60)
        self.alert_time_filter_combo.addItem("最近1小时", 60 * 60)
        self.alert_time_filter_combo.addItem("最近24小时", 24 * 60 * 60)
        self.alert_time_filter_combo.currentIndexChanged.connect(self.apply_alert_filters)
        alert_time_filter_row.addWidget(self.alert_time_filter_combo)

        self.alert_restore_history_checkbox = QCheckBox("启动恢复历史")
        self.alert_restore_history_checkbox.setChecked(True)
        self.alert_restore_history_checkbox.toggled.connect(self.on_alert_history_controls_changed)
        alert_time_filter_row.addWidget(self.alert_restore_history_checkbox)

        alert_time_filter_row.addWidget(QLabel("保留天数"))
        self.alert_history_retention_days_spin = QSpinBox()
        self.alert_history_retention_days_spin.setRange(1, 90)
        self.alert_history_retention_days_spin.setValue(7)
        self.alert_history_retention_days_spin.valueChanged.connect(self.on_alert_history_controls_changed)
        alert_time_filter_row.addWidget(self.alert_history_retention_days_spin)
        alert_layout.addLayout(alert_time_filter_row)

        alert_search_row = QHBoxLayout()
        alert_search_row.addWidget(QLabel("搜索"))
        self.alert_keyword_edit = QLineEdit()
        self.alert_keyword_edit.setPlaceholderText("按来源或内容筛选告警")
        self.alert_keyword_edit.setClearButtonEnabled(True)
        self.alert_keyword_edit.textChanged.connect(self.apply_alert_filters)
        alert_search_row.addWidget(self.alert_keyword_edit)
        alert_layout.addLayout(alert_search_row)

        self.alert_table = QTableWidget(0, 5)
        self.alert_table.setHorizontalHeaderLabels(["时间", "级别", "来源", "内容", "状态"])
        self.alert_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.alert_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.alert_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alert_table.setAlternatingRowColors(True)
        self.alert_table.verticalHeader().setVisible(False)
        self.alert_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.alert_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_table.cellDoubleClicked.connect(self.on_alert_row_double_clicked)
        alert_layout.addWidget(self.alert_table)

        self.alert_stats_overview_label = QLabel("统计: 可见0条 | 未确认0条")
        alert_layout.addWidget(self.alert_stats_overview_label)

        self.alert_stats_table = QTableWidget(0, 6)
        self.alert_stats_table.setHorizontalHeaderLabels(["来源", "总数", "INFO", "WARN", "ERROR", "未确认"])
        self.alert_stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alert_stats_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.alert_stats_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.alert_stats_table.verticalHeader().setVisible(False)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_stats_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.alert_stats_table.cellDoubleClicked.connect(self.on_alert_stats_row_double_clicked)
        alert_layout.addWidget(self.alert_stats_table)

        alert_button_row = QHBoxLayout()
        ack_alert_button = QPushButton("确认选中")
        ack_alert_button.clicked.connect(self.on_ack_selected_alerts)
        alert_button_row.addWidget(ack_alert_button)

        ack_visible_alert_button = QPushButton("确认可见未确认")
        ack_visible_alert_button.clicked.connect(self.on_ack_visible_unacked_alerts)
        alert_button_row.addWidget(ack_visible_alert_button)

        clear_acked_button = QPushButton("清空已确认")
        clear_acked_button.clicked.connect(self.on_clear_acknowledged_alerts)
        alert_button_row.addWidget(clear_acked_button)

        clear_all_alert_button = QPushButton("清空全部")
        clear_all_alert_button.clicked.connect(self.on_clear_all_alerts)
        alert_button_row.addWidget(clear_all_alert_button)

        clear_visible_alert_button = QPushButton("清空可见")
        clear_visible_alert_button.clicked.connect(self.on_clear_visible_alerts)
        alert_button_row.addWidget(clear_visible_alert_button)

        export_alert_button = QPushButton("导出CSV")
        export_alert_button.clicked.connect(self.on_export_alerts_csv)
        alert_button_row.addWidget(export_alert_button)

        export_alert_json_button = QPushButton("导出JSON")
        export_alert_json_button.clicked.connect(self.on_export_alerts_json)
        alert_button_row.addWidget(export_alert_json_button)

        export_alert_stats_button = QPushButton("导出统计CSV")
        export_alert_stats_button.clicked.connect(self.on_export_alert_statistics_csv)
        alert_button_row.addWidget(export_alert_stats_button)

        refresh_alert_stats_button = QPushButton("刷新统计")
        refresh_alert_stats_button.clicked.connect(self.update_alert_statistics)
        alert_button_row.addWidget(refresh_alert_stats_button)
        alert_layout.addLayout(alert_button_row)

        alert_history_row = QHBoxLayout()
        save_alert_history_button = QPushButton("保存历史")
        save_alert_history_button.clicked.connect(self.on_save_alert_history_snapshot)
        alert_history_row.addWidget(save_alert_history_button)

        load_alert_history_button = QPushButton("加载历史")
        load_alert_history_button.clicked.connect(self.on_load_alert_history_snapshot)
        alert_history_row.addWidget(load_alert_history_button)

        export_alert_history_jsonl_button = QPushButton("导出历史JSONL")
        export_alert_history_jsonl_button.clicked.connect(self.on_export_alert_history_jsonl)
        alert_history_row.addWidget(export_alert_history_jsonl_button)

        prune_alert_history_button = QPushButton("清理过期历史")
        prune_alert_history_button.clicked.connect(self.on_prune_alert_history)
        alert_history_row.addWidget(prune_alert_history_button)
        alert_layout.addLayout(alert_history_row)
        self.refresh_alert_id_threshold_table()
        self._refresh_alert_threshold_preset_description()
        self.refresh_alert_threshold_preview_table()
        self._refresh_alert_threshold_import_meta_label()
        self.refresh_alert_threshold_diff_table()
        self.on_alert_rule_controls_changed()

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
        control_layout.addWidget(replay_group)
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

        alert_tab = QWidget()
        alert_tab_layout = QVBoxLayout(alert_tab)
        alert_tab_layout.setContentsMargins(6, 6, 6, 6)
        alert_tab_layout.addWidget(alert_group)
        alert_tab_layout.addStretch()
        self.right_tabs.addTab(alert_tab, "告警")

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
        if not self.data_source.connect():
            self.status_bar.showMessage("数据源连接失败")
            self._refresh_data_source_runtime_label()
            return
        initial_data = self.data_source.poll()
        removed_ids = self.platform_manager.apply_updates(initial_data)
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
        all_platforms = self.platform_manager.get_all_platforms()
        stale_ids = self.platform_manager.get_stale_platform_ids()
        self.map_view.update_platforms(all_platforms)
        self.map_view.set_stale_platforms(stale_ids)
        self.evaluation_service.update(all_platforms)
        self.update_platform_table(all_platforms)
        self._raise_runtime_alerts(all_platforms, stale_ids, removed_ids)
        self.refresh_alert_threshold_preview_table()
        self.map_view.fit_all_platforms()
        status = self.data_source.get_status()
        if status.connected:
            self.status_bar.showMessage(f"数据源已连接: {status.source_name} ({status.mode})")
        self._refresh_data_source_runtime_label()

    def on_timer_update(self) -> None:
        self._mark_ui_tick()
        if self.data_source.is_replay_mode:
            self._advance_replay_frame(status_prefix="回放")
            self._refresh_data_source_runtime_label()
            return

        platform_data = self.data_source.next_frame()
        self._apply_frame_update(platform_data)
        self._refresh_data_source_runtime_label()

    def _apply_frame_update(self, platform_data: list[PlatformState], status_prefix: str = "") -> None:
        removed_ids = self.platform_manager.apply_updates(platform_data)
        all_platforms = self.platform_manager.get_all_platforms()
        stale_ids = self.platform_manager.get_stale_platform_ids()
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
            self.evaluation_service.remove_platforms(removed_ids)
        self.map_view.update_platforms(all_platforms)
        self.map_view.set_stale_platforms(stale_ids)
        self.evaluation_service.update(all_platforms)
        self.update_platform_table(all_platforms)
        self._raise_runtime_alerts(all_platforms, stale_ids, removed_ids)
        self.refresh_alert_threshold_preview_table()

        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix=status_prefix)
            return

        if removed_ids:
            self.clear_selected_platform_info()
            self.platform_table.clearSelection()

        stale_count = len(stale_ids)
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

    def _refresh_data_source_runtime_label(self) -> None:
        if not hasattr(self, "source_status_label"):
            return
        status = self.data_source.get_status()
        detail = status.message.strip() if status.message else "no details"
        ui_platform_count = len(self.platform_manager.get_all_platforms())
        ui_alert_count = self.alert_table.rowCount() if hasattr(self, "alert_table") else 0
        ui_summary = (
            f"ui(platforms={ui_platform_count},alerts={ui_alert_count},refresh_hz={self._ui_tick_rate_hz:.1f})"
        )
        self.source_status_label.setText(
            f"数据源: {status.source_name} | {status.mode} | {detail} | {ui_summary}"
        )

    def _mark_ui_tick(self) -> None:
        self._ui_tick_count += 1
        now = time.monotonic()
        elapsed = now - self._ui_tick_window_start_sec
        if elapsed < 1.0:
            return
        self._ui_tick_rate_hz = self._ui_tick_count / elapsed
        self._ui_tick_count = 0
        self._ui_tick_window_start_sec = now

    def on_platform_selected(self, platform_info: PlatformState, status_prefix: str = "") -> None:
        self.id_label.setText(str(platform_info.id))
        self.type_label.setText(str(platform_info.type))
        self.x_label.setText(f"{platform_info.x:.2f}")
        self.y_label.setText(f"{platform_info.y:.2f}")
        self.z_label.setText(f"{platform_info.z:.2f}")
        self.speed_label.setText(f"{platform_info.speed:.2f}")
        self.timestamp_label.setText(f"{platform_info.timestamp:.2f}")

        metrics = self.evaluation_service.get_metrics(str(platform_info.id))
        if metrics is not None and metrics.planar_error is not None:
            self.truth_error_label.setText(f"{metrics.planar_error:.2f}")
        else:
            self.truth_error_label.setText("--")
        if metrics is not None and metrics.rms_planar_error is not None:
            self.truth_rms_error_label.setText(f"{metrics.rms_planar_error:.2f}")
        else:
            self.truth_rms_error_label.setText("--")

        selected_id = str(platform_info.id)
        self.error_plot_widget.set_series(self.evaluation_service.get_error_series(selected_id))
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
        if self.data_source.is_replay_mode:
            self._advance_replay_frame(status_prefix="回放单步")
            return
        platform_data = self.data_source.next_frame()
        self._apply_frame_update(platform_data, status_prefix="单步刷新完成")

    def on_follow_toggled(self, enabled: bool) -> None:
        self.map_view.set_follow_selected(enabled)
        self.follow_lock_checkbox.setEnabled(enabled)
        self._save_ui_state()

    def on_track_duration_changed(self, duration_sec: float) -> None:
        self.map_view.set_track_duration(duration_sec)
        self.evaluation_service.set_history_duration(duration_sec)
        self.status_bar.showMessage(f"已设置轨迹时间窗: {duration_sec:.1f}s")
        self._save_ui_state()

    def on_clear_tracks(self) -> None:
        self.map_view.clear_tracks()
        self.evaluation_service.clear_histories(self.platform_manager.get_all_platforms())
        selected_info = self.map_view.get_selected_platform_info()
        if selected_info is not None:
            self.on_platform_selected(selected_info, status_prefix="轨迹已清除")
        else:
            self.status_bar.showMessage("轨迹已清除")

    def on_alert_threshold_mode_toggled(self, enabled: bool) -> None:
        self._set_alert_type_threshold_controls_enabled(enabled)
        if self._is_loading_ui_state:
            return
        self.refresh_alert_threshold_preview_table()
        self._mark_alert_preset_custom()
        if enabled:
            self.status_bar.showMessage("已启用按平台类型误差阈值")
        else:
            self.status_bar.showMessage("已切换为统一误差阈值")
        self._save_ui_state()

    def on_alert_rule_controls_changed(self, _value: object | None = None) -> None:
        planar_enabled = (
            self.alert_trigger_enabled_checkbox.isChecked()
            and self.alert_enable_planar_error_checkbox.isChecked()
        )
        self.alert_error_cooldown_spin.setEnabled(
            planar_enabled
        )
        self.alert_error_escalate_count_spin.setEnabled(
            planar_enabled
        )
        if not planar_enabled:
            self.runtime_alert_engine.clear_planar_error_state()
        if self._is_loading_ui_state:
            return
        self._save_ui_state()

    def on_alert_history_controls_changed(self, _value: object | None = None) -> None:
        if self._is_loading_ui_state:
            return
        self._save_ui_state()

    def _collect_alert_records(self, visible_only: bool = False) -> list[AlertRecord]:
        records: list[AlertRecord] = []
        for row in range(self.alert_table.rowCount()):
            if visible_only and self.alert_table.isRowHidden(row):
                continue
            row_data = self._read_alert_row(row)
            time_item = self.alert_table.item(row, 0)
            records.append(
                AlertRecord(
                    epoch=row_data.epoch if row_data.epoch is not None else 0.0,
                    time_text=time_item.text() if time_item is not None else "",
                    level=row_data.level,
                    source=row_data.source,
                    message=row_data.message,
                    status=row_data.status,
                )
            )
        return records

    def _persist_alert_history_snapshot(self) -> None:
        if self._is_restoring_alert_history:
            return
        records = self._collect_alert_records(visible_only=False)
        self.alert_history_service.save_snapshot(records)

    def _restore_alert_history_records(
        self,
        records: list[AlertRecord],
        *,
        clear_existing: bool,
    ) -> None:
        self._is_restoring_alert_history = True
        try:
            if clear_existing:
                self.alert_table.setRowCount(0)
            for record in records:
                self._append_alert(
                    record.level,
                    record.source,
                    record.message,
                    timestamp_epoch=record.epoch,
                    status_text=record.status,
                    time_text=record.normalized_time_text(),
                    apply_filters=False,
                    persist_history=False,
                )
            self.apply_alert_filters()
        finally:
            self._is_restoring_alert_history = False

    def _auto_restore_alert_history(self) -> None:
        if not self.alert_restore_history_checkbox.isChecked():
            return
        records = self.alert_history_service.load_snapshot()
        if not records:
            return
        self._restore_alert_history_records(records, clear_existing=False)
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已自动恢复告警历史: {len(records)} 条")

    def on_save_alert_history_snapshot(self) -> None:
        records = self._collect_alert_records(visible_only=False)
        if self.alert_history_service.save_snapshot(records):
            self.status_bar.showMessage(
                f"已保存告警历史: {len(records)} 条 -> {self.alert_history_service.store_path}"
            )
            return
        self.status_bar.showMessage("保存告警历史失败")

    def on_load_alert_history_snapshot(self) -> None:
        records = self.alert_history_service.load_snapshot()
        if not records:
            self.status_bar.showMessage("未找到可用告警历史")
            return
        self._restore_alert_history_records(records, clear_existing=True)
        self.status_bar.showMessage(f"已加载告警历史: {len(records)} 条")

    def on_export_alert_history_jsonl(self) -> None:
        records = self._collect_alert_records(visible_only=False)
        if not records:
            self.status_bar.showMessage("当前无告警历史可导出")
            return
        file_path = self.alert_history_service.export_jsonl(records)
        if file_path is None:
            self.status_bar.showMessage("告警历史JSONL导出失败")
            return
        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"已导出告警历史JSONL: {file_path}")

    def on_prune_alert_history(self) -> None:
        records = self._collect_alert_records(visible_only=False)
        pruned, removed = self.alert_history_service.prune_records(
            records,
            retention_days=self.alert_history_retention_days_spin.value(),
        )
        if removed <= 0:
            self.status_bar.showMessage("无过期告警历史需要清理")
            return
        self._restore_alert_history_records(pruned, clear_existing=True)
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已清理过期告警历史: {removed} 条")

    def on_alert_id_threshold_mode_toggled(self, enabled: bool) -> None:
        self._set_alert_id_threshold_controls_enabled(enabled)
        if self._is_loading_ui_state:
            return
        self.refresh_alert_threshold_preview_table()
        self._mark_alert_preset_custom()
        if enabled:
            self.status_bar.showMessage("已启用按平台ID阈值覆盖")
        else:
            self.status_bar.showMessage("已关闭按平台ID阈值覆盖")
        self._save_ui_state()

    def _set_alert_type_threshold_controls_enabled(self, enabled: bool) -> None:
        self.alert_error_threshold_uav_spin.setEnabled(enabled)
        self.alert_error_threshold_ugv_spin.setEnabled(enabled)

    def _set_alert_id_threshold_controls_enabled(self, enabled: bool) -> None:
        self.alert_id_threshold_id_edit.setEnabled(enabled)
        self.alert_id_threshold_value_spin.setEnabled(enabled)
        self.set_alert_id_threshold_button.setEnabled(enabled)
        self.remove_alert_id_threshold_button.setEnabled(enabled)
        self.apply_selected_platform_threshold_button.setEnabled(enabled)
        self.clear_alert_id_threshold_button.setEnabled(enabled)
        self.alert_id_threshold_table.setVisible(enabled)

    def on_alert_threshold_preset_changed(self, _index: int) -> None:
        self._refresh_alert_threshold_preset_description()
        self.refresh_alert_threshold_diff_table()
        if self._is_loading_ui_state:
            return
        self._save_ui_state()

    def _mark_alert_preset_custom(self) -> None:
        if str(self.alert_threshold_preset_combo.currentData()) == "custom":
            return
        blocker = QSignalBlocker(self.alert_threshold_preset_combo)
        try:
            index = self.alert_threshold_preset_combo.findData("custom")
            if index >= 0:
                self.alert_threshold_preset_combo.setCurrentIndex(index)
        finally:
            del blocker
        self._clear_alert_threshold_import_meta()
        self._refresh_alert_threshold_preset_description()
        self.refresh_alert_threshold_diff_table()

    def on_alert_threshold_value_changed(self, _value: float) -> None:
        if self._is_loading_ui_state:
            return
        self.refresh_alert_threshold_preview_table()
        self._mark_alert_preset_custom()
        self._save_ui_state()

    def _alert_preset_by_key(self, key: str) -> AlertThresholdPreset | None:
        for preset in self.alert_threshold_presets:
            if preset.key == key:
                return preset
        return None

    def _refresh_alert_threshold_preset_description(self) -> None:
        preset_key = str(self.alert_threshold_preset_combo.currentData())
        preset = self._alert_preset_by_key(preset_key)
        if preset is None:
            self.alert_threshold_preset_desc_label.setText("预设不可用")
            return
        self.alert_threshold_preset_desc_label.setText(f"说明: {preset.description}")

    def _current_alert_threshold_config(self) -> AlertThresholdConfig:
        return AlertThresholdConfig(
            unified_threshold=self.alert_error_threshold_spin.value(),
            use_type_threshold=self.alert_use_type_threshold_checkbox.isChecked(),
            uav_threshold=self.alert_error_threshold_uav_spin.value(),
            ugv_threshold=self.alert_error_threshold_ugv_spin.value(),
            use_id_threshold=self.alert_use_id_threshold_checkbox.isChecked(),
            id_overrides=dict(self.alert_id_threshold_overrides),
        )

    def _apply_alert_threshold_config(self, config: AlertThresholdConfig) -> None:
        blockers = (
            QSignalBlocker(self.alert_error_threshold_spin),
            QSignalBlocker(self.alert_use_type_threshold_checkbox),
            QSignalBlocker(self.alert_error_threshold_uav_spin),
            QSignalBlocker(self.alert_error_threshold_ugv_spin),
            QSignalBlocker(self.alert_use_id_threshold_checkbox),
        )
        try:
            self.alert_error_threshold_spin.setValue(config.unified_threshold)
            self.alert_use_type_threshold_checkbox.setChecked(config.use_type_threshold)
            self.alert_error_threshold_uav_spin.setValue(config.uav_threshold)
            self.alert_error_threshold_ugv_spin.setValue(config.ugv_threshold)
            self.alert_use_id_threshold_checkbox.setChecked(config.use_id_threshold)
        finally:
            for blocker in blockers:
                del blocker

        self.alert_id_threshold_overrides = dict(config.id_overrides)
        self.refresh_alert_id_threshold_table()
        self.refresh_alert_threshold_preview_table()
        self._set_alert_type_threshold_controls_enabled(config.use_type_threshold)
        self._set_alert_id_threshold_controls_enabled(config.use_id_threshold)
        self.refresh_alert_threshold_diff_table()

    def _clear_alert_threshold_import_meta(self) -> None:
        self.last_alert_threshold_import_meta = None
        self._refresh_alert_threshold_import_meta_label()

    def _refresh_alert_threshold_import_meta_label(self) -> None:
        meta = self.last_alert_threshold_import_meta
        if meta is None:
            self.alert_threshold_import_meta_label.setText("阈值配置文件: 未导入")
            return

        migrated_note = " | 已兼容旧格式" if meta.migrated_from_legacy else ""
        exported_at = meta.exported_at if meta.exported_at is not None else "--"
        self.alert_threshold_import_meta_label.setText(
            f"阈值配置文件: v{meta.schema_version} | 预设:{meta.preset_key} | "
            f"导出时间:{exported_at}{migrated_note}"
        )

    def refresh_alert_threshold_diff_table(self) -> None:
        current_config = self._current_alert_threshold_config()
        preset_key = str(self.alert_threshold_preset_combo.currentData())
        preset = self._alert_preset_by_key(preset_key)
        if preset is None:
            reference_name = "参考预设"
            reference_config = AlertThresholdConfig()
        else:
            reference_name = preset.label
            reference_config = preset.config

        diffs = diff_alert_threshold_configs(current_config, reference_config)
        self.alert_threshold_diff_label.setText(f"与{reference_name}差异: {len(diffs)}项")

        blocker = QSignalBlocker(self.alert_threshold_diff_table)
        try:
            self.alert_threshold_diff_table.setRowCount(0)
            for row, (field_name, current_text, reference_text) in enumerate(diffs):
                self.alert_threshold_diff_table.insertRow(row)
                self.alert_threshold_diff_table.setItem(row, 0, QTableWidgetItem(field_name))
                self.alert_threshold_diff_table.setItem(row, 1, QTableWidgetItem(current_text))
                self.alert_threshold_diff_table.setItem(row, 2, QTableWidgetItem(reference_text))
        finally:
            del blocker

    def on_apply_alert_threshold_preset(self) -> None:
        preset_key = str(self.alert_threshold_preset_combo.currentData())
        preset = self._alert_preset_by_key(preset_key)
        if preset is None:
            self.status_bar.showMessage("阈值预设不存在")
            return
        if preset.key == "custom":
            self.status_bar.showMessage("当前为自定义预设，不覆盖现有配置")
            return
        self._clear_alert_threshold_import_meta()
        self._apply_alert_threshold_config(preset.config)
        self.status_bar.showMessage(f"已应用阈值预设: {preset.label}")
        self._save_ui_state()

    def on_export_alert_threshold_config_json(self) -> None:
        export_dir = Path.cwd() / "exports" / "alerts"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = export_dir / f"alert_threshold_config_{timestamp}.json"
        file_path_raw, _ = QFileDialog.getSaveFileName(
            self,
            "导出告警阈值配置",
            str(default_path),
            "JSON Files (*.json)",
        )
        if not file_path_raw:
            self.status_bar.showMessage("已取消导出告警阈值配置")
            return
        file_path = Path(file_path_raw)
        config = self._current_alert_threshold_config()
        if not save_alert_threshold_config(
            file_path,
            config,
            preset_key=str(self.alert_threshold_preset_combo.currentData()),
        ):
            self.status_bar.showMessage("导出告警阈值配置失败")
            return
        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"已导出告警阈值配置: {file_path}")

    def on_import_alert_threshold_config_json(self) -> None:
        default_dir = Path.cwd() / "exports" / "alerts"
        file_path_raw, _ = QFileDialog.getOpenFileName(
            self,
            "导入告警阈值配置",
            str(default_dir),
            "JSON Files (*.json)",
        )
        if not file_path_raw:
            self.status_bar.showMessage("已取消导入告警阈值配置")
            return
        file_path = Path(file_path_raw)
        loaded = load_alert_threshold_config_with_meta(file_path)
        if loaded is None:
            self.status_bar.showMessage("告警阈值配置文件无效")
            return
        config, meta = loaded
        self._apply_alert_threshold_config(config)
        self.last_alert_threshold_import_meta = meta
        self._refresh_alert_threshold_import_meta_label()

        imported_preset_key = meta.preset_key.strip()
        preset_index = self.alert_threshold_preset_combo.findData(imported_preset_key)
        if preset_index >= 0:
            blocker = QSignalBlocker(self.alert_threshold_preset_combo)
            try:
                self.alert_threshold_preset_combo.setCurrentIndex(preset_index)
            finally:
                del blocker
            self._refresh_alert_threshold_preset_description()
            self.refresh_alert_threshold_diff_table()
        else:
            self._mark_alert_preset_custom()

        self.status_bar.showMessage(f"已导入告警阈值配置: {file_path}")
        self._save_ui_state()

    def on_reset_alert_threshold_to_balanced(self) -> None:
        preset = self._alert_preset_by_key("balanced")
        if preset is None:
            self.status_bar.showMessage("均衡预设不存在")
            return
        self._clear_alert_threshold_import_meta()
        blockers = (QSignalBlocker(self.alert_threshold_preset_combo),)
        try:
            index = self.alert_threshold_preset_combo.findData("balanced")
            if index >= 0:
                self.alert_threshold_preset_combo.setCurrentIndex(index)
        finally:
            for blocker in blockers:
                del blocker
        self._refresh_alert_threshold_preset_description()
        self._apply_alert_threshold_config(preset.config)
        self.status_bar.showMessage("已恢复均衡预设")
        self._save_ui_state()

    def _normalize_threshold_platform_id(self, platform_id: str) -> str:
        return platform_id.strip()

    def on_fill_selected_platform_id_for_threshold(self) -> None:
        selected = self.map_view.get_selected_platform_info()
        if selected is None:
            self.status_bar.showMessage("当前未选中平台")
            return
        self.alert_id_threshold_id_edit.setText(str(selected.id))

    def on_alert_id_threshold_row_clicked(self, row: int, _col: int) -> None:
        id_item = self.alert_id_threshold_table.item(row, 0)
        value_item = self.alert_id_threshold_table.item(row, 1)
        if id_item is None or value_item is None:
            return
        self.alert_id_threshold_id_edit.setText(id_item.text())
        try:
            self.alert_id_threshold_value_spin.setValue(float(value_item.text()))
        except ValueError:
            return

    def on_alert_threshold_preview_row_double_clicked(self, row: int, _col: int) -> None:
        id_item = self.alert_threshold_preview_table.item(row, 0)
        if id_item is None:
            return
        platform_id = id_item.text().strip()
        if not platform_id:
            return
        self.alert_id_threshold_id_edit.setText(platform_id)
        if self.map_view.select_platform_by_id(platform_id):
            self.platform_manager.set_selected_platform(platform_id)
            self.map_view.center_on_selected()
            self.right_tabs.setCurrentIndex(0)
            self.status_bar.showMessage(f"已定位并填入阈值平台: {platform_id}")
            return
        self.status_bar.showMessage(f"已填入阈值平台ID: {platform_id}")

    def on_set_alert_id_threshold(self) -> None:
        platform_id = self._normalize_threshold_platform_id(self.alert_id_threshold_id_edit.text())
        if not platform_id:
            self.status_bar.showMessage("请输入平台ID")
            return
        threshold = self.alert_id_threshold_value_spin.value()
        self.alert_id_threshold_overrides[platform_id] = threshold
        self.refresh_alert_id_threshold_table(select_platform_id=platform_id)
        self.refresh_alert_threshold_preview_table()
        self._mark_alert_preset_custom()
        self.status_bar.showMessage(f"已设置平台阈值: {platform_id} -> {threshold:.1f} m")
        self._save_ui_state()

    def on_remove_selected_alert_id_threshold(self) -> None:
        selected_rows = self.alert_id_threshold_table.selectionModel().selectedRows()
        if not selected_rows:
            self.status_bar.showMessage("未选中平台阈值")
            return
        row = selected_rows[0].row()
        id_item = self.alert_id_threshold_table.item(row, 0)
        if id_item is None:
            return
        platform_id = id_item.text()
        if platform_id in self.alert_id_threshold_overrides:
            self.alert_id_threshold_overrides.pop(platform_id, None)
            self.refresh_alert_id_threshold_table()
            self.refresh_alert_threshold_preview_table()
            self._mark_alert_preset_custom()
            self.status_bar.showMessage(f"已删除平台阈值: {platform_id}")
            self._save_ui_state()

    def on_clear_alert_id_thresholds(self) -> None:
        self.alert_id_threshold_overrides.clear()
        self.refresh_alert_id_threshold_table()
        self.refresh_alert_threshold_preview_table()
        self._mark_alert_preset_custom()
        self.status_bar.showMessage("已清空全部平台ID阈值")
        self._save_ui_state()

    def refresh_alert_id_threshold_table(self, select_platform_id: str | None = None) -> None:
        rows = sorted(self.alert_id_threshold_overrides.items(), key=lambda item: item[0])
        blocker = QSignalBlocker(self.alert_id_threshold_table)
        try:
            self.alert_id_threshold_table.setRowCount(0)
            focus_row: int | None = None
            for row, (platform_id, threshold) in enumerate(rows):
                if select_platform_id is not None and platform_id == select_platform_id:
                    focus_row = row
                self.alert_id_threshold_table.insertRow(row)
                self.alert_id_threshold_table.setItem(row, 0, QTableWidgetItem(platform_id))
                self.alert_id_threshold_table.setItem(row, 1, QTableWidgetItem(f"{threshold:.2f}"))
            if focus_row is not None:
                self.alert_id_threshold_table.selectRow(focus_row)
        finally:
            del blocker

    def refresh_alert_threshold_preview_table(self) -> None:
        platform_list = sorted(
            self.platform_manager.get_all_platforms(),
            key=lambda item: str(item.id),
        )
        self.alert_threshold_preview_label.setText(
            f"生效阈值预览: {len(platform_list)}个平台"
        )
        blocker = QSignalBlocker(self.alert_threshold_preview_table)
        try:
            self.alert_threshold_preview_table.setRowCount(0)
            for row, state in enumerate(platform_list):
                threshold, scope = self._error_threshold_for_platform(
                    str(state.id),
                    str(state.type),
                )
                self.alert_threshold_preview_table.insertRow(row)
                self.alert_threshold_preview_table.setItem(row, 0, QTableWidgetItem(str(state.id)))
                self.alert_threshold_preview_table.setItem(row, 1, QTableWidgetItem(f"{threshold:.2f}"))
                self.alert_threshold_preview_table.setItem(row, 2, QTableWidgetItem(scope))
        finally:
            del blocker
        self.refresh_alert_threshold_diff_table()

    def _error_threshold_for_platform(self, platform_id: str, platform_type: str) -> tuple[float, str]:
        config = self._current_alert_threshold_config()
        return resolve_error_threshold(platform_id, platform_type, config)

    def on_stale_timeout_changed(self, value: float) -> None:
        self.platform_manager.set_stale_timeout(value)
        stale_ids = self.platform_manager.get_stale_platform_ids()
        self.map_view.set_stale_platforms(stale_ids)
        self._raise_runtime_alerts(
            self.platform_manager.get_all_platforms(),
            stale_ids,
            [],
        )
        self.remove_timeout_spin.setMinimum(value)
        if self.remove_timeout_spin.value() < value:
            self.remove_timeout_spin.setValue(value)

    def on_remove_timeout_changed(self, value: float) -> None:
        removed_ids = self.platform_manager.set_remove_timeout(value)
        if removed_ids:
            self.map_view.remove_platforms(removed_ids)
            self.clear_selected_platform_info()
            self.platform_table.clearSelection()
        all_platforms = self.platform_manager.get_all_platforms()
        stale_ids = self.platform_manager.get_stale_platform_ids()
        self.map_view.set_stale_platforms(stale_ids)
        self.update_platform_table(all_platforms)
        self._raise_runtime_alerts(all_platforms, stale_ids, removed_ids)
        self.refresh_alert_threshold_preview_table()

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
        if self.data_source.is_replay_mode:
            self.status_bar.showMessage("已恢复自动回放")
            return
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
        series = self.evaluation_service.get_error_series(platform_id)
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
        series = self.evaluation_service.get_error_series(platform_id)
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

    def on_start_recording(self) -> None:
        if self.data_source.is_replay_mode:
            self.status_bar.showMessage("回放模式下不能开始录制")
            return
        if not self.data_source.start_recording():
            self.status_bar.showMessage("开始录制失败")
            return
        self.replay_status_label.setText("模式: 实时录制中")
        self.replay_file_label.setText("文件: --")
        self.replay_frame_label.setText("帧: --/--")
        self._set_replay_slider_state(enabled=False, max_index=0, value=0)
        self.status_bar.showMessage("已开始录制实时数据")

    def on_stop_recording_and_save(self) -> None:
        if not self.data_source.is_recording:
            self.status_bar.showMessage("当前未处于录制状态")
            return
        recorded_frames = self.data_source.stop_recording()
        if not recorded_frames:
            self.replay_status_label.setText("模式: 实时")
            self.replay_frame_label.setText("帧: --/--")
            self.status_bar.showMessage("录制为空，未生成文件")
            return

        record_dir = Path.cwd() / "exports" / "recordings"
        record_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = record_dir / f"replay_{timestamp}.jsonl"
        if not self.data_source.save_recording_jsonl(file_path):
            self.status_bar.showMessage("录制保存失败")
            return

        self.replay_status_label.setText("模式: 实时")
        self.replay_frame_label.setText(f"帧: 0/{len(recorded_frames)}")
        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(
            f"录制完成并保存: {file_path} | 帧数: {len(recorded_frames)}"
        )

    def on_load_replay_file(self) -> None:
        record_dir = Path.cwd() / "exports" / "recordings"
        record_dir.mkdir(parents=True, exist_ok=True)
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "选择回放文件",
            str(record_dir),
            "Replay Files (*.jsonl);;All Files (*)",
        )
        if not file_path_str:
            return

        self.load_replay_from_path(Path(file_path_str))

    def load_replay_from_path(self, file_path: Path) -> bool:
        if not self.data_source.load_replay_jsonl(file_path):
            self.status_bar.showMessage("回放文件为空或格式无效")
            return False

        self.replay_status_label.setText("模式: 回放")
        self.replay_file_label.setText(f"文件: {file_path.name}")
        self._set_replay_slider_state(
            enabled=True,
            max_index=self.data_source.replay_total_frames - 1,
            value=0,
        )
        self.replay_frame_label.setText(f"帧: 0/{self.data_source.replay_total_frames}")
        self._reset_platform_runtime()
        self._advance_replay_frame(status_prefix="回放加载")
        self.status_bar.showMessage(f"已加载回放文件: {file_path}")
        return True

    def on_exit_replay_mode(self) -> None:
        if not self.data_source.is_replay_mode:
            self.status_bar.showMessage("当前不在回放模式")
            return
        self.data_source.exit_replay_mode()
        self.replay_status_label.setText("模式: 实时")
        self.replay_file_label.setText("文件: --")
        self.replay_frame_label.setText("帧: --/--")
        self._set_replay_slider_state(enabled=False, max_index=0, value=0)
        self._reset_platform_runtime()
        self._load_initial_data()
        self.status_bar.showMessage("已退出回放模式并恢复实时数据")

    def on_replay_prev_frame(self) -> None:
        if not self.data_source.is_replay_mode:
            self.status_bar.showMessage("当前不在回放模式")
            return
        if not self.data_source.step_back_replay_cursor():
            self.status_bar.showMessage("已经是回放首帧")
            return
        self._advance_replay_frame(status_prefix="回放回退")

    def on_replay_next_frame(self) -> None:
        if not self.data_source.is_replay_mode:
            self.status_bar.showMessage("当前不在回放模式")
            return
        if self.timer.isActive():
            self.status_bar.showMessage("当前为自动回放，请先暂停再单步")
            return
        self._advance_replay_frame(status_prefix="回放单步")

    def _advance_replay_frame(self, status_prefix: str = "回放") -> bool:
        if not self.data_source.is_replay_mode:
            return False
        total = self.data_source.replay_total_frames
        current_index = self.data_source.replay_frame_index
        if current_index >= total:
            if self.timer.isActive():
                self.timer.stop()
            self.status_bar.showMessage("回放结束")
            return False

        frame = self.data_source.next_frame()
        self._apply_frame_update(
            frame,
            status_prefix=f"{status_prefix} {current_index + 1}/{total}",
        )
        self._update_replay_progress(current_index)
        return True

    def on_replay_slider_changed(self, value: int) -> None:
        if self._syncing_replay_slider or not self.data_source.is_replay_mode:
            return
        if value < 0 or value >= self.data_source.replay_total_frames:
            return
        self.data_source.replay_frame_index = value
        self._advance_replay_frame(status_prefix="回放定位")

    def _set_replay_slider_state(self, enabled: bool, max_index: int, value: int) -> None:
        self._syncing_replay_slider = True
        try:
            self.replay_slider.setEnabled(enabled)
            self.replay_slider.setMinimum(0)
            self.replay_slider.setMaximum(max(0, max_index))
            self.replay_slider.setValue(max(0, min(value, max(0, max_index))))
        finally:
            self._syncing_replay_slider = False

    def _update_replay_progress(self, current_index: int) -> None:
        total = self.data_source.replay_total_frames
        self.replay_status_label.setText("模式: 回放")
        self.replay_frame_label.setText(f"帧: {current_index + 1}/{total}")
        self._set_replay_slider_state(enabled=True, max_index=total - 1, value=current_index)

    def _reset_platform_runtime(self) -> None:
        existing_ids = [state.id for state in self.map_view.get_all_platform_infos()]
        if existing_ids:
            self.map_view.remove_platforms(existing_ids)
        self.platform_manager = PlatformManager(
            stale_timeout_sec=self.stale_timeout_spin.value(),
            remove_timeout_sec=self.remove_timeout_spin.value(),
        )
        self.platform_row_by_id.clear()
        self.platform_table.setRowCount(0)
        self.platform_table.clearSelection()
        self.clear_selected_platform_info()
        self.map_view.set_stale_platforms(set())
        self.evaluation_service.reset()
        self.runtime_alert_engine.reset()

    def _raise_runtime_alerts(
        self,
        all_platforms: list[PlatformState],
        stale_ids: set[str],
        removed_ids: list[str],
    ) -> None:
        events = self.runtime_alert_engine.evaluate(
            all_platforms=all_platforms,
            stale_ids=stale_ids,
            removed_ids=removed_ids,
            trigger_enabled=self.alert_trigger_enabled_checkbox.isChecked(),
            enable_stale=self.alert_enable_stale_checkbox.isChecked(),
            enable_recover=self.alert_enable_recover_checkbox.isChecked(),
            enable_offline=self.alert_enable_offline_checkbox.isChecked(),
            enable_planar_error=self.alert_enable_planar_error_checkbox.isChecked(),
            cooldown_sec=self.alert_error_cooldown_spin.value(),
            escalate_count=self.alert_error_escalate_count_spin.value(),
            threshold_resolver=self._error_threshold_for_platform,
        )
        for event in events:
            self._append_alert(event.level, event.source, event.message)

    def _append_alert(
        self,
        level: str,
        source: str,
        message: str,
        *,
        timestamp_epoch: float | None = None,
        status_text: str = "未确认",
        time_text: str | None = None,
        apply_filters: bool = True,
        persist_history: bool = True,
    ) -> None:
        row = self.alert_table.rowCount()
        self.alert_table.insertRow(row)
        epoch_value = float(timestamp_epoch) if timestamp_epoch is not None else datetime.now().timestamp()
        display_time_text = time_text if time_text is not None else datetime.fromtimestamp(epoch_value).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        time_item = QTableWidgetItem(display_time_text)
        time_item.setData(Qt.ItemDataRole.UserRole, epoch_value)
        self.alert_table.setItem(row, 0, time_item)
        self.alert_table.setItem(row, 1, QTableWidgetItem(level))
        self.alert_table.setItem(row, 2, QTableWidgetItem(source))
        self.alert_table.setItem(row, 3, QTableWidgetItem(message))
        status_item = QTableWidgetItem(status_text)
        self.alert_table.setItem(row, 4, status_item)

        if level == "ERROR":
            color = QColor(255, 120, 120)
        elif level == "WARN":
            color = QColor(255, 200, 120)
        else:
            color = QColor(180, 220, 255)
        for col in range(self.alert_table.columnCount()):
            item = self.alert_table.item(row, col)
            if item is not None:
                item.setForeground(QBrush(color))

        while self.alert_table.rowCount() > self.alert_max_rows:
            self.alert_table.removeRow(0)
        if apply_filters:
            self.apply_alert_filters()
        if persist_history:
            self._persist_alert_history_snapshot()

    def _read_alert_row(self, row: int) -> AlertRow:
        level_text = self.alert_table.item(row, 1).text() if self.alert_table.item(row, 1) else ""
        source_text = self.alert_table.item(row, 2).text() if self.alert_table.item(row, 2) else ""
        message_text = self.alert_table.item(row, 3).text() if self.alert_table.item(row, 3) else ""
        status_text = self.alert_table.item(row, 4).text() if self.alert_table.item(row, 4) else ""
        time_item = self.alert_table.item(row, 0)
        epoch_value: float | None = None
        if time_item is not None:
            raw_epoch = time_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(raw_epoch, (float, int)):
                epoch_value = float(raw_epoch)
        return AlertRow(
            epoch=epoch_value,
            level=level_text,
            source=source_text,
            message=message_text,
            status=status_text,
        )

    def apply_alert_filters(self, _signal_value: object | None = None) -> None:
        level_filter = self.alert_level_filter_combo.currentData()
        status_filter = self.alert_status_filter_combo.currentData()
        time_window_sec = self.alert_time_filter_combo.currentData()
        keyword = self.alert_keyword_edit.text().strip().lower()
        now_epoch = datetime.now().timestamp()

        for row in range(self.alert_table.rowCount()):
            row_data = self._read_alert_row(row)
            visible = should_show_alert(
                row_data,
                level_filter=level_filter,
                status_filter=status_filter,
                time_window_sec=time_window_sec,
                keyword=keyword,
                now_epoch=now_epoch,
            )
            self.alert_table.setRowHidden(row, not visible)
        self.update_alert_statistics()

    def on_reset_alert_filters(self) -> None:
        blockers = (
            QSignalBlocker(self.alert_level_filter_combo),
            QSignalBlocker(self.alert_status_filter_combo),
            QSignalBlocker(self.alert_time_filter_combo),
            QSignalBlocker(self.alert_keyword_edit),
        )
        try:
            self.alert_level_filter_combo.setCurrentIndex(0)
            self.alert_status_filter_combo.setCurrentIndex(0)
            self.alert_time_filter_combo.setCurrentIndex(0)
            self.alert_keyword_edit.clear()
        finally:
            for blocker in blockers:
                del blocker
        self.apply_alert_filters()
        self.status_bar.showMessage("告警筛选已重置")
        self._save_ui_state()

    def _collect_alert_statistics(
        self,
        visible_only: bool = True,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        rows: list[AlertRow] = []
        for row in range(self.alert_table.rowCount()):
            if visible_only and self.alert_table.isRowHidden(row):
                continue
            rows.append(self._read_alert_row(row))
        return summarize_alert_rows(rows)

    def update_alert_statistics(self) -> None:
        summary, by_source = self._collect_alert_statistics(visible_only=True)
        self.alert_stats_overview_label.setText(
            f'统计: 可见{summary["total"]}条 | 未确认{summary["unacked"]}条 | '
            f'INFO {summary["INFO"]} / WARN {summary["WARN"]} / ERROR {summary["ERROR"]}'
        )

        source_rows = sorted(
            by_source.items(),
            key=lambda item: (-item[1]["total"], item[0]),
        )
        self.alert_stats_table.setRowCount(0)
        for row, (source, stats) in enumerate(source_rows):
            self.alert_stats_table.insertRow(row)
            self.alert_stats_table.setItem(row, 0, QTableWidgetItem(source))
            self.alert_stats_table.setItem(row, 1, QTableWidgetItem(str(stats["total"])))
            self.alert_stats_table.setItem(row, 2, QTableWidgetItem(str(stats["INFO"])))
            self.alert_stats_table.setItem(row, 3, QTableWidgetItem(str(stats["WARN"])))
            self.alert_stats_table.setItem(row, 4, QTableWidgetItem(str(stats["ERROR"])))
            self.alert_stats_table.setItem(row, 5, QTableWidgetItem(str(stats["unacked"])))

    def on_ack_selected_alerts(self) -> None:
        selected_rows = self.alert_table.selectionModel().selectedRows()
        if not selected_rows:
            self.status_bar.showMessage("未选中告警")
            return
        for model_index in selected_rows:
            status_item = self.alert_table.item(model_index.row(), 4)
            if status_item is not None:
                status_item.setText("已确认")
        self.apply_alert_filters()
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已确认 {len(selected_rows)} 条告警")

    def on_ack_visible_unacked_alerts(self) -> None:
        ack_count = 0
        for row in range(self.alert_table.rowCount()):
            if self.alert_table.isRowHidden(row):
                continue
            status_item = self.alert_table.item(row, 4)
            if status_item is None:
                continue
            if status_item.text() == "未确认":
                status_item.setText("已确认")
                ack_count += 1
        self.apply_alert_filters()
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已确认可见未确认告警: {ack_count} 条")

    def on_clear_acknowledged_alerts(self) -> None:
        removed = 0
        for row in range(self.alert_table.rowCount() - 1, -1, -1):
            status_item = self.alert_table.item(row, 4)
            if status_item is not None and status_item.text() == "已确认":
                self.alert_table.removeRow(row)
                removed += 1
        self.apply_alert_filters()
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已清空 {removed} 条已确认告警")

    def on_clear_all_alerts(self) -> None:
        self.alert_table.setRowCount(0)
        self.update_alert_statistics()
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage("已清空全部告警")

    def on_clear_visible_alerts(self) -> None:
        removed = 0
        for row in range(self.alert_table.rowCount() - 1, -1, -1):
            if self.alert_table.isRowHidden(row):
                continue
            self.alert_table.removeRow(row)
            removed += 1
        self.apply_alert_filters()
        self._persist_alert_history_snapshot()
        self.status_bar.showMessage(f"已清空可见告警: {removed} 条")

    def on_alert_row_double_clicked(self, row: int, _col: int) -> None:
        source_item = self.alert_table.item(row, 2)
        if source_item is None:
            return
        source_id = source_item.text().strip()
        if not source_id:
            return
        if self.map_view.select_platform_by_id(source_id):
            self.platform_manager.set_selected_platform(source_id)
            self.map_view.center_on_selected()
            self.right_tabs.setCurrentIndex(0)
            self.status_bar.showMessage(f"已根据告警定位平台: {source_id}")
        else:
            self.status_bar.showMessage(f"未找到告警来源平台: {source_id}")

    def on_alert_stats_row_double_clicked(self, row: int, _col: int) -> None:
        source_item = self.alert_stats_table.item(row, 0)
        if source_item is None:
            return
        source_id = source_item.text().strip()
        if not source_id:
            return
        self.alert_keyword_edit.setText(source_id)
        self.status_bar.showMessage(f"已按来源筛选告警: {source_id}")

    def on_export_alerts_csv(self) -> None:
        export_dir = Path.cwd() / "exports" / "alerts"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"alerts_{timestamp}.csv"

        rows: list[list[str]] = []
        for row in range(self.alert_table.rowCount()):
            if self.alert_table.isRowHidden(row):
                continue
            row_data: list[str] = []
            for col in range(self.alert_table.columnCount()):
                item = self.alert_table.item(row, col)
                row_data.append(item.text() if item is not None else "")
            rows.append(row_data)

        if not rows:
            self.status_bar.showMessage("当前筛选结果为空，未导出告警CSV")
            return

        try:
            with file_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["time", "level", "source", "message", "status"])
                writer.writerows(rows)
        except OSError:
            self.status_bar.showMessage("告警CSV导出失败")
            return

        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"已导出告警CSV: {file_path}")

    def on_export_alerts_json(self) -> None:
        export_dir = Path.cwd() / "exports" / "alerts"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"alerts_{timestamp}.json"

        payload: list[dict[str, str]] = []
        for row in range(self.alert_table.rowCount()):
            if self.alert_table.isRowHidden(row):
                continue
            payload.append(
                {
                    "time": self.alert_table.item(row, 0).text() if self.alert_table.item(row, 0) else "",
                    "level": self.alert_table.item(row, 1).text() if self.alert_table.item(row, 1) else "",
                    "source": self.alert_table.item(row, 2).text() if self.alert_table.item(row, 2) else "",
                    "message": self.alert_table.item(row, 3).text() if self.alert_table.item(row, 3) else "",
                    "status": self.alert_table.item(row, 4).text() if self.alert_table.item(row, 4) else "",
                }
            )

        if not payload:
            self.status_bar.showMessage("当前筛选结果为空，未导出告警JSON")
            return

        try:
            file_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            self.status_bar.showMessage("告警JSON导出失败")
            return

        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"已导出告警JSON: {file_path}")

    def on_export_alert_statistics_csv(self) -> None:
        summary, by_source = self._collect_alert_statistics(visible_only=True)
        if summary["total"] == 0:
            self.status_bar.showMessage("当前筛选结果为空，未导出统计CSV")
            return

        export_dir = Path.cwd() / "exports" / "alerts"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"alerts_stats_{timestamp}.csv"
        try:
            with file_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["scope", "total", "INFO", "WARN", "ERROR", "unacked"])
                writer.writerow(
                    [
                        "visible",
                        summary["total"],
                        summary["INFO"],
                        summary["WARN"],
                        summary["ERROR"],
                        summary["unacked"],
                    ]
                )
                writer.writerow([])
                writer.writerow(["source", "total", "INFO", "WARN", "ERROR", "unacked"])
                for source, stats in sorted(by_source.items(), key=lambda item: (-item[1]["total"], item[0])):
                    writer.writerow(
                        [
                            source,
                            stats["total"],
                            stats["INFO"],
                            stats["WARN"],
                            stats["ERROR"],
                            stats["unacked"],
                        ]
                    )
        except OSError:
            self.status_bar.showMessage("告警统计CSV导出失败")
            return

        self.refresh_export_index(focus_path=file_path)
        self.status_bar.showMessage(f"已导出告警统计CSV: {file_path}")

    def refresh_export_index(
        self,
        _signal_value: object | None = None,
        focus_path: Path | None = None,
    ) -> None:
        export_root = Path.cwd() / "exports"
        entries: list[tuple[Path, float, bool]] = []
        selected_type = self.export_type_filter_combo.currentData()
        selected_time_window_sec = self.export_time_filter_combo.currentData()
        selected_sort = self.export_sort_combo.currentData()
        keyword = self.export_keyword_edit.text().strip().lower()
        now_ts = datetime.now().timestamp()
        active_paths: set[str] = set()

        if export_root.exists():
            internal_store_paths = {
                self._pinned_store_path().resolve(),
                self._ui_state_store_path().resolve(),
                self.alert_history_service.store_path.resolve(),
            }
            for path in export_root.rglob("*"):
                if not path.is_file():
                    continue
                if path.resolve() in internal_store_paths:
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
                path_key = str(path.resolve())
                active_paths.add(path_key)
                entries.append((path, mtime, path_key in self.pinned_export_paths))

        # Clean up missing pinned files.
        if self.pinned_export_paths:
            valid_pinned = {path for path in self.pinned_export_paths if path in active_paths}
            if valid_pinned != self.pinned_export_paths:
                self.pinned_export_paths = valid_pinned
                self._save_pinned_exports()

        if selected_sort == "mtime_asc":
            entries.sort(key=lambda item: item[1], reverse=False)
        elif selected_sort == "name_asc":
            entries.sort(key=lambda item: item[0].name.lower(), reverse=False)
        elif selected_sort == "name_desc":
            entries.sort(key=lambda item: item[0].name.lower(), reverse=True)
        else:
            entries.sort(key=lambda item: item[1], reverse=True)

        # Pinned files always stay on top.
        entries.sort(key=lambda item: 0 if item[2] else 1)
        entries = entries[:80]

        focus_row: int | None = None
        blocker = QSignalBlocker(self.export_index_table)
        try:
            self.export_index_table.setRowCount(0)
            for row, (path, mtime, pinned) in enumerate(entries):
                if focus_path is not None and path == focus_path:
                    focus_row = row
                self.export_index_table.insertRow(row)

                pin_item = QTableWidgetItem("★" if pinned else "")
                pin_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.export_index_table.setItem(row, 0, pin_item)

                name_item = QTableWidgetItem(path.name)
                name_item.setData(Qt.ItemDataRole.UserRole, str(path))
                name_item.setToolTip(str(path))
                self.export_index_table.setItem(row, 1, name_item)

                type_item = QTableWidgetItem(self._infer_export_type_label(path))
                self.export_index_table.setItem(row, 2, type_item)

                time_item = QTableWidgetItem(
                    datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                )
                self.export_index_table.setItem(row, 3, time_item)
        finally:
            del blocker

        if self.export_index_table.rowCount() == 0:
            return
        if focus_row is None:
            focus_row = 0
        self.export_index_table.selectRow(focus_row)

    def _ui_state_store_path(self) -> Path:
        return Path.cwd() / "exports" / ".ui_state.json"

    def _set_combo_to_saved_data(self, combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _load_ui_state(self) -> None:
        store_path = self._ui_state_store_path()
        state = load_ui_state(store_path)
        if state is None:
            return

        self._is_loading_ui_state = True
        try:
            blockers = [
                QSignalBlocker(self.platform_type_filter_combo),
                QSignalBlocker(self.platform_status_filter_combo),
                QSignalBlocker(self.platform_keyword_edit),
                QSignalBlocker(self.alert_level_filter_combo),
                QSignalBlocker(self.alert_status_filter_combo),
                QSignalBlocker(self.alert_time_filter_combo),
                QSignalBlocker(self.alert_keyword_edit),
                QSignalBlocker(self.alert_threshold_preset_combo),
                QSignalBlocker(self.alert_trigger_enabled_checkbox),
                QSignalBlocker(self.alert_enable_planar_error_checkbox),
                QSignalBlocker(self.alert_enable_stale_checkbox),
                QSignalBlocker(self.alert_enable_recover_checkbox),
                QSignalBlocker(self.alert_enable_offline_checkbox),
                QSignalBlocker(self.alert_error_cooldown_spin),
                QSignalBlocker(self.alert_error_escalate_count_spin),
                QSignalBlocker(self.alert_restore_history_checkbox),
                QSignalBlocker(self.alert_history_retention_days_spin),
            ]
            try:
                self._set_combo_to_saved_data(
                    self.platform_type_filter_combo,
                    state.platform_type_filter,
                )
                self._set_combo_to_saved_data(
                    self.platform_status_filter_combo,
                    state.platform_status_filter,
                )
                self.platform_keyword_edit.setText(state.platform_keyword)

                self._set_combo_to_saved_data(
                    self.alert_level_filter_combo,
                    state.alert_level_filter,
                )
                self._set_combo_to_saved_data(
                    self.alert_status_filter_combo,
                    state.alert_status_filter,
                )
                self._set_combo_to_saved_data(
                    self.alert_time_filter_combo,
                    state.alert_time_filter_sec,
                )
                self.alert_keyword_edit.setText(state.alert_keyword)
            finally:
                for blocker in blockers:
                    del blocker

            self.follow_checkbox.setChecked(state.follow_selected)
            self.follow_lock_checkbox.setChecked(state.follow_lock_when_enabled)
            self.track_checkbox.setChecked(state.show_tracks)
            self.label_checkbox.setChecked(state.show_labels)
            self.truth_checkbox.setChecked(state.show_truth_points)
            self.truth_track_checkbox.setChecked(state.show_truth_tracks)
            self.velocity_vector_checkbox.setChecked(state.show_velocity_vectors)

            self.track_duration_spin.setValue(state.track_duration_sec)
            self.alert_trigger_enabled_checkbox.setChecked(state.alert_trigger_enabled)
            self.alert_enable_planar_error_checkbox.setChecked(state.alert_enable_planar_error)
            self.alert_enable_stale_checkbox.setChecked(state.alert_enable_stale)
            self.alert_enable_recover_checkbox.setChecked(state.alert_enable_recover)
            self.alert_enable_offline_checkbox.setChecked(state.alert_enable_offline)
            self.alert_error_cooldown_spin.setValue(state.alert_error_cooldown_sec)
            self.alert_error_escalate_count_spin.setValue(state.alert_error_escalate_count)
            self.alert_restore_history_checkbox.setChecked(state.alert_restore_history_on_start)
            self.alert_history_retention_days_spin.setValue(state.alert_history_retention_days)
            self.alert_error_threshold_spin.setValue(state.alert_error_threshold)
            self.alert_use_type_threshold_checkbox.setChecked(state.alert_use_type_threshold)
            self.alert_error_threshold_uav_spin.setValue(state.alert_error_threshold_uav)
            self.alert_error_threshold_ugv_spin.setValue(state.alert_error_threshold_ugv)
            self._set_combo_to_saved_data(
                self.alert_threshold_preset_combo,
                state.alert_threshold_preset_key,
            )
            self.alert_use_id_threshold_checkbox.setChecked(state.alert_use_id_threshold)
            self.alert_id_threshold_overrides = dict(state.alert_id_threshold_overrides)
            self.refresh_alert_id_threshold_table()
            self.refresh_alert_threshold_preview_table()
            self._refresh_alert_threshold_preset_description()
            self._set_alert_type_threshold_controls_enabled(state.alert_use_type_threshold)
            self._set_alert_id_threshold_controls_enabled(state.alert_use_id_threshold)
            self.on_alert_rule_controls_changed()

            sort_column = state.platform_sort_column
            try:
                sort_order = Qt.SortOrder(state.platform_sort_order)
            except ValueError:
                sort_order = Qt.SortOrder.AscendingOrder
            if 0 <= sort_column < self.platform_table.columnCount():
                self.platform_table.horizontalHeader().setSortIndicator(sort_column, sort_order)
                self.platform_table.sortByColumn(sort_column, sort_order)

            self.apply_platform_table_filters()
            self.apply_alert_filters()
        finally:
            self._is_loading_ui_state = False

    def _save_ui_state(self) -> None:
        if self._is_loading_ui_state or not self._ui_state_ready:
            return
        state = UiState(
            platform_type_filter=str(self.platform_type_filter_combo.currentData()),
            platform_status_filter=str(self.platform_status_filter_combo.currentData()),
            platform_keyword=self.platform_keyword_edit.text().strip(),
            platform_sort_column=self.platform_table.horizontalHeader().sortIndicatorSection(),
            platform_sort_order=self.platform_table.horizontalHeader().sortIndicatorOrder().value,
            alert_level_filter=str(self.alert_level_filter_combo.currentData()),
            alert_status_filter=str(self.alert_status_filter_combo.currentData()),
            alert_time_filter_sec=self.alert_time_filter_combo.currentData(),
            alert_keyword=self.alert_keyword_edit.text().strip(),
            follow_selected=self.follow_checkbox.isChecked(),
            follow_lock_when_enabled=self.follow_lock_checkbox.isChecked(),
            show_tracks=self.track_checkbox.isChecked(),
            show_labels=self.label_checkbox.isChecked(),
            show_truth_points=self.truth_checkbox.isChecked(),
            show_truth_tracks=self.truth_track_checkbox.isChecked(),
            show_velocity_vectors=self.velocity_vector_checkbox.isChecked(),
            track_duration_sec=self.track_duration_spin.value(),
            alert_trigger_enabled=self.alert_trigger_enabled_checkbox.isChecked(),
            alert_enable_planar_error=self.alert_enable_planar_error_checkbox.isChecked(),
            alert_enable_stale=self.alert_enable_stale_checkbox.isChecked(),
            alert_enable_recover=self.alert_enable_recover_checkbox.isChecked(),
            alert_enable_offline=self.alert_enable_offline_checkbox.isChecked(),
            alert_error_cooldown_sec=self.alert_error_cooldown_spin.value(),
            alert_error_escalate_count=self.alert_error_escalate_count_spin.value(),
            alert_restore_history_on_start=self.alert_restore_history_checkbox.isChecked(),
            alert_history_retention_days=self.alert_history_retention_days_spin.value(),
            alert_error_threshold=self.alert_error_threshold_spin.value(),
            alert_use_type_threshold=self.alert_use_type_threshold_checkbox.isChecked(),
            alert_error_threshold_uav=self.alert_error_threshold_uav_spin.value(),
            alert_error_threshold_ugv=self.alert_error_threshold_ugv_spin.value(),
            alert_threshold_preset_key=str(self.alert_threshold_preset_combo.currentData()),
            alert_use_id_threshold=self.alert_use_id_threshold_checkbox.isChecked(),
            alert_id_threshold_overrides=dict(self.alert_id_threshold_overrides),
        )
        save_ui_state(self._ui_state_store_path(), state)

    def _pinned_store_path(self) -> Path:
        return Path.cwd() / "exports" / ".pinned_exports.json"

    def _load_pinned_exports(self) -> None:
        store_path = self._pinned_store_path()
        if not store_path.exists():
            return
        try:
            data = json.loads(store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        normalized: set[str] = set()
        for item in data:
            if not isinstance(item, str):
                continue
            normalized.add(str(Path(item).resolve()))
        self.pinned_export_paths = normalized

    def _save_pinned_exports(self) -> None:
        store_path = self._pinned_store_path()
        store_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            serialized = json.dumps(
                sorted(self.pinned_export_paths),
                ensure_ascii=False,
                indent=2,
            )
            store_path.write_text(serialized, encoding="utf-8")
        except OSError:
            return

    def _infer_export_type_key(self, path: Path) -> str:
        file_name = path.name
        suffix = path.suffix.lower()
        if file_name.startswith("nav_snapshot_") and suffix == ".png":
            return "snapshot"
        if file_name.startswith("alert_threshold_config_") and suffix == ".json":
            return "alert_cfg"
        if file_name.startswith("alert_history_") and suffix == ".jsonl":
            return "alerts_json"
        if file_name.startswith("alerts_") and suffix == ".json":
            return "alerts_json"
        if suffix == ".csv":
            return "error_csv"
        if suffix == ".png" and "_planar_error_" in file_name:
            return "error_plot"
        return "other"

    def _infer_export_type_label(self, path: Path) -> str:
        type_key = self._infer_export_type_key(path)
        if type_key == "snapshot":
            return "态势截图"
        if type_key == "alert_cfg":
            return "告警配置JSON"
        if type_key == "alerts_json":
            return "告警记录JSON/JSONL"
        if type_key == "error_csv":
            return "误差CSV"
        if type_key == "error_plot":
            return "误差曲线PNG"
        return "其他文件"

    def on_export_index_double_clicked(self, row: int, _col: int) -> None:
        self.export_index_table.selectRow(row)
        self.on_open_selected_export()

    def _get_selected_export_paths(self, notify_empty: bool = True) -> list[Path]:
        selected_rows = self.export_index_table.selectionModel().selectedRows()
        if not selected_rows:
            if notify_empty:
                self.status_bar.showMessage("未选中导出文件")
            return []

        selected_paths: list[Path] = []
        for model_index in selected_rows:
            name_item = self.export_index_table.item(model_index.row(), 1)
            if name_item is None:
                continue
            file_path_raw = name_item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(file_path_raw, str):
                continue
            selected_paths.append(Path(file_path_raw))
        if not selected_paths and notify_empty:
            self.status_bar.showMessage("导出文件信息无效")
        return selected_paths

    def _get_selected_export_path(self) -> Path | None:
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return None
        return selected_paths[0]

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
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return
        clipboard_text = "\n".join(str(path) for path in selected_paths)
        QApplication.clipboard().setText(clipboard_text)
        if len(selected_paths) == 1:
            self.status_bar.showMessage(f"已复制路径: {selected_paths[0]}")
        else:
            self.status_bar.showMessage(f"已复制 {len(selected_paths)} 个文件路径")

    def on_pin_selected_export(self) -> None:
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return
        added_count = 0
        for file_path in selected_paths:
            path_key = str(file_path.resolve())
            if path_key in self.pinned_export_paths:
                continue
            self.pinned_export_paths.add(path_key)
            added_count += 1
        if added_count == 0:
            self.status_bar.showMessage("所选文件均已置顶")
            return
        self._save_pinned_exports()
        self.refresh_export_index(focus_path=selected_paths[0])
        self.status_bar.showMessage(f"已置顶 {added_count} 个文件")

    def on_unpin_selected_export(self) -> None:
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return
        removed_count = 0
        for file_path in selected_paths:
            path_key = str(file_path.resolve())
            if path_key not in self.pinned_export_paths:
                continue
            self.pinned_export_paths.remove(path_key)
            removed_count += 1
        if removed_count == 0:
            self.status_bar.showMessage("所选文件均未置顶")
            return
        self._save_pinned_exports()
        self.refresh_export_index(focus_path=selected_paths[0])
        self.status_bar.showMessage(f"已取消置顶 {removed_count} 个文件")

    def on_select_all_visible_exports(self) -> None:
        row_count = self.export_index_table.rowCount()
        if row_count == 0:
            self.status_bar.showMessage("当前筛选结果为空")
            return
        self.export_index_table.selectAll()
        self.status_bar.showMessage(f"已全选 {row_count} 个可见文件")

    def on_open_selected_exports_batch(self) -> None:
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return

        opened_count = 0
        missing_count = 0
        for file_path in selected_paths:
            if not file_path.exists():
                missing_count += 1
                continue
            if QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path))):
                opened_count += 1
        if opened_count == 0 and missing_count > 0:
            self.refresh_export_index()
            self.status_bar.showMessage("所选文件均不存在，已刷新导出索引")
            return
        self.status_bar.showMessage(
            f"批量打开完成 | 成功: {opened_count} | 不存在: {missing_count}"
        )

    def on_cleanup_selected_exports(self) -> None:
        selected_paths = self._get_selected_export_paths()
        if not selected_paths:
            return

        reply = QMessageBox.question(
            self,
            "批量清理导出文件",
            f"确定删除选中的 {len(selected_paths)} 个导出文件吗？\n该操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_bar.showMessage("已取消批量清理")
            return

        deleted_count = 0
        failed_count = 0
        for file_path in selected_paths:
            try:
                if file_path.exists():
                    file_path.unlink()
                    deleted_count += 1
                else:
                    failed_count += 1
            except OSError:
                failed_count += 1
            self.pinned_export_paths.discard(str(file_path.resolve()))
        self._save_pinned_exports()
        self.refresh_export_index()
        self.status_bar.showMessage(
            f"批量清理完成 | 删除: {deleted_count} | 失败/不存在: {failed_count}"
        )

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
        sort_column = self.platform_table.horizontalHeader().sortIndicatorSection()
        sort_order = self.platform_table.horizontalHeader().sortIndicatorOrder()
        sorting_enabled = self.platform_table.isSortingEnabled()
        if sorting_enabled:
            self.platform_table.setSortingEnabled(False)

        self._rebuild_platform_row_mapping()
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

            self._set_table_numeric_text(row, 2, f"{platform_info.speed:.2f}", platform_info.speed)
            self._set_table_numeric_text(
                row,
                3,
                f"{platform_info.timestamp:.2f}",
                platform_info.timestamp,
            )
            is_stale = self.platform_manager.is_platform_stale(platform_id)
            self._set_table_text(row, 4, "超时" if is_stale else "正常")
            self._set_row_style(row, is_stale)

        self._rebuild_platform_row_mapping()
        if sorting_enabled:
            self.platform_table.setSortingEnabled(True)
            self.platform_table.sortByColumn(sort_column, sort_order)
            self._rebuild_platform_row_mapping()
        self.apply_platform_table_filters()

    def apply_platform_table_filters(self, _signal_value: object | None = None) -> None:
        type_filter = self.platform_type_filter_combo.currentData()
        status_filter = self.platform_status_filter_combo.currentData()
        keyword = self.platform_keyword_edit.text().strip().lower()

        for row in range(self.platform_table.rowCount()):
            id_text = self.platform_table.item(row, 0).text() if self.platform_table.item(row, 0) else ""
            type_text = self.platform_table.item(row, 1).text() if self.platform_table.item(row, 1) else ""
            status_text = self.platform_table.item(row, 4).text() if self.platform_table.item(row, 4) else ""

            visible = True
            if type_filter not in (None, "all") and type_text != str(type_filter):
                visible = False
            if status_filter not in (None, "all") and status_text != str(status_filter):
                visible = False
            if keyword and keyword not in id_text.lower():
                visible = False
            self.platform_table.setRowHidden(row, not visible)

        self.update_platform_summary_label()

    def update_platform_summary_label(self) -> None:
        total = self.platform_table.rowCount()
        visible_count = 0
        uav_count = 0
        ugv_count = 0
        normal_count = 0
        stale_count = 0

        for row in range(total):
            if self.platform_table.isRowHidden(row):
                continue
            visible_count += 1
            type_text = self.platform_table.item(row, 1).text() if self.platform_table.item(row, 1) else ""
            status_text = self.platform_table.item(row, 4).text() if self.platform_table.item(row, 4) else ""
            if type_text == "UAV":
                uav_count += 1
            elif type_text == "UGV":
                ugv_count += 1
            if status_text == "超时":
                stale_count += 1
            else:
                normal_count += 1

        self.platform_summary_label.setText(
            f"统计: 可见{visible_count}/总{total} | UAV {uav_count} | UGV {ugv_count} | "
            f"正常 {normal_count} | 超时 {stale_count}"
        )

    def on_reset_platform_filters(self) -> None:
        blockers = (
            QSignalBlocker(self.platform_type_filter_combo),
            QSignalBlocker(self.platform_status_filter_combo),
            QSignalBlocker(self.platform_keyword_edit),
        )
        try:
            self.platform_type_filter_combo.setCurrentIndex(0)
            self.platform_status_filter_combo.setCurrentIndex(0)
            self.platform_keyword_edit.clear()
        finally:
            for blocker in blockers:
                del blocker
        self.apply_platform_table_filters()
        self.status_bar.showMessage("平台列表筛选已重置")
        self._save_ui_state()

    def on_platform_table_sort_changed(self, _col: int, _order: Qt.SortOrder) -> None:
        self._rebuild_platform_row_mapping()
        self.apply_platform_table_filters()
        self._save_ui_state()

    def _set_table_text(self, row: int, col: int, text: str) -> None:
        item = self.platform_table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.platform_table.setItem(row, col, item)
        item.setText(text)

    def _set_table_numeric_text(self, row: int, col: int, text: str, numeric_value: float) -> None:
        item = self.platform_table.item(row, col)
        if isinstance(item, NumericTableWidgetItem):
            item.set_numeric(text, numeric_value)
            return
        numeric_item = NumericTableWidgetItem(text, numeric_value)
        self.platform_table.setItem(row, col, numeric_item)

    def _set_row_style(self, row: int, is_stale: bool) -> None:
        if is_stale:
            foreground = QBrush(QColor(170, 40, 40))
        else:
            foreground = QBrush(QColor(35, 35, 35))
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
        if row is None or self.platform_table.isRowHidden(row):
            return
        self._syncing_table_selection = True
        blocker = QSignalBlocker(self.platform_table)
        try:
            self.platform_table.selectRow(row)
        finally:
            del blocker
            self._syncing_table_selection = False

    def closeEvent(self, event) -> None:
        self._save_ui_state()
        self._persist_alert_history_snapshot()
        self.data_source.disconnect()
        super().closeEvent(event)

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            "205_nav_ui 原型（第四十二步）\n\n"
            "当前功能：\n"
            "- UAV/UGV 不同图形显示\n"
            "- 平台状态统一dataclass（含在线与真值预留字段）\n"
            "- PlatformManager 集中管理状态/告警/移除\n"
            "- 数据源接口抽象，可替换接入\n"
            "- 真值点/真值轨迹显示与误差可视化（当前+RMS）\n"
            "- 选中平台误差曲线面板\n"
            "- 误差CSV与误差曲线PNG导出\n"
            "- 导出索引面板（筛选 + 搜索 + 排序 + 置顶）\n"
            "- 一键复制选中导出文件路径\n"
            "- 多选导出文件批量打开与批量清理\n"
            "- 实时数据录制与文件回放\n"
            "- 告警中心（超时/下线/误差超阈）\n"
            "- 告警确认与清理\n"
            "- 告警筛选（级别/状态/关键字）\n"
            "- 告警CSV导出\n"
            "- 告警来源分组统计与统计CSV导出\n"
            "- 双击告警可快速定位对应平台\n"
            "- 双击告警统计来源可快速筛选告警\n"
            "- 平台列表支持类型/状态/关键字筛选\n"
            "- 平台列表支持点击表头排序\n"
            "- 平台筛选条件与排序支持重启恢复\n"
            "- 平台列表统计概览（可见/总数/UAV/UGV/正常/超时）\n"
            "- 轨迹时间窗可在线调节\n"
            "- 速度矢量显示开关\n"
            "- 速度矢量样式区分UAV/UGV\n"
            "- 误差告警阈值支持统一/按类型配置\n"
            "- 误差告警阈值支持按平台ID覆盖\n"
            "- 告警阈值预设方案一键切换\n"
            "- 告警阈值配置支持JSON导入/导出\n"
            "- 告警阈值JSON支持版本化与旧格式兼容导入\n"
            "- 告警阈值生效来源实时预览\n"
            "- 支持从阈值配置文件回显元信息（版本/预设/导出时间）\n"
            "- 告警阈值支持与参考预设差异对比\n"
            "- 告警规则支持按项开关与误差告警间隔配置\n"
            "- 误差告警支持连续超阈升级为ERROR\n"
            "- 告警支持一键确认可见未确认与清空可见\n"
            "- 告警记录支持JSON导出\n"
            "- 告警支持时间窗筛选\n"
            "- 告警历史支持保存/加载/JSONL导出/按天清理\n"
            "- 支持启动自动恢复告警历史\n"
            "- 导出索引支持筛选告警配置JSON\n"
            "- 回放时间轴拖动定位\n"
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
