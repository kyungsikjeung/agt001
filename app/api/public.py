"""헬스체크, 시안 페이지, 생성 사이트 서빙."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import settings
from app.security import sanitize_token

router = APIRouter()


# AI가 만든 페이지는 앱과 같은 주소에서 열리므로, 브라우저가 이 페이지를 "출처 없는 문서"로
# 다루게 해 앱의 브라우저 저장소(채팅방 본인 확인 값)와 쿠키에 손대지 못하게 한다.
# 별도 미리보기 주소로 옮기기 전의 임시 격리다 (docs/product/DESIGN_PIPELINE_PLAN.md §13, 보안 P0).
_SITE_HEADERS = {
    # 스크립트는 허용하되(생성 사이트 동작), 앱 출처로 취급되지 않게 한다. 외부 링크 새 탭과 문의 폼 전송은 허용.
    "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox",
    "X-Content-Type-Options": "nosniff",
}
_DESIGN_HEADERS = {
    # 시안은 보기 전용: 스크립트·폼·팝업 모두 불필요. 검색 노출 금지.
    "Content-Security-Policy": "sandbox; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex",
}


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


@router.get("/editor", include_in_schema=False)
def editor():
    # 사장님용 직접 편집 화면(P-10a). 지금은 목업 데이터로만 동작하는 프로토타입이다.
    page = settings.frontend_dist_dir / "editor.html"
    if not page.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(page)


@router.get("/projects", include_in_schema=False)
def projects_page():
    # 내 프로젝트(1-1b): 이 기기에서 연 방 + 로그인하면 계정에 옮긴 방.
    page = settings.frontend_dist_dir / "projects.html"
    if not page.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(page)


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
    return HTMLResponse(path.read_text(encoding="utf-8"), headers=_DESIGN_HEADERS)


@router.get("/design/{requirement_id}/{variant}/", response_class=HTMLResponse)
def design_variant_page(requirement_id: str, variant: str):
    # 시안 3안 각각 (C7). 보기 전용 CSP는 고르기 페이지와 같다.
    if variant not in ("v1", "v2", "v3"):
        raise HTTPException(status_code=404)
    path = _project_dir(requirement_id, "design") / variant / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"), headers=_DESIGN_HEADERS)


@router.get("/design/{requirement_id}/{variant}.png")
def design_variant_preview(requirement_id: str, variant: str):
    # /preview.png(카카오 미리보기, 1안)도 이 경로 모양에 걸리므로 함께 받는다.
    if variant not in ("v1", "v2", "v3", "preview"):
        raise HTTPException(status_code=404)
    path = _project_dir(requirement_id, "design") / f"{variant}.png"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/design/{requirement_id}/preview.png")
def design_preview(requirement_id: str):
    path = _project_dir(requirement_id, "design") / "preview.png"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/uploads/{room_id}/{filename}")
def uploaded_photo(room_id: str, filename: str):
    # 채팅방에 올린 사진(위치 정보 지운 JPEG). 생성물 전용 주소에서 연다(app/main.py _split_hosts).
    safe_room = sanitize_token(room_id)
    stem = filename[:-4] if filename.endswith(".jpg") else ""
    if not safe_room or not stem or sanitize_token(stem) != stem:
        raise HTTPException(status_code=404)
    path = settings.generated_dir / "uploads" / safe_room / f"{stem}.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=86400"})


@router.get("/site/{requirement_id}")
def site_root_redirect(requirement_id: str):
    return RedirectResponse(url=f"/site/{requirement_id}/", status_code=308)


@router.get("/site/{requirement_id}/")
@router.get("/site/{requirement_id}/{filename:path}")
def serve_site(requirement_id: str, filename: str = ""):
    # 사장님이 고른 시안을 공개했으면 그것을, 아니면 코드생성 결과를 연다.
    web_dir = _project_dir(requirement_id, "published")
    if not web_dir.is_dir():
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
    return FileResponse(target, headers=_SITE_HEADERS)
