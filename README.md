# 205_nav_ui

PySide6 原型界面，用于无人机（UAV）与无人车（UGV）协同导航定位显示。

当前阶段在保持 GUI 与状态管理稳定迭代的同时，已打通 ROS2 最小接入闭环（单平台 pose/truth/health）。

## 0. 当前阶段说明

- 项目已从“原型 UI”进入“可持续迭代架构”阶段
- 当前优先级从“新增 UI 小功能”转向“验证真实 ROS2 最小接入闭环”
- 接入策略保持不变：ROS2 逻辑走适配器层，UI 层保持无感知

## 1. 项目定位

- 平台：Ubuntu 22.04 + Python 3 + PySide6
- 运行方式：`python3 app.py`（支持 `--source` 切换数据源）
- 当前数据源：`FakeDataGenerator`（可替换接口）
- 未来方向：ROS2 Humble 在线接入、RTK 真值对比、离线回放

## 2. 当前实现能力

### 2.1 态势图显示

- 多平台动态显示（UAV 圆形、UGV 方形）
- 网格背景 + 坐标轴 + 图例
- 鼠标点击选中高亮
- 滚轮缩放，`R` 复位
- 左侧地图视图随窗口/分栏变化自适应填充
- 全局视图、定位选中、复位视图

### 2.2 轨迹与真值

- 估计轨迹显示/隐藏/清除
- 轨迹时间窗在线调节
- 速度矢量显示/隐藏
- 速度矢量按平台类型区分样式（UAV实线 / UGV虚线）
- 真值点显示/隐藏
- 真值轨迹显示/隐藏
- 估计与真值平面误差显示
- 轨迹 RMS 误差显示（按当前历史窗口）
- 选中平台误差曲线面板（右侧实时更新）

### 2.3 状态与告警

- 平台列表联动（地图选中 <-> 列表选中）
- 平台列表筛选（类型/状态/ID关键字）
- 平台列表支持点击表头排序
- 平台筛选条件与排序支持重启恢复
- 平台列表统计概览（可见/总数/UAV/UGV/正常/超时）
- 超时告警（灰显 + 列表状态）
- 下线自动移除（图元/轨迹/列表同步清理）
- 阈值在线可调（告警阈值、移除阈值）
- 告警中心（超时/下线/误差超阈）
- 告警规则开关（超时/恢复/下线/误差）与全局触发开关
- 误差告警支持触发间隔与连续超阈升级（WARN -> ERROR）
- 告警误差阈值支持统一模式与按类型模式（UAV/UGV）
- 告警误差阈值支持按平台ID覆盖（单平台精细阈值）
- 告警阈值预设（均衡/敏感/稳健/地面精细）一键应用
- 告警阈值配置支持JSON导入/导出
- 告警阈值配置JSON包含版本字段并兼容旧格式导入
- 告警阈值生效来源预览（每平台阈值与来源）
- 告警阈值配置显示文件元信息（版本/预设/导出时间）
- 告警阈值支持与参考预设差异对比
- 告警时间窗筛选（10分钟/1小时/24小时）
- 告警确认、清空已确认、清空全部
- 告警支持一键确认可见未确认与清空可见
- 告警记录支持JSON导出
- 告警历史快照保存/加载、JSONL导出、按保留天数清理
- 可设置启动时自动恢复告警历史
- 告警筛选（级别/状态/关键字）
- 告警CSV导出
- 告警来源分组统计与统计CSV导出
- 双击告警定位来源平台
- 双击统计来源快速筛选告警

### 2.4 运行控制

