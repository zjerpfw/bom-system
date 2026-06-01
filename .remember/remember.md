# BOM智能采集系统记忆

最后更新：2026-06-01

## 当前状态

项目当前路径：

```text
D:\BOM\bom-system
```

不要再使用 C 盘旧目录，也不要回到 `D:\BOM 智能采集系统\bom-system`。

系统已经完成 M1 到 M8 主体开发、端到端测试脚本、图文使用说明、Windows 便携包打包脚本、GitHub Actions 自动构建 EXE 工作流和客户部署说明。

当前产品定位调整为：

```text
电脑端审核工作台优先，手机/平板用于拍照上传和临时审核补充
```

前端要保持桌面端左侧导航、顶部页面标题、宽屏分栏；移动端继续保留底部 TabBar。

## 最近关键决策

用户找不到稳定可用的 AI/embedding 中转站接口，因此系统保持：

```text
规则模式优先，AI增强可配置
```

不要拆成两个项目，也不要创建单独的“无AI版本”。统一通过系统配置切换。

`AI_ENABLED=false` 时必须能走规则模式完成：

- ERP物料导入
- OCR规则提取
- 命名对照、精确匹配、本地规则候选
- 人工审核
- 缺失物料处理
- Excel导出

## 系统配置中心

数据库表：

```text
system_settings
```

接口：

```text
GET  /api/settings/system
POST /api/settings/system
```

前端「设置」页维护：

- AI增强能力开关
- OpenAI兼容接口地址
- 接口密钥
- 聊天模型
- 向量模型和向量供应商
- 阿里 DashScope 向量配置
- 百度千帆向量配置
- 百度OCR App ID / API Key / Secret Key
- 百度OCR免费额度保护参数
- 前端请求 API Key

密钥保存后不明文回显。数据库 `system_settings` 优先级高于 `.env`，`.env` 只作为默认值。

## AI和中转站注意事项

用户提供过 fululai.cn 中转站和密钥，只用于临时测试，不能写入项目文件。

曾验证：

```text
OPENAI_BASE_URL=https://fululai.cn/v1
OPENAI_CHAT_MODEL=gpt-5.5
```

聊天模型最小请求通过，但 embedding 接口当时未通过：

```text
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
embedding_ok=false
404 page not found
```

结论：

- `gpt-5.5` 可作为聊天/提取/判断模型，前提是中转站继续可用。
- 语义匹配仍需要可用 embedding 接口和 embedding 模型。
- 没有 embedding 时保持规则模式。
- 聊天模型不能替代 embedding 模型。

后端 OpenAI 兼容响应必须通过：

```text
backend/app/core/openai_client.py
```

不要重新写死 `response.choices[0]`。中转站可能返回纯字符串、`choices`、`output_text` 或 Responses API `output`，OCR提取和匹配判断都要兼容。

## OCR注意事项

- PaddleOCR 离线模型放在 `offline/paddleocr`。
- Windows 打包时要继续兼容本地模型目录和中文路径。
- 百度OCR调用有本地免费额度保护，失败调用也按一次预占处理。
- 已增加拍照表格增强模式：表格区域裁切、透视矫正、对比度增强后再送百度表格OCR。
- 强反光、边缘裁切、严重倾斜仍可能导致漏行，应提示用户重新拍清晰照片。

## 前端注意事项

- 前端技术栈固定：Vue 3 + Vite + Vant 4。
- 系统主色是 `#1D9E75`，Vant primary 按钮不要退回默认蓝色。
- 全局提示必须可见：Vant Toast/Dialog/Notify 文字颜色、背景和层级要显式控制，不能出现空白提示框。
- 电脑端布局在 `frontend/src/App.vue` 和 `frontend/src/styles/main.css`。
- 上传、审核、设置、物料库、缺失物料页都要保持桌面可用，不要只按手机窄屏设计。

## 已完成模块

- M1 项目初始化 + 数据库
- M2 ERP物料基准导入
- M3 OCR识别服务：PaddleOCR、百度表格、拍照表格增强、规则/AI提取
- M4 AI语义匹配引擎：精确、规则、embedding、LLM判断、写库
- M5 审核协作接口：仪表盘、审核列表、批量确认、改派、日志、API Key
- M6 前端审核界面：Dashboard、ReviewList、Upload、MissingList、Settings、Materials
- M7 BOM导出：4 Sheet Excel
- M8 语音录入：Web Speech API 免费方案

## 重要文件

```text
backend/main.py
backend/app/core/config.py
backend/app/core/database.py
backend/app/core/openai_client.py
backend/app/core/paths.py
backend/app/api/router.py
backend/app/api/settings.py
backend/app/services/settings_service.py
backend/app/services/ocr_service.py
backend/app/services/match_service.py
backend/app/services/material_service.py
backend/app/services/export_service.py
frontend/src/App.vue
frontend/src/api/index.ts
frontend/src/styles/main.css
frontend/src/views/Settings.vue
frontend/src/views/ReviewList.vue
frontend/src/views/Upload.vue
frontend/src/views/Materials.vue
docs/USER_GUIDE.md
docs/PACKAGE_GUIDE.md
scripts/e2e_test.py
scripts/package_windows.ps1
.github/workflows/windows-release.yml
```

## 常用验证命令

后端测试：

```powershell
cd "D:\BOM\bom-system"
.\backend\.build-venv\Scripts\python.exe -m pytest backend\tests -q
```

前端构建：

```powershell
cd "D:\BOM\bom-system\frontend"
pnpm build
```

打包路径测试：

```powershell
.\backend\.build-venv\Scripts\python.exe -m pytest backend\tests\test_m10_packaging.py -q
```

本地 Windows 便携包打包：

```powershell
.\scripts\package_windows.ps1 -Version local
```

便携包发布路径在 `release/`，包名模式如：

```text
bom-system-windows-local-YYYYMMDD-*.zip
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
