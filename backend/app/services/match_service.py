import asyncio
import inspect
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import faiss
import numpy as np
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.openai_client import create_openai_client, extract_text_from_openai_response
from app.models.bom_item import BomItem
from app.models.material import Material
from app.models.missing_material import MissingMaterial
from app.models.name_mapping import NameMapping
from app.services.embedding_service import create_embedding as create_provider_embedding


MATCH_SYSTEM_PROMPT = """
你是工厂物料命名专家，帮助判断研发的叫法对应系统中的哪个物料。
规则：
- 只能从候选列表中选择，不能创造新选项
- 如果没有合适的候选，返回 matched_code: null
- confidence 表示你的把握程度（0.0-1.0）
输出JSON：{"matched_code": "编码或null", "confidence": 0.85, "reason": "简短理由"}
"""
EMBEDDING_ACCEPT_SCORE = 0.85
EMBEDDING_SCORE_GAP = 0.08
RULE_ACCEPT_SCORE = 0.74
FUZZY_ACCEPT_SCORE = 0.85


def call_create_openai_client(api_key: str | None = None, base_url: str | None = None):
    """兼容测试替换后的OpenAI客户端工厂。"""
    if api_key is None and base_url is None:
        return create_openai_client()
    return create_openai_client(api_key=api_key, base_url=base_url)


def call_create_embedding(raw_name: str, runtime_settings=None) -> list[float]:
    """兼容测试替换后的向量函数。"""
    if runtime_settings is None:
        return create_embedding(raw_name)
    return create_embedding(raw_name, runtime_settings=runtime_settings)


@dataclass
class MatchResult:
    raw_name: str
    matched_code: str | None
    matched_name: str | None
    matched_spec: str | None
    confidence: float
    match_level: str
    candidates: list[dict]


def call_llm_judge(raw_name: str, candidates: list[dict], runtime_settings=None) -> MatchResult:
    """兼容测试替换后的LLM判断函数。"""
    if runtime_settings is None:
        return llm_judge(raw_name, candidates)
    return llm_judge(raw_name, candidates, runtime_settings=runtime_settings)


def create_embedding(raw_name: str, runtime_settings=None) -> list[float]:
    """按系统配置生成物料名称向量。"""
    return create_provider_embedding(raw_name, runtime_settings=runtime_settings, text_type="query")


def normalize_query_vector(vector: list[float]) -> np.ndarray:
    """归一化查询向量。"""
    array = np.array([vector], dtype="float32")
    faiss.normalize_L2(array)
    return array


def strip_markdown_json(content: str) -> str:
    """去除LLM返回中的markdown代码块。"""
    text = content.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


async def exact_match(raw_name: str, db: AsyncSession) -> MatchResult | None:
    """先查命名对照，再查物料名称精确匹配。"""
    mapping_result = await db.execute(
        select(NameMapping)
        .where(NameMapping.raw_name == raw_name)
        .order_by(desc(NameMapping.used_count), desc(NameMapping.updated_at))
        .limit(1)
    )
    mapping = mapping_result.scalar_one_or_none()
    if mapping:
        return MatchResult(
            raw_name=raw_name,
            matched_code=mapping.system_code,
            matched_name=mapping.system_name,
            matched_spec=mapping.spec,
            confidence=1.0,
            match_level="exact",
            candidates=[],
        )

    material_result = await db.execute(
        select(Material).where(or_(Material.code == raw_name, Material.name == raw_name)).limit(1)
    )
    material = material_result.scalar_one_or_none()
    if material:
        return MatchResult(
            raw_name=raw_name,
            matched_code=material.code,
            matched_name=material.name,
            matched_spec=material.spec,
            confidence=1.0,
            match_level="exact",
            candidates=[],
        )
    return None


async def get_materials_by_code(db: AsyncSession, codes: list[str]) -> dict[str, Material]:
    """按物料编码批量查询物料。"""
    if not codes:
        return {}
    result = await db.execute(select(Material).where(Material.code.in_(codes)))
    materials = result.scalars().all()
    return {material.code: material for material in materials}


def normalize_match_text(value: str | None) -> str:
    """规范化匹配文本。"""
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = text.replace("×", "x").replace("*", "x")
    return re.sub(r"[\s\-_/（）()]+", "", text)


def compact_match_tokens(value: str | None) -> set[str]:
    """提取用于模糊匹配的数字、字母和中文片段。"""
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = text.replace("×", "x").replace("*", "x")
    return set(re.findall(r"[a-z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]+", text))


def sequence_similarity(left: str, right: str) -> float:
    """计算两个短文本的序列相似度。"""
    if not left or not right:
        return 0.0
    return len(set(left) & set(right)) / max(len(set(left) | set(right)), 1)


