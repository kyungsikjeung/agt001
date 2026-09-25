"""헬스체크, 시안 페이지, 생성 사이트 서빙."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import settings
from app.security import sanitize_token

router = APIRouter()


def _project_dir(requirement_id: str, sub: str):
    safe_id = sanitize_token(requirement_id)
    if not safe_id:
        raise HTTPException(status_code=404)
    return settings.generated_dir / safe_id / sub


@router.get("/", include_in_schema=False)
def home():
    # 랜딩(React). 빌드 전(단위 테스트·CI)에는 기존 1:1 채팅 화면으로 폴백한다.
    index = settings.frontend_dist_dir / "index.html"
    return FileResponse(index if index.is_file() else settings.static_dir / "index.html")


@router.get("/landing.html", include_in_schema=False)
def old_landing():
    # 예전 랜딩 주소로 공유된 링크를 새 랜딩으로 보낸다.
    return RedirectResponse("/", status_code=308)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/design/{requirement_id}", response_class=HTMLResponse)
def design_page(requirement_id: str):
    path = _project_dir(requirement_id, "design") / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/design/{requirement_id}/preview.png")
def design_preview(requirement_id: str):
    path = _project_dir(requirement_id, "design") / "preview.png"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")


@router.get("/site/{requirement_id}")
def site_root_redirect(requirement_id: str):
    return RedirectResponse(url=f"/site/{requirement_id}/", status_code=308)


@router.get("/site/{requirement_id}/")
@router.get("/site/{requirement_id}/{filename:path}")
def serve_site(requirement_id: str, filename: str = ""):
    web_dir = _project_dir(requirement_id, "web")
    if not web_dir.is_dir():
        raise HTTPException(status_code=404)
    root = web_dir.resolve()
    target = (root / (filename or "index.html")).resolve()
    # 경로 순회 방어: 해석된 경로가 반드시 산출물 디렉터리 안이어야 한다.
    if not target.is_relative_to(root):
        raise HTTPException(status_code=404)
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)
