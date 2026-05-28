# CLAUDE.md

本文件给后续接手本仓库的 Claude/Codex 使用。请优先遵守用户最新要求，其次遵守本文件。

## 项目定位

这是一个「BOM智能采集系统」，用于制造业场景：

1. 将研发口述、纸质图纸、Excel打印件中的BOM转成结构化数据。
2. 与ERP物料主数据做命名匹配。
3. 让研发/审核员在移动端确认。
4. 导出ERP可导入的Excel。

项目路径固定在：

```text
D:\BOM 智能采集系统\bom-system
```

不要再把文件写到 C 盘旧目录。

## 技术栈约束

不得随意更换技术栈：

- 后端：Python 3.11 + FastAPI + SQLite + SQLAlchemy async
- OCR：PaddleOCR 本地识别 + 百度OCR表格识别
- AI：OpenAI兼容接口、`text-embedding-3-small`、FAISS、聊天模型可配置
- 前端：Vue 3 + Vite + Vant 4
- 导出：openpyxl
- 包管理：后端 uv/pip，前端 pnpm

## 代码规范

- 注释使用中文。
- 变量名、函数名、类名使用英文。
- 配置项统一从 `.env` 或数据库系统配置读取，不硬编码密钥。
- 所有 API 返回统一格式：

```json
{"code": 0, "msg": "ok", "data": {}}
```

- 每个模块目录应保留 `README.md` 说明。
- 后端使用异步 SQLAlchemy 会话，接口依赖 `get_db()`。
- 手工编辑文件时优先使用补丁方式，避免误改无关文件。

## 运行命令

后端：

```powershell
cd "D:\BOM 智能采集系统\bom-system\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd "D:\BOM 智能采集系统\bom-system\frontend"
pnpm dev --host 127.0.0.1 --port 5173
```

后端测试：

```powershell
cd "D:\BOM 智能采集系统\bom-system"
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

前端构建：

```powershell
cd "D:\BOM 智能采集系统\bom-system\frontend"
pnpm build
```

端到端脚本：

```powershell
cd "D:\BOM 智能采集系统\bom-system"
.\backend\.venv\Scripts\python.exe .\scripts\e2e_test.py
```

Windows便携包打包：

```powershell
cd "D:\BOM 智能采集系统\bom-system"
.\scripts\package_windows.ps1 -Version local
```

## 配置策略

`.env` 是启动默认值，数据库 `system_settings` 是运行时覆盖值。数据库配置优先于 `.env`。

关键配置：

```env
API_KEY=
AI_ENABLED=false
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
DATABASE_URL=sqlite+aiosqlite:///./data/bom.db
```

当前系统支持无 AI 规则模式：

- `AI_ENABLED=false` 时不调用 OpenAI。
- OCR文本提取走规则解析。
- 物料匹配走命名对照、精确匹配和本地规则候选。
- 审核、缺失物料、导出仍可正常使用。

AI增强模式：

- 在前端「设置」页开启。
- 配置接口地址、API Key、聊天模型、向量模型。
- 中转站必须兼容 `/v1/chat/completions` 和 `/v1/embeddings`。
- 聊天模型不能替代 embedding 模型。

不要把真实 API Key 写入仓库。

## 关键后端模块

- `backend/main.py`：FastAPI入口、CORS、启动建表、API Key中间件。
- `backend/app/core/config.py`：读取 `.env` 默认配置。
- `backend/app/core/database.py`：异步数据库引擎、`get_db()`、初始化表。
- `backend/app/core/paths.py`：源码和EXE打包环境的 `.env`、`data/`、前端静态文件路径适配。
- `backend/app/models/`：数据库模型。
- `backend/app/api/router.py`：统一注册 API 路由。
- `backend/app/services/material_service.py`：ERP物料导入、embedding、FAISS索引。
- `backend/app/services/ocr_service.py`：图像预处理、PaddleOCR、百度OCR、规则/AI提取。
- `backend/app/services/match_service.py`：精确匹配、规则匹配、embedding匹配、LLM判断、匹配写库。
- `backend/app/services/settings_service.py`：系统配置中心。
- `backend/app/services/export_service.py`：Excel导出。

## 关键前端模块

- `frontend/src/api/index.ts`：Axios实例和接口封装。
- `frontend/src/views/Dashboard.vue`：仪表盘和产品导出入口。
- `frontend/src/views/ReviewList.vue`：核心审核页。
- `frontend/src/views/Upload.vue`：图片/表格上传和语音录入入口。
- `frontend/src/views/MissingList.vue`：缺失物料处理。
- `frontend/src/views/Settings.vue`：API Key、AI开关、接口地址、模型配置。
- `frontend/src/components/VoiceCapture.vue`：浏览器 Web Speech API 语音录入。

## 数据库表

当前主要表：

- `materials`
- `bom_items`
- `name_mapping`
- `missing_materials`
- `operation_logs`
- `system_settings`

SQLite文件、FAISS索引和本地使用账本放在 `backend/data/`。
EXE便携包运行时放在 `server/data/`。

## 已知注意事项

- 项目当前目录可能不是 Git 仓库，`git status` 可能只显示 `?? ./`。
- Windows 中文路径下 FAISS 读写已做临时文件兼容，改动时不要破坏。
- 百度OCR调用有本地免费额度保护，失败调用也按一次预占处理。
- 测试环境偶尔出现 aiosqlite event loop closed warning；目前测试能通过，不代表功能失败。
- 前端是手机/平板审核工具，按钮要足够大，最小字号保持 16px 左右。

## 完成工作前检查

涉及后端逻辑时至少运行：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

涉及前端时至少运行：

```powershell
cd frontend
pnpm build
```

如果改动 OCR、AI、导出或端到端流程，补跑：

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\e2e_test.py
```

如果改动打包、运行路径或部署说明，补跑：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_m10_packaging.py -q
```
