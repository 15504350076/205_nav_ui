# 205_nav_ui

PySide6 原型界面，用于无人机（UAV）与无人车（UGV）协同导航定位显示。

当前阶段目标是先把 GUI 原型和状态管理打磨好，使用假数据驱动，不接 ROS2/真实传感器。

## 1. 项目定位

- 平台：Ubuntu 22.04 + Python 3 + PySide6
- 运行方式：`python3 app.py`
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
- 告警误差阈值支持统一模式与按类型模式（UAV/UGV）
- 告警确认、清空已确认、清空全部
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
- 一键复制选中导出文件路径
- 多选导出文件批量打开与批量清理

## 3. 架构说明

### 3.1 核心分层

- `models.py`
  - `PlatformState`：统一平台状态 `dataclass`
  - 已预留字段：`is_online`、`truth_x/y/z`
- `data_source.py`
  - `PlatformDataSource` 协议（可替换数据源接口）
- `platform_manager.py`
  - 集中管理平台状态、超时告警、超时移除、选中状态
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

## 4. 快速启动

```bash
cd /home/pdq/205_nav_ui
python3 app.py
```

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

## 6. 后续建议

- 增加 `PlatformDataSource` 的 ROS2 适配实现（保持 UI 层无感知）
- 增加日志回放数据源（JSONL/CSV）
- 增加导出索引按目录分组与统计
- 增加告警规则配置（按平台/级别自定义阈值）
- 扩展测试：`MapView` 交互与主窗口联动
