# ROS2 最小接入协议（冻结版 v1）

本协议用于 `205_nav_ui` 的最小真实接入闭环，目标是保证车/机/真值/告警链路不漂移。

## 1. 最小必需 Topic

- `pose`：`/swarm/{platform_id}/nav/pose`
- `truth`：`/swarm/{platform_id}/truth/pose`
- `health`：`/swarm/{platform_id}/health`

默认模板常量定义见 `ros_protocol.py`。

## 2. 支持消息类型

- `pose`：`geometry_msgs/msg/PoseStamped`、`nav_msgs/msg/Odometry`
- `truth`：`geometry_msgs/msg/PoseStamped`、`nav_msgs/msg/Odometry`
- `health`：`std_msgs/msg/String`

## 3. 平台 ID 规则

优先级固定：

1. 从 topic 模板 `{platform_id}` 提取
2. 若 topic 无法提取，回退 `payload.platform_id`

## 4. 时间戳规则

优先级固定：

1. `header.stamp`
2. `payload.timestamp`
3. 本地接收时间（`local_receive_time`）

补充：

- `header.stamp == 0` 视为缺失，回退下一优先级
- 若新消息时间戳小于平台上次时间戳，判定为“时间回退”，丢弃并计数

## 5. 坐标系与单位

- 坐标系：`ENU`
- 位置单位：`meter`
- 速度单位：`meter_per_second`

## 6. Health 枚举

固定枚举集合：

- `OK`
- `TRACKING`
- `DEGRADED`
- `LOST`
- `OFFLINE`
- `DISCONNECTED`
- `UNKNOWN`

未知/乱码/空字符串统一归一到 `UNKNOWN`。

## 7. 缺字段降级规则

- `pose/truth` 缺位置字段：回退已有状态值，同时计入 `degraded` 计数
- `health` 缺状态字段：归一为 `UNKNOWN`，并按规则推导 `is_online`
- 时间戳缺失：按时间戳优先级回退

## 8. 动态发现收敛规则

- 发现平台后需满足最小激活消息数（默认 `1`）才向 UI 推送
- 平台总数有上限保护（默认 `120`）
- 单次轮询向 UI 推送有上限（默认 `80`）
- discovery 扫描周期默认 `1.0s`，可调

## 9. 可观测性分层指标

- ROS2 接入层：原始消息计数、最近消息时延、解析失败计数、类型不匹配计数
- 适配/状态层：成功写入次数、丢弃计数、时间回退计数、降级计数
- UI 层：当前展示平台数、告警数、刷新频率
