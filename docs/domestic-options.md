# 幻尔与陆吾的替代选择

资料核对日期：2026-11-26。以下是技术选项，不是已经完成采购和迁移的 BOM。

| 选择 | 官方公开配置 | 对 M10 的参考价值 |
| --- | --- | --- |
| 幻尔 WonderDuck | RK3566 + AT32，HX-08LCM 磁编码舵机，标称 0.06 s / 60° | 双足 RL 开发参考；官方介绍 MuJoCo / PPO 路线，软件包范围与交付需确认 |
| 幻尔 HTS-35H | 35 kgf·cm @ 11.1 V，0.18 s / 60°，UART 115200，位置 / 电压 / 温度反馈 | 受力关节台架候选，尚未验证连续扭矩、带载速度与总线时序 |
| 陆吾 XGO-Rider2 | CM5 + ESP32、FOC 无刷轮毂、4.5 kgf·cm 磁编码总线舵机 | 更接近轮足形态；官方提供 LQR / SDK 相关说明，不能据此认定其完整 RL 训练源码已公开 |

当前 M10 优先保留差速底盘完成跟踪闭环。需要轮足验证时参考陆吾，需要双足强化学习开发时参考幻尔。品牌国产替代与芯片国产化分别评估：Rider2 使用树莓派 CM5。

WonderDuck 官网当时标注 12 月 7 日发货。所有标称参数需按电压、负载、温度和测量口径再次核验；不可仅按扭矩数值判定兼容。

来源：[WonderDuck](https://www.hiwonder.com/products/wonderduck)、[HTS-35H](https://www.hiwonder.com/products/hts-35h)、[XGO-Rider2](https://www.xgorobot.com/rider.html)。
