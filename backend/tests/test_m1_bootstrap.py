import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def test_settings_loads_database_url_from_env():
    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"
    os.environ["OPENAI_BASE_URL"] = "https://api.example.com/v1"
    os.environ["OPENAI_CHAT_MODEL"] = "gpt-5.5"
    os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "sqlite+aiosqlite:///./data/test.db"
    assert settings.openai_base_url == "https://api.example.com/v1"
    assert settings.openai_chat_model == "gpt-5.5"
    assert settings.openai_embedding_model == "text-embedding-3-small"


def test_database_models_create_expected_tables():
    from app.core.database import Base
    from app.models import bom_item, material, missing_material, name_mapping

    table_names = set(Base.metadata.tables.keys())

    assert {
        "materials",
        "bom_items",
        "name_mapping",
        "missing_materials",
    }.issubset(table_names)
    assert "code" in Base.metadata.tables["materials"].columns
    assert "status" in Base.metadata.tables["bom_items"].columns
    assert "used_count" in Base.metadata.tables["name_mapping"].columns
    assert "ai_suggested_category" in Base.metadata.tables["missing_materials"].columns


def test_health_api_uses_unified_response_format():
    from main import app

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"code": 0, "msg": "ok", "data": {"status": "running"}}
