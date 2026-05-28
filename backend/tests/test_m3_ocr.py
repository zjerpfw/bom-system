import json
import sys
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def create_test_image_bytes(text: str = "BOM M3") -> bytes:
    image = np.full((120, 320, 3), 255, dtype=np.uint8)
    cv2.putText(image, text, (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
    success, buffer = cv2.imencode(".png", image)
    assert success
    return buffer.tobytes()


def test_preprocess_image_returns_binary_gray_array():
    from app.services.ocr_service import preprocess_image

    processed = preprocess_image(create_test_image_bytes())

    assert isinstance(processed, np.ndarray)
    assert len(processed.shape) == 2
    assert processed.dtype == np.uint8
    assert set(np.unique(processed)).issubset({0, 255})


def test_normalize_text_replaces_full_width_and_symbols():
    from app.services.ocr_service import normalize_text

    result = normalize_text("　铜柱Ｍ３ × １０Ω ５μ ９０°　")

    assert result == "铜柱M3 x 10Ohm 5u 90deg"


def test_ocr_with_paddle_formats_and_sorts(monkeypatch):
    from app.services import ocr_service

    class FakePaddleOCR:
        def ocr(self, image, cls=True):
            return [
                [
                    [[[20, 40], [80, 40], [80, 60], [20, 60]], ("下行", 0.91)],
                    [[[10, 10], [80, 10], [80, 30], [10, 30]], ("上行", 0.98)],
                ]
            ]

    monkeypatch.setattr(ocr_service, "get_paddle_ocr", lambda: FakePaddleOCR())

    results = ocr_service.ocr_with_paddle(np.zeros((80, 120), dtype=np.uint8))

    assert results == [
        {"text": "上行", "confidence": 0.98, "bbox": [[10, 10], [80, 10], [80, 30], [10, 30]]},
        {"text": "下行", "confidence": 0.91, "bbox": [[20, 40], [80, 40], [80, 60], [20, 60]]},
    ]


def test_extract_bom_from_ocr_text_parses_markdown_json(monkeypatch):
    from app.services import ocr_service

    class FakeMessage:
        content = """```json
        {
          "product": "测试产品",
          "items": [
            {"name": "铜柱", "spec": "M3", "quantity": 4, "unit": "个", "level": 1, "confidence": 0.86}
          ]
        }
        ```"""

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"]
            assert "铜柱 M3 4 个" in kwargs["messages"][1]["content"]
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(ocr_service, "create_openai_client", lambda: FakeClient())

    result = ocr_service.extract_bom_from_ocr_text(["铜柱 M3 4 个"], "测试产品")

    assert result["product"] == "测试产品"
    assert result["items"][0]["name"] == "铜柱"


def test_ocr_routes_return_unified_response(monkeypatch):
    import main
    from app.api import ocr

    def fake_extract(raw_lines, product_name):
        return {
            "product": product_name,
            "items": [
                {
                    "name": "铜柱",
                    "spec": "M3",
                    "quantity": 4,
                    "unit": "个",
                    "level": 1,
                    "confidence": 0.9,
                }
            ],
        }

    monkeypatch.setattr(ocr, "preprocess_image", lambda image_bytes: np.zeros((20, 20), dtype=np.uint8))
    monkeypatch.setattr(
        ocr,
        "ocr_with_paddle",
        lambda image: [{"text": "铜柱 M3 4 个", "confidence": 0.95, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
    )
    monkeypatch.setattr(ocr, "extract_bom_from_ocr_text", fake_extract)

    client = TestClient(main.app)
    image_bytes = create_test_image_bytes()

    upload_response = client.post(
        "/api/ocr/upload",
        data={"product_name": "测试产品"},
        files={"file": ("bom.png", image_bytes, "image/png")},
    )

    assert upload_response.status_code == 200
    assert upload_response.json()["code"] == 0
    assert upload_response.json()["data"]["raw_lines"] == ["铜柱 M3 4 个"]
    assert upload_response.json()["data"]["extracted"]["product"] == "测试产品"
    assert upload_response.json()["data"]["processing_time_ms"] >= 0

    text_response = client.post(
        "/api/ocr/text",
        json={"product_name": "测试产品", "text": "铜柱 M3 4 个\n螺钉 M6 8 个"},
    )

    assert text_response.status_code == 200
    assert text_response.json()["code"] == 0
    assert text_response.json()["data"]["raw_lines"] == ["铜柱 M3 4 个", "螺钉 M6 8 个"]


def test_ocr_text_route_returns_friendly_error_when_llm_unavailable(monkeypatch):
    import main
    from app.api import ocr

    def fake_extract(raw_lines, product_name):
        raise RuntimeError("OpenAI配置不可用")

    monkeypatch.setattr(ocr, "extract_bom_from_ocr_text", fake_extract)

    client = TestClient(main.app)
    response = client.post(
        "/api/ocr/text",
        json={"product_name": "测试产品", "text": "铜柱 M3 4 个"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 1
    assert "文本提取失败" in response.json()["msg"]
