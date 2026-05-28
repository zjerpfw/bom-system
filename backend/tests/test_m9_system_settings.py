import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest_asyncio.fixture
async def settings_session(tmp_path):
    from app.core.database import Base
    from app.models.material import Material

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'settings.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        session.add_all(
            [
                Material(code="M001", name="铜柱", spec="M3x6", unit="个", category="五金"),
                Material(code="M002", name="电容", spec="100uF", unit="个", category="电子"),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_settings_can_disable_ai_from_database(settings_session, monkeypatch):
    from app.core.config import get_settings
    from app.services.settings_service import get_runtime_settings, upsert_system_settings

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-5.5")
    get_settings.cache_clear()

    before = await get_runtime_settings(settings_session)
    assert before.ai_enabled is True
    assert before.openai_chat_model == "gpt-5.5"

    await upsert_system_settings(
        {
            "AI_ENABLED": False,
            "OPENAI_CHAT_MODEL": "gpt-4o-mini",
        },
        "测试员",
        settings_session,
    )

    after = await get_runtime_settings(settings_session)
    assert after.ai_enabled is False
    assert after.openai_chat_model == "gpt-4o-mini"


def test_settings_api_lists_updates_and_masks_secrets(tmp_path, monkeypatch):
    from app.core.database import Base, get_db
    import main

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'settings_api.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_local() as session:
            yield session

    import asyncio

    asyncio.run(create_tables())
    main.app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main.app)

    update_response = client.post(
        "/api/settings/system",
        json={
            "settings": {
                "AI_ENABLED": False,
                "OPENAI_BASE_URL": "https://fululai.cn/v1",
                "OPENAI_API_KEY": "sk-test-secret",
                "OPENAI_CHAT_MODEL": "gpt-5.5",
                "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
            },
            "operator": "管理员",
        },
    )
    list_response = client.get("/api/settings/system")

    assert update_response.status_code == 200
    assert update_response.json()["code"] == 0
    data = list_response.json()["data"]
    assert data["runtime"]["ai_enabled"] is False
    assert data["runtime"]["openai_base_url"] == "https://fululai.cn/v1"
    assert data["runtime"]["openai_api_key_configured"] is True
    assert data["items"]["OPENAI_API_KEY"]["value"] == "********"
    assert data["items"]["OPENAI_CHAT_MODEL"]["value"] == "gpt-5.5"
    main.app.dependency_overrides.clear()


def test_rule_extract_bom_from_ocr_text_without_ai(monkeypatch):
    from app.services import ocr_service

    def fail_client():
        raise AssertionError("AI关闭时不应创建OpenAI客户端")

    monkeypatch.setattr(ocr_service, "create_openai_client", fail_client)
    result = ocr_service.extract_bom_from_ocr_text(
        ["序号 名称 规格 数量 单位", "1 铜柱 M3x6 4 个", "2 电容 100uF 10 个"],
        "主控板V2",
        ai_enabled=False,
    )

    assert result["product"] == "主控板V2"
    assert result["items"] == [
        {"name": "铜柱", "spec": "M3x6", "quantity": 4, "unit": "个", "level": 1, "confidence": 0.62},
        {"name": "电容", "spec": "100uF", "quantity": 10, "unit": "个", "level": 1, "confidence": 0.62},
    ]


@pytest.mark.asyncio
async def test_match_material_uses_rule_candidates_when_ai_disabled(settings_session, monkeypatch):
    from app.services import match_service

    def fail_embedding(raw_name):
        raise AssertionError("AI关闭时不应生成embedding")

    def fail_llm(raw_name, candidates):
        raise AssertionError("AI关闭时不应调用LLM")

    monkeypatch.setattr(match_service, "create_embedding", fail_embedding)
    monkeypatch.setattr(match_service, "llm_judge", fail_llm)

    result = await match_service.match_material(
        "铜柱M3x6",
        settings_session,
        SimpleNamespace(ai_enabled=False),
    )

    assert result.matched_code == "M001"
    assert result.matched_name == "铜柱"
    assert result.match_level == "rule"
    assert result.confidence >= 0.70
    assert result.candidates[0]["code"] == "M001"
