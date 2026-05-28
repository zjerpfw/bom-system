# 项目记忆

最后更新：2026-05-28

## 当前状态

项目位于：

```text
D:\BOM 智能采集系统\bom-system
```

已经完成从 M1 到 M8 的主体开发，并完成整合测试脚本和图文使用说明。
已补充 Windows 便携包打包脚本、GitHub Actions 自动构建 EXE 工作流和客户部署环境说明。

当前系统可以在没有 OpenAI 可用接口的情况下运行：

- 默认 `AI_ENABLED=false`。
- OCR仍可走 PaddleOCR 和规则解析。
- 表格可在配置百度OCR后走百度表格识别。
- 物料匹配可走命名对照、精确匹配和本地规则候选。
- 人工审核、缺失物料、导出 Excel 不依赖 AI。

## 最近关键决策

用户找不到稳定可用的 AI/embedding 中转站接口，因此已将系统优化为：

```text
规则模式优先，AI增强可配置
```

不要拆成两个项目，也不要创建单独的“无AI版本”。统一通过系统配置切换。

## 系统配置中心

已新增数据库表：

```text
system_settings
```

已新增接口：

```text
GET  /api/settings/system
POST /api/settings/system
```

前端「设置」页已经可以维护：

- AI增强能力开关
- OpenAI兼容接口地址
- 接口密钥
- 聊天模型
- 向量模型
- 前端请求 API Key

密钥保存后不明文回显。

数据库中的 `system_settings` 优先级高于 `.env`。`.env` 只作为默认值。

## AI中转站测试记录

用户提供过 fululai.cn 中转站和密钥，只用于临时测试，不能写入项目文件。

已验证：

```text
OPENAI_BASE_URL=https://fululai.cn/v1
OPENAI_CHAT_MODEL=gpt-5.5
```

聊天模型最小请求通过：

```text
chat_ok=true
chat_model_returned=gpt-5.5
chat_content=pong
```

但 embedding 接口未通过：

```text
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
embedding_ok=false
404 page not found
```

`gpt-4o-audio-preview` 和 `gpt-4o-realtime-preview` 在该中转站 Chat Completions 最小请求返回 503，不适合作为当前项目主模型。

结论：

- 当前可使用 `gpt-5.5` 做聊天/提取/判断。
- 语义匹配仍需要可用 `/v1/embeddings` 和 embedding 模型。
- 没有 embedding 时保持规则模式。

## 已完成模块

### M1 项目初始化 + 数据库

- FastAPI 后端骨架。
- SQLite + SQLAlchemy async。
- `materials`、`bom_items`、`name_mapping`、`missing_materials`。
- 后续新增 `operation_logs`、`system_settings`。
- CORS、Swagger、统一响应格式。

### M2 ERP物料基准导入

- CSV 导入。
- 清洗全角半角和空行。
- code 重复更新。
- FAISS索引构建和加载。
- 注意：默认规则模式下构建向量索引会提示需要开启 AI。

### M3 OCR识别服务

- 图片预处理。
- PaddleOCR本地识别。
- 百度OCR表格识别。
- 百度免费额度本地保护。
- GPT提取和规则提取双模式。

### M4 AI语义匹配引擎

- 精确匹配。
- 规则候选匹配。
- embedding + FAISS 匹配。
- GPT候选判断。
- 匹配结果写库。
- 缺失物料队列。

### M5 审核协作接口

- 仪表盘。
- 审核列表。
- 批量确认。
- 手动改派。
- 命名映射统计。
- 操作日志。
- API Key 中间件。

### M6 前端审核界面

- Vue 3 + Vite + Vant 4。
- Dashboard。
- ReviewList。
- Upload。
- MissingList。
- Settings。

### M7 BOM导出

- `export_service.py` 生成 4 个 Sheet：
  - BOM导入表
  - 待处理项
  - 需新建物料
  - 操作日志
- 导出接口和前端导出按钮。

### M8 语音录入

- `VoiceCapture.vue`。
- Web Speech API 免费方案。
- Chrome/Edge最佳。
- iOS Safari有限支持，降级到文本输入。

## 重要文件

```text
backend/main.py
backend/app/core/config.py
backend/app/core/database.py
backend/app/core/paths.py
backend/app/api/router.py
backend/app/api/settings.py
backend/app/services/settings_service.py
backend/app/services/ocr_service.py
backend/app/services/match_service.py
backend/app/services/material_service.py
backend/app/services/export_service.py
frontend/src/api/index.ts
frontend/src/views/Settings.vue
frontend/src/views/ReviewList.vue
frontend/src/views/Upload.vue
docs/USER_GUIDE.md
docs/PACKAGE_GUIDE.md
scripts/e2e_test.py
scripts/package_windows.ps1
.github/workflows/windows-release.yml
```

## 常用验证命令

后端测试：

```powershell
cd "D:\BOM 智能采集系统\bom-system"
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

最近一次结果：

```text
38 passed
```

前端构建：

```powershell
cd "D:\BOM 智能采集系统\bom-system\frontend"
pnpm build
```

最近一次结果：构建成功。

设置接口烟测：

```text
POST /api/settings/system -> 200 0 False gpt-5.5
GET  /api/settings/system -> 200 0 gpt-5.5
```

打包路径测试：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_m10_packaging.py -q
```

本地 Windows 便携包打包：

```powershell
.\scripts\package_windows.ps1 -Version local
```

## 后续优先事项

1. 如果用户找到可用 embedding 接口，先只测试 `/v1/embeddings`，不要跑业务数据。
2. 可给系统配置页增加真正的“测试聊天接口”和“测试向量接口”按钮。
3. 可优化规则提取，对无空格 OCR 行做更强的名称/规格/数量拆分。
4. 可增加物料搜索接口，让审核页手动改派更方便。
5. 可增加用户体系，替代当前简单 API Key。
6. 如果 PyInstaller 打包 PaddleOCR 体积过大或缺隐式依赖，优先在 GitHub Actions 日志里补 hidden-import / collect-data。

## 注意事项

- 不要把用户提供的真实密钥写入 `.env`、README、测试或源码。
- 不要把项目重新写回 C 盘。
- 不要把 `gpt-4o-audio-preview`、`gpt-4o-realtime-preview` 当作当前 BOM 文本主模型。
- 没有 AI 接口时不要阻塞主流程，继续保持规则模式可用。
- 每次改动后，至少跑相关后端测试；涉及前端必须跑 `pnpm build`。
- EXE 运行时 `.env` 和数据目录在 `server/` 下，不再使用源码的 `backend/data/`。
