# frontend 模块说明

本目录用于存放 Vue 3、Vite 和 Vant 4 构建的移动端审核界面。

## 已实现页面

- `Dashboard`：审核仪表盘，展示待审核、已确认、缺失物料、自动通过率和产品进度。
- `ReviewList`：核心审核页，支持产品筛选、批量确认、候选物料改派和缺失标记。
- `Upload`：图纸或表格上传页，展示 OCR 提取预览并提交匹配。
- `MissingList`：缺失物料处理页，支持标记已在 ERP 新建。
- `Settings`：保存前端请求使用的 API Key，并提供缺失物料入口。

## 本地运行

```bash
pnpm install
pnpm dev
```

开发代理会将 `/api` 转发到 `http://localhost:8000`。
