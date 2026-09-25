"""배포: 코드생성 산출물(generated/<id>/web)을 백엔드가 /site/<id>/ 로 직접 서빙한다."""
from typing import Optional

from app.config import settings


def site_url(requirement_id: str, base_url: str) -> Optional[str]:
    base_dir = settings.generated_dir / requirement_id
    if not any(d.is_dir() and any(d.iterdir()) for d in (base_dir / "published", base_dir / "web")):
        return None
    base = f"https://{settings.preview_host}" if settings.preview_host else (settings.public_base_url or base_url).rstrip("/")
    return f"{base}/site/{requirement_id}/"
