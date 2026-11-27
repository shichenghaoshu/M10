# Dreamupers 上游源码快照

来源：https://github.com/Dreamupers/rk3566-ipc-car-public

固定提交：`c6d6b428322cf0311b0059f7d5bdd287b4bf65a2`，MIT，Copyright (c) 2026 Xi Zhang。

`rk3566-ipc-car-public/` 保存原版 11 个文本文件，包括 Python、网页、媒体配置及许可证；不修改其内容。原仓库的 3 个 PNG 未复制，原 README 中的截图请到上游查看。

[UPSTREAM.json](UPSTREAM.json) 记录来源、提交、未包含资源及每个文件的 Git blob / SHA-256。`./m10.sh doctor` 会检查哈希。升级上游时重新核对许可、差异和测试，不自动跟随 main。

实际集成入口见 [一键复刻指南](../../docs/one-click.md)。原主程序不直接启动；M10 通过独立适配层复用驱动、页面与图传配置，不沿用原始硬编码 IP、全局 kill 或主机休眠路径。
