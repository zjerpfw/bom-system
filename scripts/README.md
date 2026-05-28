# scripts 模块说明

本目录用于存放工具脚本。

后续会加入数据库初始化、ERP物料批量导入、FAISS索引重建等脚本。

## 当前脚本

- `sample_materials.csv`：ERP物料示例数据。
- `sample_bom.png`：OCR测试图片。
- `test_match.py`：三级物料匹配流程测试脚本。
- `export_test.py`：插入混合状态测试BOM数据，生成并校验Excel导出文件。
- `check_m8_voice.py`：检查语音录入组件、上传页Tab和文本提取接口接线。
- `check_integration_assets.py`：检查端到端测试脚本、根README和Docker编排文件是否齐全。
- `e2e_test.py`：离线模拟完整业务流程，导入20条物料、构建 `materials.faiss`、处理主控板V2 BOM、导出四Sheet Excel。
