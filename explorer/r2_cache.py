"""
R2 download + local disk cache for PDFs and Docling JSONs.

Downloads from Cloudflare R2 via S3 API on first access, serves from local cache thereafter.
Falls back to local sources/ paths if R2 credentials are not set (dev mode).
"""

import json
import os
from pathlib import Path

R2_CACHE_DIR = Path("/tmp/fobe_r2_cache")
REPO_ROOT = Path(__file__).resolve().parent.parent

# R2 S3-compatible credentials
_R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", "")
_R2_SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
_R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "4d91c98cd766fafa9943c72a61d60037")
_R2_BUCKET = os.environ.get("R2_BUCKET", "fobe")

_s3_client = None


def _get_s3():
    """Lazy-init S3 client for R2."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    if not _R2_ACCESS_KEY or not _R2_SECRET_KEY:
        return None
    try:
        import boto3
        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"https://{_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=_R2_ACCESS_KEY,
            aws_secret_access_key=_R2_SECRET_KEY,
            region_name="auto",
        )
        return _s3_client
    except Exception:
        return None


def _ensure_cache_dir():
    R2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (R2_CACHE_DIR / "pdfs").mkdir(exist_ok=True)
    (R2_CACHE_DIR / "docling").mkdir(exist_ok=True)


def _download_from_r2(r2_path: str, dest: Path) -> bool:
    """Download a file from R2 to dest via S3 API. Returns True on success."""
    s3 = _get_s3()
    if not s3:
        return False
    # r2_path is like "/pdfs/amag_2024.pdf" — strip leading slash for S3 key
    key = r2_path.lstrip("/")
    try:
        s3.download_file(_R2_BUCKET, key, str(dest))
        return True
    except Exception:
        # Clean up partial download
        if dest.exists():
            dest.unlink()
        return False


def get_pdf_path(slug: str, pdf_url: str | None = None) -> Path | None:
    """
    Get local path to a PDF, downloading from R2 if necessary.

    Args:
        slug: Document slug (e.g. "amag_2024")
        pdf_url: R2 URL path from documents.pdf_url (e.g. "/pdfs/amag_2024.pdf")

    Returns:
        Local file path, or None if unavailable.
    """
    _ensure_cache_dir()
    cached = R2_CACHE_DIR / "pdfs" / f"{slug}.pdf"

    if cached.exists():
        return cached

    # Try R2 download
    if pdf_url:
        if _download_from_r2(pdf_url, cached):
            return cached

    # Fallback: local sources/ directory (dev mode)
    for gaap_dir in ("ifrs", "ugb", "hgb"):
        gaap_path = REPO_ROOT / "sources" / gaap_dir
        if gaap_path.is_dir():
            # Direct match
            candidate = gaap_path / f"{slug}.pdf"
            if candidate.exists():
                return candidate
            # Subdirectory match (country codes under ifrs/)
            for subdir in gaap_path.iterdir():
                if subdir.is_dir():
                    candidate = subdir / f"{slug}.pdf"
                    if candidate.exists():
                        return candidate

    return None


def get_docling_json(slug: str, docling_url: str | None = None) -> dict | None:
    """
    Get parsed Docling JSON, downloading from R2 if necessary.

    Args:
        slug: Document slug
        docling_url: R2 URL path from documents.docling_url

    Returns:
        Parsed JSON dict, or None if unavailable.
    """
    _ensure_cache_dir()
    cached = R2_CACHE_DIR / "docling" / f"{slug}.json"

    if cached.exists():
        with open(cached) as f:
            return json.load(f)

    # Try R2 download
    if docling_url:
        if _download_from_r2(docling_url, cached):
            with open(cached) as f:
                return json.load(f)

    # Fallback: local fixture directory
    local = REPO_ROOT / "eval" / "fixtures" / slug / "docling_elements.json"
    if local.exists():
        with open(local) as f:
            return json.load(f)

    return None
