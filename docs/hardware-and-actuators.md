# 硬件与执行器

## 当前底盘

现有验证平台使用 RK3566、ESP32-S3、TB6612 和两驱差速底盘。轮速目前采用开环 PWM。

现场正式候选的接线在 [M10 固件说明](../m10-hardware-test/docs/M10_MOTOR_FIRMWARE.md) 中。历史 README 和测试草图含旧引脚，不可混用。GPIO12 已用于 BIN2，不能同时作为 STBY。

已有记录确认轮子可动作，并在固件层修正了左轮极性。各方向真实物理语义和联合稳定性仍需逐项验证。串口 ACK 只证明通信或逻辑处理，不能证明轮子已正确运动。

## Beni 公开模型提供的参考

| 部位 | OpenBeni 仿真设置 |
| --- | --- |
| L1 / R1 | 位置目标，电机力矩限幅 1.375 N·m |
| L2 / R2 | 电机限幅 3.6 N·m，加入弹簧后的仿真上限 4.6 N·m |
| LW / RW | 速度目标，力矩限幅 0.6 N·m |
| 偏航云台 | 理想 PD，限幅 0.1 N·m |

这些是公开仿真参数，量产电机型号未在本次资料中披露，不能把它们当作电机额定规格，也不能用厂商标称 / 堵转扭矩直接替代。

替代件至少需要验证：持续负载、速度和反馈周期、通信延迟、死区、发热、供电裕量以及断连行为。

来源：[beni_robot.py](https://github.com/Mondo-Robotics/open-beni/blob/4545b86a131d05519050df11a424368ef9f06b4f/python/beni_rl/beni_robot.py)、[actuator.py](https://github.com/Mondo-Robotics/open-beni/blob/4545b86a131d05519050df11a424368ef9f06b4f/python/beni_rl/actuator.py)。