- 暂停 / 恢复 / 单步刷新
- 回放倍速：`0.5x / 1.0x / 2.0x`
- 掉帧仿真（启用开关 + 丢包率）
- 左右分栏支持鼠标拖拽调宽
- 右侧功能按选项卡分类切换（监控/显示/控制/导出/说明/告警）
- 实时数据录制（JSONL）
- 文件回放（加载后自动回放 + 单步前进/后退 + 时间轴拖动定位）
- 一键导出态势图截图（保存到 `exports/` 目录）
- 误差数据导出（CSV）与误差曲线导出（PNG）
- 导出索引面板（类型/时间筛选 + 关键字搜索 + 排序 + 置顶）
- 导出索引支持告警配置JSON筛选
- 导出索引支持告警记录JSON筛选
- 导出索引支持告警历史JSONL筛选
- 一键复制选中导出文件路径
- 多选导出文件批量打开与批量清理

## 3. 架构说明

### 3.1 核心分层

- `platform_state.py`
  - `PlatformState`：统一平台状态模型（含 `to_dict/from_dict`）
- `models.py`
  - 兼容层：对外重导出 `PlatformState`
- `data_source.py`
  - `PlatformDataSource` / `ReplayCapableDataSource` 协议（实时/回放统一接口）
- `data_adapter.py`
  - 统一适配器接口（`connect/disconnect/poll/next_frame/is_live/get_status`）
- `live_data_source.py`
  - 实时源适配器（将 `PlatformDataSource` 接入统一适配器接口）
- `replay_data_source.py`
  - 录制与回放数据源封装（实时源包装、JSONL读写、回放游标控制）
- `ros_bridge_adapter.py`
  - ROS2 桥接适配器骨架与 mock 实时适配器
- `ros2_client.py`
  - 真实 ROS2 入站客户端（`rclpy`）与 stub/in-memory 客户端
- `ros_topic_mapping.py`
  - 约定 ROS topic 到 `PlatformState` 字段映射（pose/truth/health）
- `alert_event.py`
  - 统一告警事件模型（运行态与历史快照共用）
- `platform_manager.py`
  - 集中管理平台状态、超时告警、超时移除、选中状态
- `alert_rules.py`
  - 告警阈值规则解析、预设定义、版本化JSON配置读写与差异比较
- `alert_history.py`
  - 告警历史记录模型、历史快照读写、JSONL导出与按时间清理
- `alert_history_service.py`
  - 告警历史快照服务（读写/导出/按保留天数清理）
- `alert_center.py`
  - 告警筛选判定与分组统计聚合（与UI表格解耦的纯逻辑）
- `alert_runtime.py`
  - 运行态告警规则引擎（超时/恢复/下线/误差升级）
- `evaluation_service.py`
  - 导航估计/真值/评估结果三层解耦与误差/RMS聚合
- `ui_state.py`
  - 统一管理 UI 筛选/排序/显示开关/阈值配置的序列化与持久化
- `map_view.py`
  - 只负责可视化：图元、轨迹、真值层、视图交互
- `main_window.py`
  - 负责 UI 编排、控件联动、状态栏信息、调用 manager/data source
- `fake_data.py`
  - 当前默认数据源，实现 `PlatformDataSource`
  - 提供估计值 + 真值 + 掉帧仿真

### 3.2 关键设计点

- 状态与可视化解耦：`PlatformManager` 决策，`MapView` 渲染
- 数据源可插拔：后续接 ROS2 时可替换 `FakeDataGenerator`
- 数据结构统一：UI 与业务共享 `PlatformState`

### 3.3 核心数据流

- `fake/replay/mock_ros/ros2` 数据源 -> `DataAdapter`
- `DataAdapter` 输出统一 `PlatformState`
- `PlatformManager` 维护在线/超时/移除状态
- `EvaluationService` 计算误差与 RMS
- `RuntimeAlertEngine` 触发运行态告警
- `MapView + MainWindow` 完成可视化与交互编排
- `AlertHistoryService / export` 负责历史与导出

## 4. 快速启动

```bash
cd /home/pdq/205_nav_ui
python3 app.py
```

可选数据源启动方式：

```bash
# 默认假数据
python3 app.py --source fake

# ROS2 形态 mock 实时流
python3 app.py --source mock_ros --mock-ros-ids UAV1,UAV2,UGV1 --mock-ros-interval 0.1

# 从 JSONL 录制文件直接回放
python3 app.py --source replay --replay-file exports/recordings/xxx.jsonl

# 最小真实 ROS2 接入（单平台）
python3 app.py --source ros2 --ros2-platform-id UAV1
```

