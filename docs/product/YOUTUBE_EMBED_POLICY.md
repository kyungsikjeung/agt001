# 유튜브 배경 영상 예외 보안 정책 (2026-10-03)

> 대표 결정(10/3): 첫 화면 영상이 자동으로 재생되게, **유튜브만** 예외로 하는 공개 사이트 보안 정책을 둔다.

## 1. 원래 규칙 (바뀌지 않음)

- 공개 사이트(`/site/<id>/`)는 미리보기 주소에서 열리고, 모든 페이지를 "출처 없는 문서"로 격리한다
  (`Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox`).
- 게시 전 검사(`publish_check`, S-5)는 외부 스크립트·외부 폼·자동 이동·비밀값·격리를 푸는 틀(iframe)을 막는다.
- 예외는 카카오 지도 SDK 한 주소뿐이었다(MAP_CONTRACT §4).

유튜브 플레이어는 격리된 문서 안에서는 재생되지 않는다(플레이어가 자기 출처가 필요). 그래서 예외가 필요하다.

## 2. 예외의 범위 — 아래를 모두 만족할 때만

| # | 조건 | 어디서 지키나 |
|---|---|---|
| Y-1 | 틀은 렌더러가 첫 화면(`hero--video`)에 그린 **한 모양**뿐: `https://www.youtube-nocookie.com/embed/<11자 ID>?autoplay=1&mute=1&loop=1&playlist=<같은 ID>&controls=0&playsinline=1&rel=0&modestbranding=1&iv_load_policy=3&disablekb=1`, `sandbox="allow-scripts allow-same-origin allow-presentation"`, `referrerpolicy="strict-origin-when-cross-origin"`, `allow="autoplay; encrypted-media; picture-in-picture"`, `aria-hidden`·`tabindex=-1`·`data-yt-bg` | `youtube_embed.IFRAME_RE` (템플릿과 글자 하나까지 같아야 함) |
| Y-2 | ID는 영문·숫자·`_`·`-` 11자, 사장님이 준 유튜브 주소를 `parse_video_url`로 읽은 것만 | `youtube_embed.video_id` |
| Y-3 | 게시 전 검사는 Y-1 모양의 틀**만** 빼고 나머지를 원래대로 본다. 값 하나라도 다르면(조작 단추 켜기, 다른 주소, 격리 해제 토큰 추가, 재생목록 ID 바꾸기, sandbox 빼기) 원래 규칙으로 판정 | `publish_check.check_html` |
| Y-4 | 공개 사이트를 줄 때 페이지에 Y-1 틀이 있고 게시 전 검사를 통과할 때**만** 유튜브 전용 헤더 | `public._site_headers` → `youtube_embed.page_uses_youtube` |

유튜브 전용 헤더(`SITE_CSP_YOUTUBE`):

```
sandbox allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox;
frame-src https://www.youtube-nocookie.com; child-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'
```

- 격리에 `allow-same-origin`이 더해진다(유튜브 플레이어가 동작하려면 필요).
- 대신 페이지 안의 틀은 브라우저가 **youtube-nocookie 주소만** 열게 묶는다. 다른 외부 틀은 열리지 않는다.
- `allow-top-navigation`은 끝까지 주지 않는다(페이지가 바깥 창을 다른 곳으로 보낼 수 없음).
- 유튜브 일반 주소가 아니라 `youtube-nocookie.com`(재생 전 추적 쿠키를 덜 쓰는 주소)을 쓴다.

## 3. 화면

- 소리 끔·반복·조작 없음으로 첫 화면을 꽉 채운다. 누를 수 없는 배경이고, 오른쪽 아래 "▶ 소리 켜고 보기"는 유튜브로 연다.
- 영상 아래에 유튜브 썸네일이 깔려 있어, 저전력 모드·차단·느린 연결로 재생이 안 되면 그대로 썸네일이 보인다.
- 움직임 줄이기 설정이면 영상을 숨기고 썸네일만 보인다.
- 인스타그램·네이버TV는 배경 재생을 지원하지 않아 기존 표지(썸네일 + ▶ 재생 단추)로 보인다.
- 실시간 대화 미리보기·시안 3안 페이지는 격리를 그대로 두므로 렌더러가 **공개본에서만** 배경 틀을 넣는다(`render_site(public=True)`).
  시안·미리보기에는 틀 없이 썸네일과 "소리 켜고 보기"만 보인다(깨진 틀이 썸네일을 가리지 않게).

## 4. 남는 위험과 대비

| 위험 | 대비 |
|---|---|
| 예외 페이지의 스크립트가 미리보기 주소의 브라우저 저장소에 닿을 수 있음 | 공개 사이트에는 우리 렌더러 스크립트만 들어간다(외부 스크립트는 게시 전 검사가 막음). 미리보기 주소의 쿠키(`pv_*`)는 httponly라 스크립트가 못 읽는다. 앱 주소의 로그인 쿠키는 다른 주소라 닿지 않는다 |
| 유튜브 쪽 추적 | nocookie 주소, 소리 끔. 개인정보처리방침에 "유튜브 영상을 넣으면 유튜브가 시청 정보를 처리할 수 있음" 문구 추가 필요(법률 검토 때) |
| 유튜브가 주소 규칙을 바꿈 | 재생이 안 돼도 썸네일이 보이므로 화면이 깨지지 않는다 |

## 5. 검증

`tests/unit/test_youtube_embed.py` 5개: 유튜브만 배경 틀이 생김(인스타·빈 주소는 틀 없음), 틀을 한 군데라도 고치면 예외 탈락·게시 차단,
전용 헤더 내용, 공개 사이트 서빙이 유튜브 페이지에만 전용 헤더를 주고 고친 파일은 원래 헤더를 받는지.
이 작업 환경은 유튜브 접속이 막혀 있어(조직 네트워크 정책) **실제 재생은 운영 서버에서 휴대폰으로 확인 필요**.

## 6. 연결

실시간 대화에서 고른 첫 화면(영상 포함)은 시안 1안("말로 고른 안")에 들어가고, 1안을 공개하면 이 정책이 공개 사이트에서 작동한다
(COMPOSE_INTERVIEW_CONTRACT §11).
