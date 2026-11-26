# 模型与版本报告

## 兼容边界

板端 RKNN Runtime 1.0.0、驱动 0.4.2。官方当前 `rknn_model_zoo` 的已发布版本最低为 1.5，并明确要求匹配同系列 RKNPU2 SDK；因此当前不能把新版 YOLOv8 RKNN 模型部署到这块固件，也不能静默切 CPU。

初始 NPU 验证采用官方 `airockchip/rknpu2` 提交 `1346f96`（2021-04-30，SDK 1.0.0）自带 `ssd_inception_v2.rknn`。它是 COCO 检测模型，可覆盖 person/cat/dog，用于验证真实 NPU 和端到端接口。YOLOv8n INT8 是固件升级后的正式目标。

模型 SHA256：`3aa23fc18e6f5f087c0aadc1e9828efe07cb0f792e0ce62e1ebd1e04e1905b62`。输入为 1×300×300×3 UINT8/NHWC；两个输出均为 INT8 affine quantization。真实板端结果：person 最高 0.9766、cat 0.9885、dog 0.9199。

模型文件下载/提取后由 `scripts/prepare_models.sh` 生成 SHA256 manifest。所有模型均不提交 Git。

官方旧提交中的 `Android/librknn_api/arm64-v8a/librknn_api.so` 只有 1 MiB，ELF 节表指向文件末尾之后，无法被现代 linker 使用。构建脚本只读地从目标机拉取完整 `/vendor/lib64/librknnrt.so` 作为链接输入；部署和运行仍使用板端原文件，绝不覆盖 Runtime。
