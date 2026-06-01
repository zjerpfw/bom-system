import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest_asyncio.fixture
async def persistence_session(tmp_path):
    from app.core.database import Base
    from app.models.material import Material

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'match_persistence.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        session.add_all(
            [
                Material(code="M001", name="铜柱", spec="M3x10", unit="个", category="五金"),
                Material(code="M002", name="螺钉", spec="M6x20", unit="个", category="五金"),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_process_extracted_bom_persists_status_mapping_and_missing(persistence_session, monkeypatch):
    from app.models.bom_item import BomItem
    from app.models.missing_material import MissingMaterial
    from app.models.name_mapping import NameMapping
    from app.services import match_service

    async def fake_batch_match(items, db, app_state):
        return [
            match_service.MatchResult("铜柱", "M001", "铜柱", "M3x10", 0.95, "exact", []),
            match_service.MatchResult(
                "螺丝",
                "M002",
                "螺钉",
                "M6x20",
                0.78,
                "llm",
                [{"code": "M002", "name": "螺钉", "spec": "M6x20", "score": 0.78}],
            ),
            match_service.MatchResult("异形件", None, None, None, 0.0, "none", []),
        ]

    monkeypatch.setattr(match_service, "batch_match", fake_batch_match)
    extracted = {
        "product": "测试夹具",
        "items": [
            {"name": "铜柱", "spec": "M3x10", "quantity": 4, "unit": "个", "level": 1},
            {"name": "螺丝", "spec": "M6x20", "quantity": 8, "unit": "个", "level": 1},
            {"name": "异形件", "spec": "定制", "quantity": 1, "unit": "件", "level": 1},
        ],
    }

    stats = await match_service.process_extracted_bom(extracted, "测试夹具", persistence_session, SimpleNamespace())

    assert stats == {"auto_confirmed": 1, "pending_review": 2, "missing": 1, "total": 3}

    bom_items = (await persistence_session.execute(select(BomItem).order_by(BomItem.id))).scalars().all()
    mappings = (await persistence_session.execute(select(NameMapping))).scalars().all()
    missing_items = (await persistence_session.execute(select(MissingMaterial))).scalars().all()

    assert [item.status for item in bom_items] == ["confirmed", "pending", "pending"]
    assert bom_items[0].material_code == "M001"
    assert bom_items[1].match_level == "llm"
    assert '"M002"' in (bom_items[1].candidates_json or "")
    assert mappings[0].raw_name == "铜柱"
    assert mappings[0].used_count == 1
    assert missing_items[0].raw_name == "异形件"
    assert missing_items[0].ai_suggested_spec == "定制"


@pytest.mark.asyncio
async def test_process_extracted_bom_matches_duplicate_material_names_once(persistence_session, monkeypatch):
    from app.models.bom_item import BomItem
    from app.services import match_service

    matched_batches = []

    async def fake_batch_match(items, db, app_state):
        matched_batches.append([item["name"] for item in items])
        return [
            match_service.MatchResult(item["name"], "M001", "铜柱", item.get("spec"), 0.95, "exact", [])
            for item in items
        ]

    monkeypatch.setattr(match_service, "batch_match", fake_batch_match)
    extracted = {
        "product": "批量火锅料",
        "items": [
            {"name": "铜柱", "spec": "M3x10", "quantity": 4, "unit": "个", "level": 1},
            {"name": "铜柱", "spec": "M3x10", "quantity": 6, "unit": "个", "level": 1},
            {"name": "铜柱", "spec": "M3x10", "quantity": 8, "unit": "个", "level": 1},
        ],
    }

    stats = await match_service.process_extracted_bom(extracted, "", persistence_session, SimpleNamespace())

    assert matched_batches == [["铜柱"]]
    assert stats == {"auto_confirmed": 3, "pending_review": 0, "missing": 0, "total": 3}

    bom_items = (await persistence_session.execute(select(BomItem).order_by(BomItem.id))).scalars().all()
    assert [int(item.quantity) for item in bom_items] == [4, 6, 8]
    assert [item.material_code for item in bom_items] == ["M001", "M001", "M001"]


@pytest.mark.asyncio
async def test_confirm_and_reject_match_update_bom_and_mapping(persistence_session, monkeypatch):
    from app.models.bom_item import BomItem
    from app.models.name_mapping import NameMapping
    from app.services import match_service

    pending_item = BomItem(
        product_name="测试夹具",
        raw_name="螺丝",
        material_name="螺钉",
        quantity=8,
        unit="个",
        status="pending",
        confidence=0.78,
        match_level="llm",
    )
    rejected_item = BomItem(product_name="测试夹具", raw_name="异形件", status="pending", confidence=0)
    persistence_session.add_all([pending_item, rejected_item])
    await persistence_session.commit()

    await match_service.confirm_match(pending_item.id, "M002", "张工", persistence_session)
    await match_service.reject_match(rejected_item.id, "李工", persistence_session)

    refreshed_pending = await persistence_session.get(BomItem, pending_item.id)
    refreshed_rejected = await persistence_session.get(BomItem, rejected_item.id)
    mapping = (
        await persistence_session.execute(
            select(NameMapping).where(NameMapping.raw_name == "螺丝", NameMapping.system_code == "M002")
        )
    ).scalar_one()

    assert refreshed_pending.status == "confirmed"
    assert refreshed_pending.material_code == "M002"
    assert refreshed_pending.material_name == "螺钉"
    assert refreshed_pending.reviewer == "张工"
    assert refreshed_rejected.status == "rejected"
    assert refreshed_rejected.reviewer == "李工"
    assert mapping.used_count == 1


def configure_match_api_test(tmp_path, monkeypatch):
    from app.core.database import Base, get_db
    from app.models.material import Material
    from app.services import match_service
    import main

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'match_api.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add_all(
                [
                    Material(code="M001", name="铜柱", spec="M3x10", unit="个", category="五金"),
                    Material(code="M002", name="螺钉", spec="M6x20", unit="个", category="五金"),
                ]
            )
            await session.commit()

    async def override_get_db():
        async with session_local() as session:
            yield session

    async def fake_batch_match(items, db, app_state):
        from app.services import match_service

        return [
            match_service.MatchResult("铜柱", "M001", "铜柱", "M3x10", 0.95, "exact", []),
            match_service.MatchResult(
                "螺丝",
                "M002",
                "螺钉",
                "M6x20",
                0.78,
                "llm",
                [{"code": "M002", "name": "螺钉", "spec": "M6x20", "score": 0.78}],
            ),
            match_service.MatchResult("异形件", None, None, None, 0.0, "none", []),
        ]

    import asyncio

    asyncio.run(create_tables())
    main.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(match_service, "batch_match", fake_batch_match)
    return TestClient(main.app), main.app


