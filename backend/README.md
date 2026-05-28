# backend 模块说明

本目录是 BOM 智能采集系统后端服务。

## 模块职责

- 提供 FastAPI 接口。
- 管理 SQLite 数据库连接。
- 定义物料、BOM条目、命名对照和缺失物料模型。
- 后续承载 OCR、AI匹配、审核协作和导出服务。

## 启动方式

```bash
uvicorn main:app --reload
```

启动时会自动创建数据库表。
