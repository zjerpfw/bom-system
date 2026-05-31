import asyncio
import json
import math
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable

import faiss
import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.paths import get_data_dir
from app.models.material import Material
from app.services.embedding_service import create_embeddings


DATA_DIR = get_data_dir()
FAISS_INDEX_PATH = DATA_DIR / "materials.faiss"
ID_MAP_PATH = DATA_DIR / "id_map.json"


def normalize_text(value) -> str:
    """清洗单元格文本，统一全角半角并去除首尾空格。"""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return text.strip()


def run_async(coro):
    """在同步服务函数中执行异步数据库操作。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("当前同步服务函数不能在运行中的事件循环内直接调用")


async def async_import_materials_from_csv(file_path: str) -> dict:
    """异步导入ERP物料CSV文件。"""
    result = {"total": 0, "success": 0, "skipped": 0, "errors": []}
    data_frame = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig").fillna("")
    required_columns = ["编码", "名称", "规格", "单位", "类别"]
    missing_columns = [column for column in required_columns if column not in data_frame.columns]
    if missing_columns:
        result["errors"].append(f"缺少列: {', '.join(missing_columns)}")
        return result

    rows = data_frame[required_columns].to_dict("records")
    async with AsyncSessionLocal() as session:
        for row_number, row in enumerate(rows, start=2):
            code = normalize_text(row["编码"])
            name = normalize_text(row["名称"])
            spec = normalize_text(row["规格"])
            unit = normalize_text(row["单位"])
            category = normalize_text(row["类别"])

            if not any([code, name, spec, unit, category]):
                continue

            result["total"] += 1
            if not code or not name:
                result["skipped"] += 1
                result["errors"].append(f"第{row_number}行缺少编码或名称")
                continue

            statement = insert(Material).values(
                code=code,
                name=name,
                spec=spec,
                unit=unit,
                category=category,
                source="erp_csv",
            )
            statement = statement.on_conflict_do_update(
                index_elements=[Material.code],
                set_={
                    "name": statement.excluded.name,
                    "spec": statement.excluded.spec,
                    "unit": statement.excluded.unit,
                    "category": statement.excluded.category,
                    "source": statement.excluded.source,
                },
            )
            await session.execute(statement)
            result["success"] += 1

        await session.commit()

    return result


def import_materials_from_csv(file_path: str) -> dict:
    """导入ERP物料CSV文件。"""
    return run_async(async_import_materials_from_csv(file_path))


def default_embedding_provider(texts: list[str]) -> list[list[float]]:
    """按系统配置生成文本向量。"""
    return create_embeddings(texts, text_type="document")


def normalize_vectors(vectors: list[list[float]]) -> np.ndarray:
    """归一化向量以支持内积相似度检索。"""
    array = np.array(vectors, dtype="float32")
    if array.size == 0:
        return array
    faiss.normalize_L2(array)
    return array


def write_faiss_index(index: faiss.Index, file_path: Path) -> None:
    """写入FAISS索引，兼容Windows中文路径。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".faiss") as temp_file:
        temp_path = Path(temp_file.name)
    try:
        faiss.write_index(index, str(temp_path))
        shutil.move(str(temp_path), file_path)
    finally:
        temp_path.unlink(missing_ok=True)


def read_faiss_index(file_path: Path) -> faiss.Index:
    """读取FAISS索引，兼容Windows中文路径。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".faiss") as temp_file:
        temp_path = Path(temp_file.name)
    try:
        shutil.copyfile(file_path, temp_path)
        return faiss.read_index(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)


async def async_build_embedding_index(
    embedding_provider: Callable[[list[str]], list[list[float]]] | None = None,
) -> None:
    """异步构建物料向量索引。"""
    provider = embedding_provider or default_embedding_provider
    if embedding_provider is None and not get_settings().ai_enabled:
        raise RuntimeError("AI功能未启用，无法构建向量索引；请在系统设置中开启AI并配置可用的向量接口")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Material).order_by(Material.code))
        materials = list(result.scalars().all())
        if not materials:
            index = faiss.IndexFlatIP(0)
            write_faiss_index(index, FAISS_INDEX_PATH)
            ID_MAP_PATH.write_text("{}", encoding="utf-8")
            return

        texts = [f"{material.name} {material.spec or ''}".strip() for material in materials]
        vectors = provider(texts)
        vector_array = normalize_vectors(vectors)
        index = faiss.IndexFlatIP(vector_array.shape[1])
        index.add(vector_array)

        id_map: dict[str, str] = {}
        for index_id, material in enumerate(materials):
            material.embedding_json = json.dumps(vectors[index_id], ensure_ascii=False)
            id_map[str(index_id)] = material.code

        await session.commit()

    write_faiss_index(index, FAISS_INDEX_PATH)
    ID_MAP_PATH.write_text(json.dumps(id_map, ensure_ascii=False, indent=2), encoding="utf-8")


def build_embedding_index(
    embedding_provider: Callable[[list[str]], list[list[float]]] | None = None,
) -> None:
    """构建物料向量索引。"""
    return run_async(async_build_embedding_index(embedding_provider=embedding_provider))


def load_index() -> tuple[faiss.Index | None, dict]:
    """加载FAISS索引和物料编码映射。"""
    if not FAISS_INDEX_PATH.exists() or not ID_MAP_PATH.exists():
        return None, {}
    index = read_faiss_index(FAISS_INDEX_PATH)
    id_map = json.loads(ID_MAP_PATH.read_text(encoding="utf-8"))
    return index, id_map


async def async_get_material_stats() -> dict:
    """查询物料统计和索引状态。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(Material))
        material_total = result.scalar_one()

    index_ready = FAISS_INDEX_PATH.exists() and ID_MAP_PATH.exists()
    index_count = 0
    if index_ready:
        index, _ = load_index()
        index_count = index.ntotal if index is not None else 0

    return {
        "material_total": material_total,
        "index_ready": index_ready,
        "index_count": index_count,
    }
