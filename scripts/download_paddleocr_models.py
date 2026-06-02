from pathlib import Path


MODEL_ROOT = Path(__file__).resolve().parents[1] / "offline" / "paddleocr" / "whl"
MODEL_SPECS = [
    (
        MODEL_ROOT / "det" / "ch" / "ch_PP-OCRv4_det_infer",
        "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar",
    ),
    (
        MODEL_ROOT / "rec" / "ch" / "ch_PP-OCRv4_rec_infer",
        "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar",
    ),
    (
        MODEL_ROOT / "cls" / "ch_ppocr_mobile_v2.0_cls_infer",
        "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar",
    ),
]


def main() -> None:
    """Download PaddleOCR Chinese models to the offline directory."""
    from paddleocr.ppocr.utils.network import maybe_download

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    for model_dir, url in MODEL_SPECS:
        maybe_download(str(model_dir), url)
        required_file = model_dir / "inference.pdmodel"
        if not required_file.exists():
            raise FileNotFoundError(f"PaddleOCR model file is missing: {required_file}")
    print(f"PaddleOCR models are ready at: {MODEL_ROOT}")


if __name__ == "__main__":
    main()