def token_similarity(raw_name: str, material: Material) -> float:
    """计算本地规则匹配分数。"""
    raw_text = normalize_match_text(raw_name)
    name_text = normalize_match_text(material.name)
    spec_text = normalize_match_text(material.spec)
    code_text = normalize_match_text(material.code)
    if not raw_text or not name_text:
        return 0.0

    if raw_text == code_text:
        return 1.0
    if code_text and code_text in raw_text:
        return 0.96

    score = 0.0
    if raw_text == name_text:
        score += 0.86
    elif name_text in raw_text or raw_text in name_text:
        score += 0.68
    else:
        score += sequence_similarity(raw_text, name_text) * 0.56

    if spec_text and spec_text in raw_text:
        score += 0.22
    else:
        raw_tokens = compact_match_tokens(raw_name)
        spec_tokens = compact_match_tokens(material.spec)
        if raw_tokens and spec_tokens:
            score += min(len(raw_tokens & spec_tokens) / max(len(spec_tokens), 1), 1.0) * 0.18

    return round(min(score, 0.96), 4)


async def rule_match(raw_name: str, db: AsyncSession, top_k: int = 5) -> list[dict]:
    """无AI模式下用名称和规格做本地候选匹配。"""
    normalized_raw = normalize_match_text(raw_name)
    if not normalized_raw:
        return []
    result = await db.execute(
        select(Material)
        .where(or_(Material.name.contains(raw_name), Material.spec.contains(raw_name)))
        .limit(50)
    )
    materials = list(result.scalars().all())
    if len(materials) < top_k:
        all_result = await db.execute(select(Material).limit(500))
        material_by_code = {material.code: material for material in materials}
        for material in all_result.scalars().all():
            material_by_code.setdefault(material.code, material)
        materials = list(material_by_code.values())

    candidates = []
    for material in materials:
        score = token_similarity(raw_name, material)
        if score <= 0:
            continue
        candidates.append(
            {
                "code": material.code,
                "name": material.name,
                "spec": material.spec,
                "score": score,
            }
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:top_k]


async def fuzzy_match(raw_name: str, db: AsyncSession, top_k: int = 5) -> list[dict]:
    """用本地准确和模糊规则生成候选物料。"""
    return await rule_match(raw_name, db, top_k=top_k)


def should_accept_fuzzy(candidates: list[dict]) -> bool:
    """判断本地模糊匹配是否足够明确。"""
    if not candidates:
        return False
    first_score = float(candidates[0].get("score") or 0.0)
    second_score = float(candidates[1].get("score") or 0.0) if len(candidates) > 1 else 0.0
    return first_score >= FUZZY_ACCEPT_SCORE and (first_score - second_score) >= 0.05


async def embedding_match(raw_name: str, db: AsyncSession, app_state, top_k: int = 5) -> list[dict]:
    """使用OpenAI向量和FAISS索引查找候选物料。"""
    index = getattr(app_state, "material_index", None)
    id_map = getattr(app_state, "material_id_map", None) or {}
    if index is None or not id_map or index.ntotal == 0:
        return []

    runtime_settings = getattr(app_state, "runtime_settings", None)
    query_vector = normalize_query_vector(call_create_embedding(raw_name, runtime_settings=runtime_settings))
    search_count = min(top_k, index.ntotal)
    scores, indexes = index.search(query_vector, search_count)
    candidate_codes = []
    score_by_code = {}
    for score, index_id in zip(scores[0], indexes[0]):
        if int(index_id) < 0:
            continue
        code = id_map.get(str(int(index_id)))
        if not code:
            continue
        candidate_codes.append(code)
        score_by_code[code] = float(max(0.0, min(1.0, score)))

    material_by_code = await get_materials_by_code(db, candidate_codes)
    candidates = []
    for code in candidate_codes:
        material = material_by_code.get(code)
        if not material:
            continue
        candidates.append(
            {
                "code": material.code,
                "name": material.name,
                "spec": material.spec,
                "score": score_by_code[code],
            }
        )
    return candidates


def llm_judge(raw_name: str, candidates: list[dict], runtime_settings=None) -> MatchResult:
    """调用GPT判断候选物料。"""
    if not candidates:
        return MatchResult(raw_name, None, None, None, 0.0, "none", [])

    settings = get_settings()
    chat_model = runtime_settings.openai_chat_model if runtime_settings else settings.openai_chat_model
    api_key = runtime_settings.openai_api_key if runtime_settings else None
    base_url = runtime_settings.openai_base_url if runtime_settings else None
    client = call_create_openai_client(api_key=api_key, base_url=base_url)
    user_content = json.dumps({"raw_name": raw_name, "candidates": candidates}, ensure_ascii=False)
    response = client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    content = extract_text_from_openai_response(response) or "{}"
    data = json.loads(strip_markdown_json(content))
    matched_code = data.get("matched_code")
    confidence = float(data.get("confidence") or 0.0)
    selected = next((candidate for candidate in candidates if candidate.get("code") == matched_code), None)
    if not selected:
        return MatchResult(raw_name, None, None, None, 0.0, "llm", candidates)

    return MatchResult(
        raw_name=raw_name,
        matched_code=selected.get("code"),
        matched_name=selected.get("name"),
        matched_spec=selected.get("spec"),
        confidence=confidence,
        match_level="llm",
        candidates=candidates,
    )


