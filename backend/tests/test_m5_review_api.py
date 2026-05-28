import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def configure_review_api_test(tmp_path, monkeypatch, api_key: str = ""):
    from app.core.config import get_settings
    from app.core.database import Base, get_db
    from app.models.bom_item import BomItem
    from app.models.material import Material
    from app.models.missing_material import MissingMaterial
    from app.models.name_mapping import NameMapping
    import main

    if api_key:
        monkeypatch.setenv("API_KEY", api_key)
    else:
        monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'review.db').as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async def create_tables_and_seed():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add_all(
                [
                    Material(code="M001", name="铜柱", spec="M3x10", unit="个", category="五金"),
                    Material(code="M002", name="螺钉", spec="M6x20", unit="个", category="五金"),
                    Material(code="M003", name="垫片", spec="10mm", unit="个", category="五金"),
                    BomItem(
                        product_name="夹具A",
                        raw_name="铜柱",
                        material_code="M001",
                        material_name="铜柱",
                        status="confirmed",
                        confidence=0.95,
                        match_level="exact",
                    ),
                    BomItem(
                        product_name="夹具A",
                        raw_name="螺丝",
                        material_code="M002",
                        material_name="螺钉",
                        status="pending",
                        confidence=0.88,
                        match_level="llm",
                        candidates_json='[{"code":"M002","name":"螺钉","spec":"M6x20","score":0.88}]',
                    ),
                    BomItem(
                        product_name="夹具A",
                        raw_name="异形件",
                        status="pending",
                        confidence=0.65,
                        match_level="none",
                        candidates_json="[]",
                    ),
                    BomItem(
                        product_name="夹具B",
                        raw_name="旧料",
                        status="rejected",
                        confidence=0.40,
                        match_level="llm",
                    ),
                    MissingMaterial(raw_name="异形件", ai_suggested_name="异形件", status="pending"),
                    NameMapping(raw_name="铜柱", system_code="M001", system_name="铜柱", spec="M3x10", used_count=5),
                    NameMapping(raw_name="螺丝", system_code="M002", system_name="螺钉", spec="M6x20", used_count=3),
                ]
            )
            await session.commit()

    async def override_get_db():
        async with session_local() as session:
            yield session

    asyncio.run(create_tables_and_seed())
    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), main.app, session_local, get_db


def test_review_dashboard_items_mapping_stats_and_logs(tmp_path, monkeypatch):
    from app.models.bom_item import BomItem
    from app.models.operation_log import OperationLog

    client, app, session_local, get_db = configure_review_api_test(tmp_path, monkeypatch)

    dashboard_response = client.get("/api/review/dashboard")
    dashboard = dashboard_response.json()["data"]

    assert dashboard_response.status_code == 200
    assert dashboard["total_bom_items"] == 4
    assert dashboard["pending"] == 2
    assert dashboard["confirmed"] == 1
    assert dashboard["rejected"] == 1
    assert dashboard["missing_materials"] == 1
    assert dashboard["auto_confirm_rate"] == 0.25
    assert dashboard["products"][0] == {"name": "夹具A", "pending": 2, "total": 3}

    items_response = client.get("/api/review/items?product_name=夹具A&status=pending&page=1&page_size=10")
    items_data = items_response.json()["data"]

    assert items_response.status_code == 200
    assert items_data["total"] == 2
    assert items_data["items"][0]["candidates"][0]["code"] == "M002"
    assert items_data["items"][0]["match_level"] == "llm"

    high_confidence_id = items_data["items"][0]["id"]
    low_confidence_id = items_data["items"][1]["id"]
    batch_response = client.post(
        "/api/review/batch-confirm",
        json={"ids": [high_confidence_id, low_confidence_id], "reviewer": "张三"},
    )
    reassign_response = client.post(
        f"/api/review/reassign/{low_confidence_id}",
        json={"system_code": "M003", "reviewer": "李四"},
    )
    stats_response = client.get("/api/review/mapping-stats")

    assert batch_response.json()["data"] == {"confirmed": 1, "skipped": 1}
    assert reassign_response.json()["data"] == {"status": "confirmed"}
    assert stats_response.json()["data"]["total"] >= 2
    assert stats_response.json()["data"]["top_used"][0]["used_count"] >= 5

    async def read_state():
        async with session_local() as session:
            confirmed_count = (
                await session.execute(select(BomItem).where(BomItem.status == "confirmed"))
            ).scalars().all()
            logs = (await session.execute(select(OperationLog).order_by(OperationLog.id))).scalars().all()
            return confirmed_count, logs

    confirmed_items, logs = asyncio.run(read_state())

    assert len(confirmed_items) == 3
    assert [log.operation for log in logs] == ["batch_confirm", "reassign"]
    assert logs[0].operator == "张三"
    assert logs[1].target_id == low_confidence_id
    app.dependency_overrides.clear()
    get_settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()


def test_api_key_middleware_blocks_api_when_configured(tmp_path, monkeypatch):
    client, app, _, _ = configure_review_api_test(tmp_path, monkeypatch, api_key="secret-key")

    blocked_response = client.get("/api/review/dashboard")
    allowed_response = client.get("/api/review/dashboard", headers={"X-API-Key": "secret-key"})

    assert blocked_response.status_code == 401
    assert blocked_response.json() == {"code": 401, "msg": "invalid api key", "data": {}}
    assert allowed_response.status_code == 200
    assert allowed_response.json()["code"] == 0
    app.dependency_overrides.clear()
    get_settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings
    monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()
