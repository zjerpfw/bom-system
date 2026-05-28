import json
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def configure_test_paths(tmp_path, monkeypatch):
    from app.core.database import Base
    from app.services import material_service

    database_file = tmp_path / "bom.db"
    database_url = f"sqlite+aiosqlite:///{database_file.as_posix()}"
    engine = create_async_engine(database_url, echo=False, future=True)
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async def create_tables():
        import app.models  # noqa: F401

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    material_service.run_async(create_tables())
    monkeypatch.setattr(material_service, "AsyncSessionLocal", test_session_local)
    monkeypatch.setattr(material_service, "FAISS_INDEX_PATH", tmp_path / "materials.faiss")
    monkeypatch.setattr(material_service, "ID_MAP_PATH", tmp_path / "id_map.json")
    return database_file


def write_csv(file_path: Path, content: str) -> Path:
    file_path.write_text(content, encoding="utf-8-sig")
    return file_path


def test_import_materials_from_csv_cleans_and_upserts(tmp_path, monkeypatch):
    from app.services.material_service import import_materials_from_csv

    database_file = configure_test_paths(tmp_path, monkeypatch)
    csv_file = write_csv(
        tmp_path / "materials.csv",
        "编码,名称,规格,单位,类别\n"
        "Ｍ001, 螺钉 , Ｍ６ , 个 , 紧固件 \n"
        ",,,, \n"
        ",缺少编码,M8,个,紧固件\n"
        "M001,螺钉升级,M8,个,紧固件\n",
    )

    result = import_materials_from_csv(str(csv_file))

    assert result["total"] == 3
    assert result["success"] == 2
    assert result["skipped"] == 1
    assert len(result["errors"]) == 1

    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            "select code, name, spec, unit, category from materials order by code"
        ).fetchall()

    assert rows == [("M001", "螺钉升级", "M8", "个", "紧固件")]


def test_build_embedding_index_writes_vectors_and_id_map(tmp_path, monkeypatch):
    from app.services.material_service import (
        build_embedding_index,
        import_materials_from_csv,
        load_index,
    )

    database_file = configure_test_paths(tmp_path, monkeypatch)
    csv_file = write_csv(
        tmp_path / "materials.csv",
        "编码,名称,规格,单位,类别\n"
        "M001,螺钉,M6,个,紧固件\n"
        "M002,垫片,10mm,个,紧固件\n",
    )
    import_materials_from_csv(str(csv_file))

    def fake_embedding_provider(texts):
        return [[1.0, 0.0, 0.0] if index == 0 else [0.0, 1.0, 0.0] for index, _ in enumerate(texts)]

    build_embedding_index(embedding_provider=fake_embedding_provider)
    index, id_map = load_index()

    assert index.ntotal == 2
    assert id_map == {"0": "M001", "1": "M002"}

    with sqlite3.connect(database_file) as connection:
        embeddings = connection.execute(
            "select embedding_json from materials order by code"
        ).fetchall()

    assert json.loads(embeddings[0][0]) == [1.0, 0.0, 0.0]
    assert json.loads(embeddings[1][0]) == [0.0, 1.0, 0.0]


def test_material_routes_use_unified_response(tmp_path, monkeypatch):
    import main
    from app.api import materials

    database_file = configure_test_paths(tmp_path, monkeypatch)
    client = TestClient(main.app)
    csv_file = write_csv(
        tmp_path / "materials.csv",
        "编码,名称,规格,单位,类别\nM001,螺钉,M6,个,紧固件\n",
    )

    with csv_file.open("rb") as file_object:
        response = client.post(
            "/api/materials/import",
            files={"file": ("materials.csv", file_object, "text/csv")},
        )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["success"] == 1

    stats_response = client.get("/api/materials/stats")

    assert stats_response.status_code == 200
    assert stats_response.json()["code"] == 0
    assert stats_response.json()["data"]["material_total"] == 1
    assert stats_response.json()["data"]["index_ready"] is False

    assert database_file.exists()

    async def fake_build_embedding_index():
        return None

    monkeypatch.setattr(materials, "async_build_embedding_index", fake_build_embedding_index)
    build_response = client.post("/api/materials/build-index")

    assert build_response.status_code == 200
    assert build_response.json() == {"code": 0, "msg": "ok", "data": {"status": "built"}}
