# 打包、GitHub自动编译与部署说明

本文说明如何把 BOM 智能采集系统交付给客户使用，以及客户端和服务器分别需要什么环境。

## 一、推荐交付形态

推荐交付三件套：

```text
1. bom-system-windows-版本号.zip              # 客户现场直接运行
2. bom-system-source-版本号.zip               # 提交/备份到GitHub或现场留档
3. bom-system-paddleocr-models-版本号.zip     # PaddleOCR离线模型包，可用U盘拷贝
```

Windows 便携包结构：

```text
bom-system-windows-版本号.zip
├── start-bom.bat
├── start-bom-and-open-browser.bat
├── package-guide.md
└── server/
    ├── bom-server.exe
    ├── .env.example
    ├── .env                 # 首次启动脚本自动复制生成
    ├── data/                # SQLite数据库、FAISS索引、本地额度账本
    └── models/              # 可放PaddleOCR离线模型
```

客户双击 `start-bom-and-open-browser.bat` 后：

- 后端 EXE 在本机启动 FastAPI。
- 前端静态页面由同一个 EXE 托管。
- 浏览器打开 `http://127.0.0.1:8000`。
- 数据保存在 `server/data/`。

PaddleOCR离线模型包解压后，把其中的 `models` 文件夹复制到 Windows 便携包的 `server/` 下即可。

## 二、服务器端环境

### 1. 使用 EXE 便携包时

服务器或主机要求：

- Windows 10 / Windows 11 / Windows Server 2019 及以上。
- 64 位系统。
- 建议内存 8GB 以上；如果启用 PaddleOCR，建议 16GB。
- 磁盘预留 10GB 以上。
- 能访问局域网中审核人员的浏览器。

不需要客户安装：

- Python
- Node.js
- pnpm
- Git

可选需要：

- 如果使用百度OCR：服务器需要能访问百度OCR接口。
- 如果开启AI增强：服务器需要能访问 OpenAI 或中转站接口。

### 2. 源码开发/部署时

服务器需要：

- Python 3.11
- pip 或 uv
- Node.js 20+
- pnpm
- Visual C++ Runtime

启动命令：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

cd frontend
pnpm dev --host 0.0.0.0 --port 5173
```

生产环境如果不用 EXE，可以使用 `docker-compose.yml`。

## 三、客户端环境

客户端是浏览器，不需要安装桌面客户端。

推荐：

- Chrome 最新版
- Microsoft Edge 最新版
- 局域网能访问服务器 IP 和端口

访问方式：

```text
http://服务器IP:8000
```

语音录入要求：

- Chrome / Edge 支持最好。
- 浏览器需要允许麦克风权限。
- iOS Safari 支持有限，可能降级到文本输入。

## 四、配置说明

首次启动后，`server/.env` 会从 `.env.example` 自动复制。

默认配置：

```env
AI_ENABLED=false
DATABASE_URL=sqlite+aiosqlite:///./data/bom.db
PADDLEOCR_MODEL_DIR=
PADDLEOCR_ASCII_CACHE_DIR=
```

默认规则模式不需要 AI 接口，也可以完成：

- OCR识别
- 规则提取
- 本地物料匹配
- 人工审核
- 缺失物料处理
- Excel导出

如果要开启 AI 增强，优先在前端「设置」页配置：

- AI增强能力：开启
- 接口地址：例如 `https://fululai.cn/v1`
- 接口密钥：中转站或 OpenAI Key
- 聊天模型：例如 `gpt-5.5`
- 向量模型：例如 `text-embedding-3-small`
- 向量服务：国内部署可选阿里 `text-embedding-v4` 或百度 `embedding-v1`

注意：聊天模型不能替代向量模型。兼容接口需要可用的 `/v1/embeddings`；阿里和百度会走系统内置适配器，不要求它们伪装成 OpenAI 接口。

如果客户现场不能联网，建议提前准备 PaddleOCR 离线模型包。复制完成后在 `server/.env` 中配置：

```env
PADDLEOCR_MODEL_DIR=./models/paddleocr/whl
PADDLEOCR_ASCII_CACHE_DIR=C:\bom-system-cache\paddleocr\whl
```

