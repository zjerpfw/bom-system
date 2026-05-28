# BOM智能采集系统

## 项目简介

BOM智能采集系统用于帮助制造业企业把研发口述、纸质图纸、Excel打印件中的零件清单转成可导入ERP的标准BOM数据。

核心流程：

1. OCR识别图纸、表格或接收语音/文本录入。
2. AI语义匹配ERP物料主数据。
3. 人工审核待确认和缺失物料。
4. 导出可导入ERP的Excel文件。

技术栈：Python 3.11、FastAPI、SQLite、SQLAlchemy、PaddleOCR、百度OCR API、OpenAI Embedding、FAISS、GPT-4o-mini、Vue 3、Vite、Vant 4、openpyxl。

## 快速启动

1. 复制配置：`copy .env.example .env`，默认 `AI_ENABLED=false` 可先不填AI密钥；按需填写百度OCR密钥和 `API_KEY`。
2. 启动后端：`cd backend && .\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`。
3. 启动前端：`cd frontend && pnpm dev --host 127.0.0.1 --port 5173`。
4. 打开前端：`http://127.0.0.1:5173`。
5. 运行验收：`.\backend\.venv\Scripts\python.exe .\scripts\e2e_test.py`。

## Windows 打包

本地打包便携版：

```powershell
.\scripts\package_windows.ps1 -Version local
```

输出文件：

```text
release/bom-system-windows-local.zip
```

源码包：

```powershell
.\scripts\package_source.ps1 -Version local
```

PaddleOCR 离线模型包：

```powershell
.\scripts\package_paddleocr_models.ps1 -Version local
```

上传到 GitHub 后，`.github/workflows/windows-release.yml` 可自动在 Windows Runner 上构建 EXE 和源码包并上传 Artifacts；手动运行时可选择同时打包 PaddleOCR 离线模型；打 tag，例如 `v0.1.0`，会自动创建 Release。

## .env 配置说明

- `API_KEY`：可选。配置后所有 `/api/*` 请求必须带 `X-API-Key`。
- `AI_ENABLED`：是否启用AI增强，默认 `false`。关闭时系统走规则提取和本地匹配，不影响人工审核与导出。
- `OPENAI_API_KEY`：用于向量生成、GPT结构化提取和语义判断；也可以在前端「设置」页保存。
- `OPENAI_BASE_URL`：可选。使用OpenAI兼容中转站时填写，例如 `https://你的中转站域名/v1`；留空则使用官方默认地址。
- `OPENAI_CHAT_MODEL`：聊天/推理模型，默认 `gpt-4o-mini`，使用你的中转站时可填 `gpt-5.5`。
- `OPENAI_EMBEDDING_MODEL`：向量模型，默认 `text-embedding-3-small`。
- `PADDLEOCR_MODEL_DIR`：PaddleOCR离线模型目录，例如 EXE 包中填写 `./models/paddleocr/whl`。
- `PADDLEOCR_ASCII_CACHE_DIR`：可选。Windows 中文安装路径下 Paddle 推理可能打不开模型文件，系统会自动复制到纯英文缓存目录；可指定如 `C:\bom-system-cache\paddleocr\whl`。
- `BAIDU_OCR_APP_ID`、`BAIDU_OCR_API_KEY`、`BAIDU_OCR_SECRET_KEY`：百度OCR表格识别配置。
- `BAIDU_OCR_ACCOUNT_TYPE`：百度账号类型，默认 `personal`。
- `BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER`：百度OCR本地免费额度保护预留次数。
- `BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT`：可选，覆盖表格识别月度免费额度保护值。
- `BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT`：可选，预留通用文字识别额度配置。
- `BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT`：可选，预留手写识别额度配置。
- `DATABASE_URL`：SQLite连接串，默认 `sqlite+aiosqlite:///./data/bom.db`。

中转站示例：

```env
OPENAI_API_KEY=你的中转站密钥
OPENAI_BASE_URL=https://你的中转站域名/v1
OPENAI_CHAT_MODEL=gpt-5.5
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

注意：中转站必须兼容 OpenAI Python SDK 的 `/v1/chat/completions` 和 `/v1/embeddings` 接口，并支持你填写的聊天模型和向量模型。

运行后也可以在前端「设置」页切换 `规则模式 / AI增强模式`，并维护接口地址、密钥、聊天模型和向量模型。数据库中的系统配置优先级高于 `.env`，密钥只保存不明文回显。

## 接口文档

后端启动后访问 `http://127.0.0.1:8000/docs` 查看 Swagger UI。

图文使用说明见：[docs/USER_GUIDE.md](docs/USER_GUIDE.md)。

打包、GitHub自动编译EXE、客户部署和环境要求见：[docs/PACKAGE_GUIDE.md](docs/PACKAGE_GUIDE.md)。

主要接口模块：

- `/api/materials/*`：ERP物料导入、索引构建和统计。
- `/api/ocr/*`：图片OCR、百度表格OCR、文本/语音转写文本提取。
- `/api/match/*`：BOM匹配处理、确认、拒绝、缺失物料。
- `/api/review/*`：审核仪表盘、审核列表、批量确认、命名映射统计。
- `/api/export/*`：BOM Excel导出和待处理项汇总。
- `/api/settings/*`：系统运行配置、AI开关和模型配置。

## 语音录入

前端上传页提供「语音录入」Tab，当前实现使用浏览器内置免费方案，也就是 Web Speech API。Chrome 和 Edge 支持最好，iOS Safari 支持有限时会自动降级为文本输入框。

如需更高准确率，可配置 `OPENAI_API_KEY`，后续扩展为前端录制 WebM 音频，发送到后端，再调用 Whisper API 转写。当前版本不会调用付费语音服务。

## 已知限制

- 未开启 AI 或未配置 `OPENAI_API_KEY` 时，系统自动使用规则模式；向量索引、GPT提取和AI判断不会调用真实模型。
- 百度OCR免费额度由本地账本保护，但最终额度仍以百度控制台为准。
- SQLite适合单机轻量部署，多用户高并发场景建议迁移到PostgreSQL。
- 当前语音录入依赖浏览器 Web Speech API，不同浏览器识别质量差异较大。

## 后续规划

- 增加Whisper音频转写后端接口。
- 增加ERP系统的正式导入适配器。
- 增加审核操作的用户体系和权限分级。
- 增加生产部署的Nginx配置、健康检查和日志采集。
