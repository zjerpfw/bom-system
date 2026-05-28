import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal, init_db
from app.services import match_service
from app.services.match_service import batch_match, match_material
from app.services.material_service import load_index


def enable_offline_match_demo(vector_size: int) -> None:
    """无OpenAI密钥时使用本地替身验证流程。"""
    if os.getenv("OPENAI_API_KEY"):
        return

    match_service.create_embedding = lambda raw_name: [1.0] + [0.0] * max(vector_size - 1, 0)
    match_service.llm_judge = lambda raw_name, candidates: match_service.MatchResult(
        raw_name=raw_name,
        matched_code=candidates[0]["code"] if candidates else None,
        matched_name=candidates[0]["name"] if candidates else None,
        matched_spec=candidates[0]["spec"] if candidates else None,
        confidence=0.8 if candidates else 0.0,
        match_level="llm" if candidates else "none",
        candidates=candidates,
    )


async def main() -> None:
    """验证三级物料匹配流程。"""
    await init_db()
    material_index, material_id_map = load_index()
    enable_offline_match_demo(material_index.d if material_index is not None else 3)
    app_state = SimpleNamespace(material_index=material_index, material_id_map=material_id_map)
    async with AsyncSessionLocal() as session:
        exact_result = await match_material("六角螺钉", session, app_state)
        print("exact:", exact_result)

        batch_results = await batch_match(
            [{"raw_name": "六角螺钉"}, {"raw_name": "铜柱M3"}, {"raw_name": "未知叫法"}],
            session,
            app_state,
        )
        for result in batch_results:
            print("batch:", result)


if __name__ == "__main__":
    asyncio.run(main())
