import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def test_dev_paths_keep_source_layout():
    from app.core.paths import get_data_dir, get_env_file, get_frontend_dist_dir, get_project_dir

    project_dir = get_project_dir()

    assert project_dir.name == "bom-system"
    assert get_env_file() == project_dir / ".env"
    assert get_data_dir() == project_dir / "backend" / "data"
    assert get_frontend_dist_dir() == project_dir / "frontend" / "dist"


def test_frozen_paths_use_runtime_root_and_meipass(tmp_path, monkeypatch):
    from app.core import paths

    runtime_root = tmp_path / "runtime"
    executable_path = runtime_root / "bom-server.exe"
    meipass_dir = tmp_path / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable_path))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    assert paths.get_runtime_root() == runtime_root
    assert paths.get_env_file() == runtime_root / ".env"
    assert paths.get_data_dir() == runtime_root / "data"
    assert paths.get_frontend_dist_dir() == meipass_dir / "frontend_dist"


def test_runtime_root_env_overrides_frozen_location(tmp_path, monkeypatch):
    from app.core import paths

    runtime_root = tmp_path / "package-root"
    executable_path = tmp_path / "bom-server" / "bom-server.exe"
    monkeypatch.setenv("BOM_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable_path))

    assert paths.get_runtime_root() == runtime_root
    assert paths.get_data_dir() == runtime_root / "data"


def test_paddleocr_model_dir_builds_offline_model_kwargs(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import ocr_service

    model_root = tmp_path / "models" / "paddleocr" / "whl"
    det_dir = model_root / "det" / "ch" / "ch_PP-OCRv4_det_infer"
    rec_dir = model_root / "rec" / "ch" / "ch_PP-OCRv4_rec_infer"
    cls_dir = model_root / "cls" / "ch_ppocr_mobile_v2.0_cls_infer"
    for directory in [det_dir, rec_dir, cls_dir]:
        directory.mkdir(parents=True)

    monkeypatch.setenv("PADDLEOCR_MODEL_DIR", str(model_root))
    get_settings.cache_clear()

    kwargs = ocr_service.get_paddle_ocr_kwargs()

    assert kwargs["det_model_dir"] == str(det_dir)
    assert kwargs["rec_model_dir"] == str(rec_dir)
    assert kwargs["cls_model_dir"] == str(cls_dir)

    monkeypatch.delenv("PADDLEOCR_MODEL_DIR", raising=False)
    get_settings.cache_clear()


def test_paddleocr_model_dir_copies_to_ascii_cache_for_non_ascii_path(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import ocr_service

    model_root = tmp_path / "中文模型" / "paddleocr" / "whl"
    det_dir = model_root / "det" / "ch" / "ch_PP-OCRv4_det_infer"
    rec_dir = model_root / "rec" / "ch" / "ch_PP-OCRv4_rec_infer"
    cls_dir = model_root / "cls" / "ch_ppocr_mobile_v2.0_cls_infer"
    for directory in [det_dir, rec_dir, cls_dir]:
        directory.mkdir(parents=True)
        (directory / "inference.pdmodel").write_text("model", encoding="utf-8")

    cache_root = tmp_path / "ascii-cache"
    monkeypatch.setenv("PADDLEOCR_MODEL_DIR", str(model_root))
    monkeypatch.setenv("PADDLEOCR_ASCII_CACHE_DIR", str(cache_root))
    get_settings.cache_clear()

    kwargs = ocr_service.get_paddle_ocr_kwargs()

    assert kwargs["det_model_dir"] == str(cache_root / "det" / "ch" / "ch_PP-OCRv4_det_infer")
    assert (cache_root / "det" / "ch" / "ch_PP-OCRv4_det_infer" / "inference.pdmodel").exists()

    monkeypatch.delenv("PADDLEOCR_MODEL_DIR", raising=False)
    monkeypatch.delenv("PADDLEOCR_ASCII_CACHE_DIR", raising=False)
    get_settings.cache_clear()


def test_windows_package_includes_cython_utility_data():
    project_dir = Path(__file__).resolve().parents[2]
    script_text = (project_dir / "scripts" / "package_windows.ps1").read_text(encoding="utf-8")

    assert "Cython\\Utility" in script_text
    assert "CppSupport.cpp" in script_text


def test_windows_package_includes_paddleocr_dynamic_source_data():
    project_dir = Path(__file__).resolve().parents[2]
    script_text = (project_dir / "scripts" / "package_windows.ps1").read_text(encoding="utf-8")

    assert "paddleocrPackageDir" in script_text
    assert "tools\\__init__.py" in script_text
    assert "--add-data \"$paddleocrPackageDir;paddleocr\"" in script_text


def test_windows_package_includes_paddle_native_libraries():
    project_dir = Path(__file__).resolve().parents[2]
    script_text = (project_dir / "scripts" / "package_windows.ps1").read_text(encoding="utf-8")

    assert "paddleLibsDir" in script_text
    assert "mklml.dll" in script_text
    assert "--add-binary \"$paddleLibsDir\\*.dll;paddle\\libs\"" in script_text


def test_windows_package_includes_paddleocr_dynamic_imports():
    project_dir = Path(__file__).resolve().parents[2]
    script_text = (project_dir / "scripts" / "package_windows.ps1").read_text(encoding="utf-8")

    assert "--hidden-import imghdr" in script_text
    assert "--hidden-import shapely" in script_text
    assert "--hidden-import pyclipper" in script_text
    assert "--collect-submodules skimage" in script_text
    assert "--collect-submodules scipy" in script_text
    assert "--collect-submodules imgaug" in script_text
    assert "--hidden-import imgaug" in script_text
    assert "--hidden-import lmdb" in script_text
    assert "--hidden-import rapidfuzz" in script_text
    assert "--hidden-import requests" in script_text
    assert "--hidden-import tqdm" in script_text
    assert "--copy-metadata imageio" in script_text
    assert "--copy-metadata imgaug" in script_text
