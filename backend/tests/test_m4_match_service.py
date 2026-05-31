import json
import sys
from pathlib import Path
from types import SimpleNamespace

import faiss
import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest_asyncio.fixture
async def test_session(tmp_path):
    from app.core.database import Base
    from app.models.material import Material
    from app.models.name_mapping import NameMapping

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'match.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        session.add_all(
            [
                Material(code="M001", name="铜柱", spec="M3x10", unit="个", category="五金"),
                Material(code="M002", name="螺钉", spec="M6x20", unit="个", category="五金"),
                NameMapping(raw_name="铜柱子", system_code="M001", system_name="铜柱", spec="M3x10", used_count=9),
                NameMapping(raw_name="铜柱子", system_code="M002", system_name="螺钉", spec="M6x20", used_count=1),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_exact_match_prefers_name_mapping_usage(test_session):
    from app.services.match_service import exact_match

    result = await exact_match("铜柱子", test_session)

    assert result.raw_name == "铜柱子"
    assert result.matched_code == "M001"
    assert result.matched_name == "铜柱"
    assert result.matched_spec == "M3x10"
    assert result.confidence == 1.0
    assert result.match_level == "exact"


@pytest.mark.asyncio
async def test_exact_match_falls_back_to_material_name(test_session):
    from app.services.match_service import exact_match

    result = await exact_match("螺钉", test_session)

    assert result.matched_code == "M002"
    assert result.matched_name == "螺钉"
    assert result.match_level == "exact"


@pytest.mark.asyncio
async def test_exact_match_supports_material_code(test_session):
    from app.services.match_service import exact_match

    result = await exact_match("M001", test_session)

    assert result.matched_code == "M001"
    assert result.matched_name == "铜柱"
    assert result.match_level == "exact"


@pytest.mark.asyncio
async def test_match_material_uses_local_fuzzy_before_ai(test_session, monkeypatch):
    from app.services import match_service

    def fail_embedding(raw_name, db, app_state, top_k=5):
        raise AssertionError("本地模糊命中时不应调用向量接口")

    def fail_llm(raw_name, candidates):
        raise AssertionError("本地模糊命中时不应调用LLM")

    monkeypatch.setattr(match_service, "embedding_match", fail_embedding)
    monkeypatch.setattr(match_service, "llm_judge", fail_llm)

    result = await match_service.match_material(
        "铜柱 M3×10",
        test_session,
        SimpleNamespace(ai_enabled=True),
    )

    assert result.matched_code == "M001"
    assert result.match_level == "fuzzy"
    assert result.confidence >= 0.85


@pytest.mark.asyncio
async def test_embedding_match_uses_faiss_and_material_lookup(test_session, monkeypatch):
    from app.services import match_service
    from app.models.material import Material

    index = faiss.IndexFlatIP(3)
    vectors = np.array([[1.0, 0.0, 0.0], [0.2, 0.8, 0.0]], dtype="float32")
    faiss.normalize_L2(vectors)
    index.add(vectors)
    app_state = SimpleNamespace(material_index=index, material_id_map={"0": "M001", "1": "M002"})

    monkeypatch.setattr(match_service, "create_embedding", lambda raw_name: [1.0, 0.0, 0.0])

    candidates = await match_service.embedding_match("铜柱", test_session, app_state, top_k=2)

    assert candidates[0]["code"] == "M001"
    assert candidates[0]["name"] == "铜柱"
    assert candidates[0]["spec"] == "M3x10"
    assert candidates[0]["score"] > candidates[1]["score"]


def test_llm_judge_selects_candidate(monkeypatch):
    from app.services import match_service

    candidates = [
        {"code": "M001", "name": "铜柱", "spec": "M3x10", "score": 0.82},
        {"code": "M002", "name": "螺钉", "spec": "M6x20", "score": 0.65},
    ]

    class FakeMessage:
        content = '{"matched_code": "M001", "confidence": 0.88, "reason": "名称相近"}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"]
            assert "铜柱子" in kwargs["messages"][1]["content"]
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(match_service, "create_openai_client", lambda: FakeClient())

    result = match_service.llm_judge("铜柱子", candidates)

    assert result.matched_code == "M001"
    assert result.matched_name == "铜柱"
    assert result.confidence == 0.88
    assert result.match_level == "llm"


@pytest.mark.asyncio
async def test_match_material_returns_embedding_when_first_score_is_clear(test_session, monkeypatch):
    from app.services import match_service

    app_state = SimpleNamespace()
    monkeypatch.setattr(match_service, "embedding_match", lambda raw_name, db, app_state, top_k=5: [
        {"code": "M001", "name": "铜柱", "spec": "M3x10", "score": 0.92},
        {"code": "M002", "name": "螺钉", "spec": "M6x20", "score": 0.70},
    ])

    result = await match_service.match_material("铜柱相似叫法", test_session, app_state)

    assert result.matched_code == "M001"
    assert result.match_level == "embedding"
    assert result.confidence == 0.92


@pytest.mark.asyncio
async def test_match_material_falls_back_to_llm(test_session, monkeypatch):
    from app.services import match_service

    app_state = SimpleNamespace()
    candidates = [{"code": "M001", "name": "铜柱", "spec": "M3x10", "score": 0.78}]
    monkeypatch.setattr(match_service, "embedding_match", lambda raw_name, db, app_state, top_k=5: candidates)
    monkeypatch.setattr(
        match_service,
        "llm_judge",
        lambda raw_name, candidates: match_service.MatchResult(
            raw_name=raw_name,
            matched_code="M001",
            matched_name="铜柱",
            matched_spec="M3x10",
            confidence=0.81,
            match_level="llm",
            candidates=candidates,
        ),
    )

    result = await match_service.match_material("铜柱近似", test_session, app_state)

    assert result.match_level == "llm"
    assert result.candidates == candidates


@pytest.mark.asyncio
async def test_batch_match_returns_result_per_item(test_session, monkeypatch):
    from app.services import match_service

    async def fake_match_material(raw_name, db, app_state):
        return match_service.MatchResult(
            raw_name=raw_name,
            matched_code=None,
            matched_name=None,
            matched_spec=None,
            confidence=0.0,
            match_level="none",
            candidates=[],
        )

    monkeypatch.setattr(match_service, "match_material", fake_match_material)
    results = await match_service.batch_match(
        [{"raw_name": "铜柱"}, {"material_name": "螺钉"}, {"name": "垫片"}],
        test_session,
        SimpleNamespace(),
    )

    assert [result.raw_name for result in results] == ["铜柱", "螺钉", "垫片"]
