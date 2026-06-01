import sys
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def create_table_image_bytes() -> bytes:
    image = np.full((220, 520, 3), 255, dtype=np.uint8)
    for y in [20, 80, 140, 200]:
        cv2.line(image, (20, y), (500, y), (0, 0, 0), 2)
    for x in [20, 150, 290, 390, 500]:
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    success, buffer = cv2.imencode(".png", image)
    assert success
    return buffer.tobytes()


def test_enhance_table_photo_for_ocr_crops_photo_background():
    from app.services.ocr_service import decode_image, enhance_table_photo_for_ocr

    image = np.full((520, 720, 3), 210, dtype=np.uint8)
    table = np.full((260, 460, 3), 255, dtype=np.uint8)
    for y in [20, 80, 140, 200, 240]:
        cv2.line(table, (20, y), (440, y), (0, 0, 0), 2)
    for x in [20, 130, 260, 340, 440]:
        cv2.line(table, (x, 20), (x, 240), (0, 0, 0), 2)

    source_points = np.float32([[0, 0], [459, 0], [459, 259], [0, 259]])
    target_points = np.float32([[120, 80], [610, 55], [640, 430], [80, 450]])
    matrix = cv2.getPerspectiveTransform(source_points, target_points)
    warped_table = cv2.warpPerspective(table, matrix, (720, 520), borderValue=(210, 210, 210))
    mask = cv2.warpPerspective(np.full((260, 460), 255, dtype=np.uint8), matrix, (720, 520))
    image[mask > 0] = warped_table[mask > 0]

    success, buffer = cv2.imencode(".jpg", image)
    assert success

    enhanced = decode_image(enhance_table_photo_for_ocr(buffer.tobytes()))

    assert enhanced.shape[0] < image.shape[0]
    assert enhanced.shape[1] < image.shape[1]
    assert enhanced.shape[0] > 180
    assert enhanced.shape[1] > 300


def test_auto_mode_sends_enhanced_image_to_baidu(monkeypatch):
    import main
    from app.api import ocr

    captured = {}

    monkeypatch.setattr(ocr, "is_table_image", lambda image_bytes: True)
    monkeypatch.setattr(ocr, "has_baidu_free_quota", lambda api_name="table_v2": True)
    monkeypatch.setattr(ocr, "enhance_table_photo_for_ocr", lambda image_bytes: b"enhanced-image")

    def fake_baidu(image_bytes):
        captured["image_bytes"] = image_bytes
        return [["序号", "名称", "用量", "单位"], ["1", "铜柱", "4", "个"]]

    monkeypatch.setattr(ocr, "ocr_table_with_baidu", fake_baidu)
    client = TestClient(main.app)

    response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试夹具", "mode": "auto"},
        files={"file": ("table.png", create_table_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["mode"] == "baidu_enhanced"
    assert captured["image_bytes"] == b"enhanced-image"


def test_get_baidu_access_token_uses_cache(monkeypatch):
    from app.core.config import get_settings
    from app.services import ocr_service

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "token-a", "expires_in": 2592000}

    def fake_post(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setenv("BAIDU_OCR_API_KEY", "api-key")
    monkeypatch.setenv("BAIDU_OCR_SECRET_KEY", "secret-key")
    get_settings.cache_clear()
    monkeypatch.setattr(ocr_service, "_baidu_token_cache", {"access_token": "", "expires_at": 0.0})
    monkeypatch.setattr(ocr_service.httpx, "post", fake_post)
    monkeypatch.setattr(ocr_service.time, "time", lambda: 1000.0)

    first_token = ocr_service.get_baidu_access_token()
    second_token = ocr_service.get_baidu_access_token()

    assert first_token == "token-a"
    assert second_token == "token-a"
    assert len(calls) == 1
    assert calls[0]["params"]["grant_type"] == "client_credentials"


def test_ocr_table_with_baidu_builds_matrix(monkeypatch, tmp_path):
    from app.services import ocr_service

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tables_result": [
                    {
                        "body": [
                            {"row_start": 0, "row_end": 0, "col_start": 0, "col_end": 0, "words": "名称"},
                            {"row_start": 0, "row_end": 0, "col_start": 1, "col_end": 1, "words": "规格"},
                            {"row_start": 1, "row_end": 1, "col_start": 0, "col_end": 0, "words": "铜柱"},
                            {"row_start": 1, "row_end": 1, "col_start": 1, "col_end": 1, "words": "M3"},
                        ]
                    }
                ]
            }

    monkeypatch.setattr(ocr_service, "get_baidu_access_token", lambda: "token-a")
    monkeypatch.setattr(ocr_service, "ensure_baidu_free_quota", lambda: None)
    monkeypatch.setattr(ocr_service, "record_baidu_table_call", lambda: None)
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *args, **kwargs: FakeResponse())

    table = ocr_service.ocr_table_with_baidu(create_table_image_bytes())

    assert table == [["名称", "规格"], ["铜柱", "M3"]]