def should_accept_embedding(candidates: list[dict]) -> bool:
    """判断向量匹配结果是否足够明确。"""
    if not candidates:
        return False
    first_score = float(candidates[0].get("score") or 0.0)
    second_score = float(candidates[1].get("score") or 0.0) if len(candidates) > 1 else 0.0
    return first_score > EMBEDDING_ACCEPT_SCORE and (first_score - second_score) >= EMBEDDING_SCORE_GAP


async def match_material(raw_name: str, db: AsyncSession, app_state) -> MatchResult:
    """执行三级物料匹配。"""
    exact_result = await exact_match(raw_name, db)
    if exact_result:
        return exact_result

    ai_enabled = getattr(app_state, "ai_enabled", None)
    runtime_settings = getattr(app_state, "runtime_settings", None)
    if ai_enabled is None and runtime_settings is not None:
        ai_enabled = runtime_settings.ai_enabled
    if ai_enabled is None:
        ai_enabled = True

    fuzzy_candidates = await fuzzy_match(raw_name, db, top_k=5)
    if should_accept_fuzzy(fuzzy_candidates):
        best = fuzzy_candidates[0]
        return MatchResult(
            raw_name=raw_name,
            matched_code=best.get("code"),
            matched_name=best.get("name"),
            matched_spec=best.get("spec"),
            confidence=float(best.get("score") or 0.0),
            match_level="fuzzy",
            candidates=fuzzy_candidates,
        )

    if not ai_enabled:
        if fuzzy_candidates and float(fuzzy_candidates[0].get("score") or 0) >= RULE_ACCEPT_SCORE:
            best = fuzzy_candidates[0]
            return MatchResult(
                raw_name=raw_name,
                matched_code=best.get("code"),
                matched_name=best.get("name"),
                matched_spec=best.get("spec"),
                confidence=float(best.get("score") or 0.0),
                match_level="rule",
                candidates=fuzzy_candidates,
            )
        return MatchResult(raw_name, None, None, None, 0.0, "none", fuzzy_candidates)

    candidate_result = embedding_match(raw_name, db, app_state, top_k=5)
    candidates = await candidate_result if inspect.isawaitable(candidate_result) else candidate_result
    if should_accept_embedding(candidates):
        best = candidates[0]
        return MatchResult(
            raw_name=raw_name,
            matched_code=best.get("code"),
            matched_name=best.get("name"),
            matched_spec=best.get("spec"),
            confidence=float(best.get("score") or 0.0),
            match_level="embedding",
            candidates=candidates,
        )

    if candidates:
        llm_result = call_llm_judge(raw_name, candidates, runtime_settings=runtime_settings)
        if llm_result.matched_code:
            return llm_result

    if fuzzy_candidates and float(fuzzy_candidates[0].get("score") or 0) >= RULE_ACCEPT_SCORE:
        best = fuzzy_candidates[0]
        return MatchResult(
            raw_name=raw_name,
            matched_code=best.get("code"),
            matched_name=best.get("name"),
            matched_spec=best.get("spec"),
            confidence=float(best.get("score") or 0.0),
            match_level="rule",
            candidates=fuzzy_candidates,
        )

    return MatchResult(
        raw_name=raw_name,
        matched_code=None,
        matched_name=None,
        matched_spec=None,
        confidence=0.0,
        match_level="none",
        candidates=candidates or fuzzy_candidates,
    )


def get_item_raw_name(item: dict) -> str:
    """从BOM条目中取待匹配名称。"""
    return item.get("raw_name") or item.get("material_name") or item.get("name") or ""


async def batch_match(items: list[dict], db: AsyncSession, app_state) -> list[MatchResult]:
    """并发批量匹配，限制最大并发为5。"""
    semaphore = asyncio.Semaphore(5)

    async def match_one(item: dict) -> MatchResult:
        async with semaphore:
            raw_name = get_item_raw_name(item)
            return await match_material(raw_name, db, app_state)

    return await asyncio.gather(*(match_one(item) for item in items))


def parse_decimal(value) -> Decimal | None:
    """将数值安全转换为Decimal。"""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def serialize_candidates(candidates: list[dict]) -> str:
    """序列化候选物料列表。"""
    return json.dumps(candidates or [], ensure_ascii=False)