### 4.1 ROS2 最小接入约定（单平台闭环）

最小 topic（默认）：

- 估计位姿：`/swarm/{platform_id}/nav/pose`（建议 `geometry_msgs/PoseStamped`）
- 真值位姿：`/swarm/{platform_id}/truth/pose`（建议 `geometry_msgs/PoseStamped`）
- 健康状态：`/swarm/{platform_id}/health`（建议 `std_msgs/String`，JSON 字符串）

内部字段映射：

- `pose topic` -> `PlatformState.x/y/z/timestamp`（可带 `type/nav_state`）
- `truth topic` -> `PlatformState.truth_x/truth_y/truth_z/timestamp`
- `health topic` -> `PlatformState.is_online/link_state/nav_state/timestamp`

健康状态字符串示例（JSON）：

```json
{"is_online": true, "link_state": "OK", "nav_state": "TRACKING", "timestamp": 1710000000.1}
```

### 4.2 ROS2 一键联调脚本

已提供最小闭环发布脚本：

- `scripts/ros2_demo_publishers.sh`

使用方式：

```bash
# 终端1：启动 UI
python3 app.py --source ros2 --ros2-platform-id UAV1

# 终端2：启动最小topic发布（默认 UAV1）
./scripts/ros2_demo_publishers.sh UAV1
```

脚本会持续发布：

- `/swarm/UAV1/nav/pose`
- `/swarm/UAV1/truth/pose`
- `/swarm/UAV1/health`

如果遇到 Qt `xcb` 插件相关错误（例如缺 `libxcb-cursor0`），可安装：

```bash
sudo apt-get update
sudo apt-get install -y libxcb-cursor0
```

无显示环境可用（例如 CI）：

```bash
QT_QPA_PLATFORM=offscreen python3 app.py
```

## 5. 测试与回归

语法检查：

```bash
python3 -m py_compile *.py
```

单元测试（重点覆盖 `PlatformManager`）：

```bash
python3 -m pytest -q
```

当前测试文件：

- `tests/test_platform_manager.py`
- `tests/test_fake_data.py`
- `tests/test_ui_state.py`
- `tests/test_alert_rules.py`
- `tests/test_alert_history.py`
- `tests/test_alert_history_service.py`
- `tests/test_alert_center.py`
- `tests/test_alert_event.py`
- `tests/test_alert_runtime.py`
- `tests/test_evaluation_service.py`
- `tests/test_live_data_source.py`
- `tests/test_main_window_alerts.py`
- `tests/test_main_window_integration.py`
- `tests/test_platform_state.py`
- `tests/test_replay_data_source.py`
- `tests/test_app_cli.py`
- `tests/test_ros2_client.py`
- `tests/test_ros_bridge_adapter.py`
- `tests/test_ros_topic_mapping.py`

CI（GitHub Actions）：

- `.github/workflows/ci.yml`
  - 执行 `python -m py_compile *.py tests/*.py`
  - 执行 `python -m pytest -q`

## 6. 后续建议

- 完善真实 ROS2 适配器（多平台/更多 topic，保持 UI 层无感知）
- 增加日志回放数据源（JSONL/CSV）
- 增加导出索引按目录分组与统计
- 增加告警规则配置（按平台/级别自定义阈值）
- 扩展测试：`MapView` 交互与主窗口联动

## 7. 后续开发路线图

- P0：完成 ROS2 最小闭环实测（单平台 pose/truth/health）
- P0：沉淀 ros2 运行脚本与联调文档（topic 发布示例、故障排查）
- P1：扩展多平台订阅（平台发现、动态上下线）
- P1：补齐 ROS2 message 适配（速度、协方差、状态码）
- P1：增加 ros2 回放一致性测试（与 JSONL 回放对比）
- P2：完善地图交互自动化测试与性能压测