def test_baidu_monthly_quota_reserves_by_api(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import ocr_service

    monkeypatch.setattr(ocr_service, "BAIDU_USAGE_FILE", tmp_path / "baidu_usage.json")
    monkeypatch.setenv("BAIDU_OCR_ACCOUNT_TYPE", "personal")
    monkeypatch.setenv("BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT", "3")
    monkeypatch.setenv("BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER", "1")
    get_settings.cache_clear()

    first_status = ocr_service.get_baidu_quota_status("table_v2")
    ocr_service.reserve_baidu_free_quota("table_v2")
    ocr_service.reserve_baidu_free_quota("table_v2")
    exhausted_status = ocr_service.get_baidu_quota_status("table_v2")

    assert first_status["limit"] == 3
    assert first_status["remaining"] == 2
    assert exhausted_status["used"] == 2
    assert exhausted_status["remaining"] == 0
    assert ocr_service.has_baidu_free_quota("table_v2") is False


def test_baidu_failed_call_consumes_local_free_quota(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import ocr_service

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"error_code": 17, "error_msg": "Open api daily request limit reached"}

    monkeypatch.setattr(ocr_service, "BAIDU_USAGE_FILE", tmp_path / "baidu_usage.json")
    monkeypatch.setenv("BAIDU_OCR_API_KEY", "api-key")
    monkeypatch.setenv("BAIDU_OCR_SECRET_KEY", "secret-key")
    monkeypatch.setenv("BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT", "1")
    monkeypatch.setenv("BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER", "0")
    get_settings.cache_clear()
    monkeypatch.setattr(ocr_service, "get_baidu_access_token", lambda: "token-a")
    monkeypatch.setattr(ocr_service.httpx, "post", lambda *args, **kwargs: calls.append(kwargs) or FakeResponse())

    try:
        ocr_service.ocr_table_with_baidu(create_table_image_bytes())
    except RuntimeError as error:
        assert "百度OCR调用失败" in str(error)

    status = ocr_service.get_baidu_quota_status("table_v2")

    assert status["used"] == 1
    assert status["remaining"] == 0


def test_table_to_bom_items_maps_header_and_skips_duplicates():
    from app.services.ocr_service import table_to_bom_items

    table = [
        ["序号", "名称", "规格型号", "用量", "单位"],
        ["1", "铜柱", "M3x10", "4", "个"],
        ["1", "铜柱", "M3x10", "4", "个"],
        ["", "", "", "", ""],
        ["2", "螺钉", "M6x20", "8", "个"],
    ]

    result = table_to_bom_items(table, "测试夹具")

    assert result["product"] == "测试夹具"
    assert result["items"] == [
        {"name": "铜柱", "spec": "M3x10", "quantity": 4, "unit": "个", "level": 1, "confidence": 0.86},
        {"name": "螺钉", "spec": "M6x20", "quantity": 8, "unit": "个", "level": 1, "confidence": 0.86},
    ]


def test_baidu_mode_without_keys_returns_friendly_error(monkeypatch):
    import main
    from app.core.config import get_settings

    monkeypatch.delenv("BAIDU_OCR_API_KEY", raising=False)
    monkeypatch.delenv("BAIDU_OCR_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(main.app)

    response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试夹具", "mode": "baidu"},
        files={"file": ("table.png", create_table_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 1
    assert "百度OCR密钥未配置" in response.json()["msg"]


def test_baidu_enhanced_mode_without_keys_returns_friendly_error(monkeypatch):
    import main
    from app.core.config import get_settings

    monkeypatch.delenv("BAIDU_OCR_API_KEY", raising=False)
    monkeypatch.delenv("BAIDU_OCR_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(main.app)

    response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试夹具", "mode": "baidu_enhanced"},
        files={"file": ("table.png", create_table_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 1
    assert "百度OCR密钥未配置" in response.json()["msg"]


def test_auto_mode_falls_back_to_paddle_when_baidu_unavailable(monkeypatch):
    import main
    from app.api import ocr

    monkeypatch.setattr(ocr, "is_table_image", lambda image_bytes: True)
    monkeypatch.setattr(ocr, "ocr_table_with_baidu", lambda image_bytes: (_ for _ in ()).throw(RuntimeError("无免费额度")))
    monkeypatch.setattr(ocr, "preprocess_image", lambda image_bytes: np.zeros((20, 20), dtype=np.uint8))
    monkeypatch.setattr(
        ocr,
        "ocr_with_paddle",
        lambda image: [{"text": "铜柱 M3 4 个", "confidence": 0.95, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
    )
    monkeypatch.setattr(
        ocr,
        "extract_bom_from_ocr_text",
        lambda raw_lines, product_name: {"product": product_name, "items": []},
    )
    client = TestClient(main.app)

    response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试夹具", "mode": "auto"},
        files={"file": ("table.png", create_table_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["mode"] == "paddle"
    assert response.json()["data"]["warnings"] == ["百度OCR不可用，已自动切换PaddleOCR"]


def test_auto_mode_skips_baidu_when_free_quota_exhausted(monkeypatch):
    import main
    from app.api import ocr

    monkeypatch.setattr(ocr, "is_table_image", lambda image_bytes: True)
    monkeypatch.setattr(ocr, "has_baidu_free_quota", lambda api_name="table_v2": False)
    monkeypatch.setattr(
        ocr,
        "ocr_table_with_baidu",
        lambda image_bytes: (_ for _ in ()).throw(AssertionError("不应调用百度OCR")),
    )
    monkeypatch.setattr(ocr, "preprocess_image", lambda image_bytes: np.zeros((20, 20), dtype=np.uint8))
    monkeypatch.setattr(
        ocr,
        "ocr_with_paddle",
        lambda image: [{"text": "铜柱 M3 4 个", "confidence": 0.95, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
    )
    monkeypatch.setattr(
        ocr,
        "extract_bom_from_ocr_text",
        lambda raw_lines, product_name: {"product": product_name, "items": []},
    )
    client = TestClient(main.app)

    response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试夹具", "mode": "auto"},
        files={"file": ("table.png", create_table_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["mode"] == "paddle"
    assert response.json()["data"]["warnings"] == ["百度OCR免费额度不足，已自动切换PaddleOCR"]
