# services 模块说明

本目录用于存放 BOM 智能采集系统的业务逻辑服务。

后续模块会在这里放置 ERP 物料导入、OCR 识别、AI 语义匹配、审核协作和导出相关逻辑。

## 当前服务

- `material_service.py`：负责 ERP 物料 CSV 导入、OpenAI 向量生成、FAISS 索引构建和索引加载。
- `match_service.py`：负责物料命名的精确匹配、向量匹配、GPT候选判断、匹配结果落库、确认和拒绝操作。
- `ocr_service.py`：负责图像预处理、PaddleOCR识别、百度OCR表格识别、OCR文本归一化和GPT结构化提取。
- `export_service.py`：负责把已确认BOM、待处理项、缺失物料和操作日志生成多Sheet Excel导入包。

CSV 导入要求列名为：`编码`、`名称`、`规格`、`单位`、`类别`。

索引文件保存在 `backend/data/materials.faiss`，物料编码映射保存在 `backend/data/id_map.json`。

## 匹配结果落库

OCR 提取后的 BOM 数据会进入 `process_extracted_bom`。系统按置信度自动分类：`0.90` 及以上自动确认并更新 `name_mapping`，`0.70` 到 `0.89` 进入待审核队列，低于 `0.70` 或未匹配时同时写入 `missing_materials`。

待审核列表的候选物料保存在 `bom_items.candidates_json`，匹配来源保存在 `bom_items.match_level`，便于前端审核界面分页展示。

## BOM导出

`export_bom_to_excel(product_name, db)` 只导出指定产品中 `status=confirmed` 的记录到「BOM导入表」，并把 `pending/rejected` 条目放入「待处理项」。自动确认记录使用浅绿色背景，人工确认记录保持白色背景。

`export_all_pending_to_excel(db)` 复用同一套四Sheet结构，用于下载全量待处理汇总。

## 百度OCR费用保护

百度OCR表格识别只在配置了 `BAIDU_OCR_API_KEY` 和 `BAIDU_OCR_SECRET_KEY` 后才会调用。

系统参考百度“免费测试资源”文档做本地月度额度保护。文档说明成功调用和失败调用都会消耗免费测试资源，因此系统在发送百度请求前会先预占一次额度，避免超额后进入付费调用。

默认额度按账号类型计算：`BAIDU_OCR_ACCOUNT_TYPE=personal` 时表格文字识别V2为 500 次/月，`enterprise` 时为 1000 次/月。可用 `BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT` 覆盖本地保护值，并用 `BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER` 预留安全余量。达到保护线后，`mode=auto` 会回退到 PaddleOCR，`mode=baidu` 会返回友好错误。

已预留 `general_basic` 和 `handwriting` 两类百度接口额度配置，后续接入通用文字识别或手写文字识别时复用同一套本地额度账本。
