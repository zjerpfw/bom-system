# api 模块说明

本目录用于存放 FastAPI 路由。

当前包含基础健康检查接口：

- `GET /api/health`：返回统一格式的服务运行状态。
- `POST /api/materials/import`：上传 ERP 物料 CSV 并导入或更新物料主数据。
- `POST /api/materials/build-index`：重建物料向量和 FAISS 索引。
- `GET /api/materials/stats`：查看物料数量和索引状态。
- `POST /api/ocr/upload`：上传图片，支持 `mode=auto|paddle|baidu`，执行预处理、OCR识别和BOM结构提取。
- `POST /api/ocr/text`：接收手动文本或语音转写文本，执行BOM结构提取。
- `POST /api/match/process`：处理 OCR 提取后的 BOM 数据，执行匹配并写入审核队列。
- `GET /api/match/pending`：分页获取待审核匹配列表。
- `POST /api/match/confirm/{id}`：确认某条匹配并更新命名对照。
- `POST /api/match/reject/{id}`：拒绝某条匹配。
- `GET /api/match/missing`：分页获取缺失物料列表。
- `POST /api/match/create-missing/{id}`：标记缺失物料已在 ERP 新建。
- `GET /api/review/dashboard`：返回审核仪表盘统计数据。
- `GET /api/review/items`：按产品、状态和分页查询 BOM 审核条目。
- `POST /api/review/batch-confirm`：批量确认高置信度待审核条目。
- `POST /api/review/reassign/{id}`：手动指定某条 BOM 条目的系统物料编码。
- `GET /api/review/mapping-stats`：返回命名对照表统计和高频映射。
- `GET /api/export/bom/{product_name}`：下载某产品的 ERP 标准 BOM 导入 Excel 包。
- `GET /api/export/all-pending`：下载全部待处理项汇总 Excel 包。

后续模块会继续扩展导出和语音录入接口。
