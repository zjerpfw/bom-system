# models 模块说明

本目录用于存放 SQLAlchemy 数据库模型。

## 当前模型

- `Material`：ERP 物料主数据。
- `BomItem`：OCR 和 AI 匹配后的 BOM 条目，保存匹配状态、匹配层级和候选物料列表。
- `NameMapping`：研发叫法与系统物料名称的命名对照。
- `MissingMaterial`：AI 无法匹配时产生的缺失物料队列。
- `OperationLog`：审核确认、批量确认和手动改派等操作日志。

模型字段以英文变量名定义，中文业务含义通过类注释说明。
