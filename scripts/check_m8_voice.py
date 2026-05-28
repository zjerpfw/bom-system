from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    """读取前端源码文本。"""
    return path.read_text(encoding="utf-8")


def assert_contains(text: str, expected: str, path: Path) -> None:
    """检查源码中包含指定内容。"""
    if expected not in text:
        raise AssertionError(f"{path} 缺少内容：{expected}")


def main() -> None:
    """检查M8语音录入关键接线。"""
    voice_path = PROJECT_DIR / "frontend" / "src" / "components" / "VoiceCapture.vue"
    upload_path = PROJECT_DIR / "frontend" / "src" / "views" / "Upload.vue"
    api_path = PROJECT_DIR / "frontend" / "src" / "api" / "index.ts"
    readme_path = PROJECT_DIR / "README.md"

    if not voice_path.exists():
        raise AssertionError("缺少 VoiceCapture.vue 组件")

    voice_text = read_text(voice_path)
    upload_text = read_text(upload_path)
    api_text = read_text(api_path)
    readme_text = read_text(readme_path)

    assert_contains(voice_text, "SpeechRecognition", voice_path)
    assert_contains(voice_text, "长按说话", voice_path)
    assert_contains(voice_text, "提交识别", voice_path)
    assert_contains(voice_text, "推荐使用 Chrome 浏览器以获得最佳语音识别效果", voice_path)
    assert_contains(upload_text, "语音录入", upload_path)
    assert_contains(upload_text, "VoiceCapture", upload_path)
    assert_contains(api_text, "extractBomFromText", api_path)
    assert_contains(api_text, '"/ocr/text"', api_path)
    assert_contains(readme_text, "当前实现使用浏览器内置免费方案", readme_path)
    assert_contains(readme_text, "Whisper API", readme_path)
    print("M8语音录入源码检查通过")


if __name__ == "__main__":
    main()
