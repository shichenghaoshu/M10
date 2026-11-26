# 部署

当前固件必须使用官方 RKNPU2 1.0.0 资产。`prepare_models.sh` 固定到提交 `1346f96` 并生成 SHA256。Android 构建需要 arm64 可执行的 NDK；禁止把新版 `librknnrt.so` 覆盖到 `/vendor`。部署目录固定为 `/data/local/tmp/m10-vision`。