def deserialize_candidates(candidates_json: str | None) -> list[dict]:
    """反序列化候选物料列表。"""
    if not candidates_json:
        return []
    try:
        data = json.loads(candidates_json)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


async def upsert_name_mapping(
    raw_name: str,
    system_code: str,
    system_name: str,
    spec: str | None,
    reviewer: str | None,
    db: AsyncSession,
) -> None:
    """新增或更新命名对照。"""
    result = await db.execute(
        select(NameMapping).where(NameMapping.raw_name == raw_name, NameMapping.system_code == system_code).limit(1)
    )
    mapping = result.scalar_one_or_none()
    if mapping:
        mapping.system_name = system_name
        mapping.spec = spec
        mapping.confirmed_by = reviewer or mapping.confirmed_by
        mapping.used_count += 1
        mapping.updated_at = datetime.now(timezone.utc)
        return

    db.add(
        NameMapping(
            raw_name=raw_name,
            system_code=system_code,
            system_name=system_name,
            spec=spec,
            confirmed_by=reviewer,
            used_count=1,
        )
    )


def build_missing_material(item: dict, match_result: MatchResult) -> MissingMaterial:
    """构造缺失物料队列记录。"""
    raw_name = match_result.raw_name or get_item_raw_name(item)
    return MissingMaterial(
        raw_name=raw_name,
        ai_suggested_name=item.get("name") or raw_name,
        ai_suggested_spec=item.get("spec"),
        ai_suggested_unit=item.get("unit"),
        ai_suggested_category=item.get("category"),
        status="pending",
    )


def build_bom_item(
    item: dict,
    product_name: str,
    match_result: MatchResult,
    status: str,
) -> BomItem:
    """构造BOM匹配落库记录。"""
    return BomItem(
        product_name=product_name,
        product_code=item.get("product_code"),
        material_code=match_result.matched_code,
        material_name=match_result.matched_name or item.get("name"),
        raw_name=match_result.raw_name or get_item_raw_name(item),
        quantity=parse_decimal(item.get("quantity")),
        unit=item.get("unit"),
        level=item.get("level"),
        confidence=parse_decimal(match_result.confidence),
        match_level=match_result.match_level,
        candidates_json=serialize_candidates(match_result.candidates),
        status=status,
    )


async def process_extracted_bom(extracted: dict, product_name: str, db: AsyncSession, app_state) -> dict:
    """处理OCR提取的BOM，写入匹配和审核数据。"""
    items = extracted.get("items") or []
    final_product_name = product_name or extracted.get("product") or ""
    match_results = await batch_match(items, db, app_state)
    stats = {"auto_confirmed": 0, "pending_review": 0, "missing": 0, "total": len(items)}

    for item, match_result in zip(items, match_results):
        is_missing = match_result.match_level == "none" or match_result.confidence < 0.70
        is_confirmed = bool(match_result.matched_code) and match_result.confidence >= 0.90 and not is_missing
        status = "confirmed" if is_confirmed else "pending"
        db.add(build_bom_item(item, final_product_name, match_result, status))

        if is_confirmed:
            stats["auto_confirmed"] += 1
            await upsert_name_mapping(
                match_result.raw_name,
                match_result.matched_code or "",
                match_result.matched_name or "",
                match_result.matched_spec,
                "auto",
                db,
            )
        else:
            stats["pending_review"] += 1

        if is_missing:
            stats["missing"] += 1
            db.add(build_missing_material(item, match_result))

    await db.commit()
    return stats


async def confirm_match(bom_item_id: int, system_code: str, reviewer: str, db: AsyncSession) -> None:
    """确认BOM条目匹配结果。"""
    bom_item = await db.get(BomItem, bom_item_id)
    if not bom_item:
        raise ValueError("BOM条目不存在")

    material_result = await db.execute(select(Material).where(Material.code == system_code).limit(1))
    material = material_result.scalar_one_or_none()
    if not material:
        raise ValueError("物料编码不存在")

    bom_item.status = "confirmed"
    bom_item.material_code = material.code
    bom_item.material_name = material.name
    bom_item.reviewer = reviewer
    bom_item.reviewed_at = datetime.now(timezone.utc)
    await upsert_name_mapping(bom_item.raw_name, material.code, material.name, material.spec, reviewer, db)
    await db.commit()


async def reject_match(bom_item_id: int, reviewer: str, db: AsyncSession) -> None:
    """拒绝BOM条目匹配结果。"""
    bom_item = await db.get(BomItem, bom_item_id)
    if not bom_item:
        raise ValueError("BOM条目不存在")
    bom_item.status = "rejected"
    bom_item.reviewer = reviewer
    bom_item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
