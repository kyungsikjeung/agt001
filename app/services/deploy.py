"""배포: 코드생성 산출물(generated/<id>/web)을 백엔드가 /site/<id>/ 로 직접 서빙한다."""
from typing import Optional

from app.config import settings


def site_url(requirement_id: str, base_url: str) -> Optional[str]:
    web_dir = settings.generated_dir / requirement_id / "web"
    if not web_dir.is_dir() or not any(web_dir.iterdir()):
        return None
    base = (settings.public_base_url or base_url).rstrip("/")
    return f"{base}/site/{requirement_id}/"
