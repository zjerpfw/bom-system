import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeResponse:
    """模拟httpx响应对象。"""

    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        """测试响应默认成功。"""
        return None

    def json(self) -> dict:
        """返回模拟JSON。"""
        return self.payload


def test_dashscope_embedding_adapter_parses_native_response(monkeypatch):
    from app.services import embedding_service

    requests = []

    class FakeClient:
        """记录阿里百炼原生向量请求。"""

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, headers, json):
            requests.append({"url": url, "headers": headers, "json": json})
            batch = json["input"]["texts"]
            return FakeResponse(
                {
                    "output": {
                        "embeddings": [
                            {"text_index": index, "embedding": [float(index), float(index + 1)]}
                            for index, _ in enumerate(batch)
                        ]
                    }
                }
            )

    monkeypatch.setattr(embedding_service.httpx, "Client", FakeClient)
    runtime_settings = SimpleNamespace(
        embedding_provider="dashscope",
        dashscope_api_key="dash-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_embedding_model="text-embedding-v4",
    )

    texts = [f"物料{index}" for index in range(11)]
    vectors = embedding_service.create_embeddings(texts, runtime_settings=runtime_settings)

    assert len(vectors) == 11
    assert len(requests) == 2
    assert [len(request["json"]["input"]["texts"]) for request in requests] == [10, 1]
    assert requests[0]["url"] == "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    assert requests[0]["headers"]["Authorization"] == "Bearer dash-key"
    assert requests[0]["json"]["model"] == "text-embedding-v4"
    assert requests[0]["json"]["parameters"]["text_type"] == "document"
    assert requests[0]["json"]["parameters"]["output_type"] == "dense"


def test_qianfan_embedding_adapter_parses_v2_response(monkeypatch):
    from app.services import embedding_service

    requests = []

    class FakeClient:
        """记录百度千帆v2向量请求。"""

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, headers, json):
            requests.append({"url": url, "headers": headers, "json": json})
            return FakeResponse(
                {
                    "data": [
                        {"index": 1, "embedding": [0.7, 0.8]},
                        {"index": 0, "embedding": [0.5, 0.6]},
                    ]
                }
            )

    monkeypatch.setattr(embedding_service.httpx, "Client", FakeClient)
    runtime_settings = SimpleNamespace(
        embedding_provider="qianfan",
        qianfan_api_key="bce-v3/test",
        qianfan_base_url="https://qianfan.baidubce.com/v2",
        qianfan_embedding_model="embedding-v1",
    )

    vectors = embedding_service.create_embeddings(["电容", "电阻"], runtime_settings=runtime_settings)

    assert vectors == [[0.5, 0.6], [0.7, 0.8]]
    assert requests[0]["url"] == "https://qianfan.baidubce.com/v2/embeddings"
    assert requests[0]["headers"]["Authorization"] == "Bearer bce-v3/test"
    assert requests[0]["json"] == {"model": "embedding-v1", "input": ["电容", "电阻"]}


def test_embedding_adapter_rejects_unknown_provider():
    from app.services import embedding_service

    runtime_settings = SimpleNamespace(embedding_provider="unknown")

    try:
        embedding_service.create_embeddings(["铜柱"], runtime_settings=runtime_settings)
    except RuntimeError as error:
        assert "不支持的向量供应商" in str(error)
    else:
        raise AssertionError("未知供应商必须抛出错误")
