# API

除 `/` 外必须带 `X-M10-Token` 或 `Authorization: Bearer`。已实现 status/objects/events/config、搜索/跟随/停止/紧急停止、主人注册请求/取消/删除。未部署人脸模型时注册返回明确 409，不伪造成功；视频流未启动时返回 503。