说明：Windows 下 Paddle 推理对中文路径不稳定。系统检测到模型目录包含中文时，会自动复制一份到纯英文缓存目录再加载；默认缓存目录是当前用户目录下的 `.bom-system\paddleocr\whl`，也可以用 `PADDLEOCR_ASCII_CACHE_DIR` 手动指定。

## 五、本地手动打包

在 Windows 开发机执行：

```powershell
cd "D:\BOM 智能采集系统\bom-system"
.\scripts\package_windows.ps1 -Version local
```

输出：

```text
release/bom-system-windows-local.zip
```

打包脚本会自动：

1. 安装前端依赖。
2. 构建前端 `frontend/dist`。
3. 安装后端依赖。
4. 使用 PyInstaller 生成 `bom-server.exe`。
5. 把前端静态文件打进 EXE。
6. 生成启动脚本和压缩包。

打包源码包：

```powershell
.\scripts\package_source.ps1 -Version local
```

输出：

```text
release/bom-system-source-local.zip
```

打包 PaddleOCR 离线模型包：

```powershell
.\scripts\package_paddleocr_models.ps1 -Version local
```

输出：

```text
release/bom-system-paddleocr-models-local.zip
```

模型包会先下载 PaddleOCR 中文检测、识别和方向分类模型。此步骤需要构建机能联网访问 PaddleOCR 模型源。

## 六、GitHub 自动编译 EXE

仓库已提供 GitHub Actions 工作流：

```text
.github/workflows/windows-release.yml
```

触发方式：

- push 到 `main`
- 手动点击 `Run workflow`
- 创建 tag，例如 `v0.1.0`

手动运行时可以选择 `include_paddleocr_models=true`，同时生成 PaddleOCR 离线模型包。模型包较大，下载和上传时间会明显增加。

GitHub 会在 Windows Runner 上自动：

1. 安装 Python 3.11。
2. 安装 Node.js 20 和 pnpm。
3. 安装后端依赖。
4. 运行后端测试。
5. 构建前端。
6. 生成 Windows EXE 运行包。
7. 生成源码包。
8. 可选生成 PaddleOCR 离线模型包。
9. 上传所有 zip 到 Artifacts。
10. 如果是 tag，会创建 GitHub Release 并上传 zip。

## 七、客户部署步骤

1. 从 GitHub Actions Artifacts 或 Release 下载 `bom-system-windows-版本号.zip`。
   如果现场不能联网，也下载 `bom-system-paddleocr-models-版本号.zip`。
2. 解压到服务器，例如：

```text
D:\BOM智能采集系统
```

3. 如果使用 PaddleOCR 离线模型包，把模型包中的 `models` 文件夹复制到：

```text
D:\BOM智能采集系统\server\models
```

4. 编辑 `server/.env`：

```env
PADDLEOCR_MODEL_DIR=./models/paddleocr/whl
```

5. 双击 `start-bom-and-open-browser.bat`。
6. 打开 `http://127.0.0.1:8000` 确认页面正常。
7. 局域网其他电脑访问：

```text
http://服务器IP:8000
```

6. 首次使用先导入 ERP 物料 CSV。
7. 如果有 AI 或百度OCR密钥，到「设置」页配置。

## 八、数据备份

重要数据目录：

```text
server/data/
```

建议每天备份：

- `bom.db`
- `materials.faiss`
- `id_map.json`
- `baidu_ocr_usage.json`

迁移服务器时，把整个 `server/data/` 复制过去即可。

## 九、常见问题

### 1. 双击后窗口一闪而过

使用 `start-bom.bat`，它会保留窗口，方便查看错误。

### 2. 其他电脑访问不了

检查：

- Windows 防火墙是否放行端口 8000。
- 服务器和客户端是否在同一局域网。
- 使用的是服务器 IP，不是 `127.0.0.1`。

### 3. AI功能不能用

先关闭 AI 增强，使用规则模式。

如果要排查 AI：

- 确认接口地址以 `/v1` 结尾。
- 确认聊天模型能走 `/v1/chat/completions`。
- 确认向量模型能走 `/v1/embeddings`。
- 如果选择阿里或百度向量服务，确认对应密钥已保存，并在「物料」页重建AI匹配索引。

### 4. 百度OCR会不会产生费用

系统有本地免费额度保护，但最终额度以百度控制台为准。没有明确免费额度时，不要开启百度OCR表格识别。