def test_match_api_process_pending_confirm_reject_and_missing(tmp_path, monkeypatch):
    client, app = configure_match_api_test(tmp_path, monkeypatch)

    process_response = client.post(
        "/api/match/process",
        json={
            "product_name": "测试夹具",
            "extracted": {
                "product": "测试夹具",
                "items": [
                    {"name": "铜柱", "spec": "M3x10", "quantity": 4, "unit": "个", "level": 1},
                    {"name": "螺丝", "spec": "M6x20", "quantity": 8, "unit": "个", "level": 1},
                    {"name": "异形件", "spec": "定制", "quantity": 1, "unit": "件", "level": 1},
                ],
            },
        },
    )

    assert process_response.status_code == 200
    assert process_response.json()["code"] == 0
    assert process_response.json()["data"] == {"auto_confirmed": 1, "pending_review": 2, "missing": 1, "total": 3}

    pending_response = client.get("/api/match/pending?page=1&page_size=10")
    pending_data = pending_response.json()["data"]

    assert pending_response.status_code == 200
    assert pending_data["total"] == 2
    assert pending_data["page"] == 1
    assert pending_data["items"][0]["raw_name"] == "螺丝"
    assert pending_data["items"][0]["candidates"][0]["code"] == "M002"
    assert pending_data["items"][0]["match_level"] == "llm"

    confirm_response = client.post(
        f"/api/match/confirm/{pending_data['items'][0]['id']}",
        json={"system_code": "M002", "reviewer": "王工"},
    )
    reject_response = client.post(
        f"/api/match/reject/{pending_data['items'][1]['id']}",
        json={"reviewer": "王工"},
    )
    missing_response = client.get("/api/match/missing")
    missing_id = missing_response.json()["data"]["items"][0]["id"]
    created_response = client.post(f"/api/match/create-missing/{missing_id}")

    assert confirm_response.json() == {"code": 0, "msg": "ok", "data": {"status": "confirmed"}}
    assert reject_response.json() == {"code": 0, "msg": "ok", "data": {"status": "rejected"}}
    assert missing_response.json()["data"]["total"] == 1
    assert created_response.json() == {"code": 0, "msg": "ok", "data": {"status": "created"}}
    app.dependency_overrides.clear()


def test_match_api_process_batch_reuses_duplicate_matches(tmp_path, monkeypatch):
    from app.models.bom_item import BomItem
    from app.core.database import get_db
    from app.services import match_service

    client, app = configure_match_api_test(tmp_path, monkeypatch)
    matched_batches = []

    async def fake_batch_match(items, db, app_state):
        matched_batches.append([item["name"] for item in items])
        return [
            match_service.MatchResult(item["name"], "M001", "铜柱", item.get("spec"), 0.95, "exact", [])
            for item in items
        ]

    monkeypatch.setattr(match_service, "batch_match", fake_batch_match)

    response = client.post(
        "/api/match/process-batch",
        json={
            "documents": [
                {
                    "product_name": "产品A",
                    "extracted": {"product": "产品A", "items": [{"name": "铜柱", "spec": "M3x10", "quantity": 4, "unit": "个"}]},
                },
                {
                    "product_name": "产品B",
                    "extracted": {"product": "产品B", "items": [{"name": "铜柱", "spec": "M3x10", "quantity": 8, "unit": "个"}]},
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"auto_confirmed": 2, "pending_review": 0, "missing": 0, "total": 2}
    assert matched_batches == [["铜柱"]]

    async def collect_items():
        async for session in app.dependency_overrides[get_db]():
            result = await session.execute(select(BomItem).order_by(BomItem.id))
            return result.scalars().all()

    import asyncio

    bom_items = asyncio.run(collect_items())
    assert [item.product_name for item in bom_items] == ["产品A", "产品B"]
    app.dependency_overrides.clear()
