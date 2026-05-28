from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    """读取文本文件。"""
    return path.read_text(encoding="utf-8")


def assert_contains(path: Path, expected: str) -> None:
    """检查文件包含指定内容。"""
    if expected not in read_text(path):
        raise AssertionError(f"{path} 缺少内容：{expected}")


def main() -> None:
    """检查端到端集成资产是否齐全。"""
    e2e_path = PROJECT_DIR / "scripts" / "e2e_test.py"
    readme_path = PROJECT_DIR / "README.md"
    compose_path = PROJECT_DIR / "docker-compose.yml"

    if not e2e_path.exists():
        raise AssertionError("缺少 scripts/e2e_test.py")
    if not compose_path.exists():
        raise AssertionError("缺少 docker-compose.yml")

    for keyword in [
        "Step 1",
        "Step 2",
        "Step 3",
        "Step 4",
        "Step 5",
        "Step 6",
        "主控板V2",
        "materials.faiss",
    ]:
        assert_contains(e2e_path, keyword)

    for keyword in ["项目简介", "快速启动", ".env 配置说明", "/docs", "已知限制"]:
        assert_contains(readme_path, keyword)

    for keyword in ["backend:", "frontend:", "./backend/data", "/api"]:
        assert_contains(compose_path, keyword)

    print("整合集成资产检查通过")


if __name__ == "__main__":
    main()
