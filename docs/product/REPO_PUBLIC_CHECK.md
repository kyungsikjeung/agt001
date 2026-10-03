# 저장소 공개 전 점검 (REPO_PUBLIC_CHECK)

> 2026-10-02 (KST) / Claude. 로드맵 P2-5, 백로그 M-12(저장소 공개 전환은 마지막에 대표가 직접).
> 공개로 바꾸기 **직전에 한 번 더** 아래 §3으로 다시 돌린다. 그 사이 커밋이 늘었을 수 있다.

## 1. 결론

전체 이력(모든 브랜치, 421개 커밋)에서 **진짜 비밀값은 나오지 않았다.** 걸린 8건은 모두 오탐이다.
공개 전에 대표가 판단할 것은 §2-2의 "노출돼도 되는 정보" 3가지뿐이다.

## 2. 결과

### 2-1. 비밀값 검사 (gitleaks 8.21.2, 기본 규칙)

| 걸린 곳 | 값 | 판단 |
|---|---|---|
| `tests/unit/test_settings_api.py`, `test_shop_settings.py` (3곳) | `SOLAPIKEY1234` 등 | 테스트용 가짜 값 |
| `tests/unit/test_publish_check.py` | `sk-abcdefgh12345678` | 게시 차단 검사가 잡는지 보는 가짜 값 |
| `static/room.html`, `static/index.html` (이력 여러 판) | `KAKAO_JS_KEY` | **카카오 JavaScript 키 = 공개 키.** 브라우저에 그대로 내려가는 값이고, 카카오 콘솔에 등록한 도메인에서만 동작한다 |
| `static/room.html` | `agt001_claimed_` | 브라우저 저장소 이름(비밀 아님) |

추가로 직접 찾은 것(전체 이력): 개인키(`BEGIN … PRIVATE KEY`), OCI OCID, NVIDIA(`nvapi-`)·구글(`AIza`, `GOCSPX-`) 키 → 테스트의 가짜 값(`GOCSPX-abcdefgh`) 1건 말고 없음.
`.env`·`.pem`·`id_rsa`·`oci_agt001` 파일이 커밋된 적 없음(`.env.example`만 있고, 모든 판의 값이 비어 있음).

### 2-2. 비밀은 아니지만 공개되면 보이는 것

| 무엇 | 어디 | 추천 |
|---|---|---|
| 운영 서버 IP `144.24.91.250`와 SSH 사용자 `ubuntu` | `scripts/deploy.sh`, `pull_backups.sh`, 문서 약 40곳 | 사이트 주소에 이미 IP가 들어 있어 숨길 수 없다. 대신 **SSH는 키로만**(비밀번호 로그인 꺼짐) 확인, 가능하면 OCI 보안 목록에서 22번 포트를 대표 IP로 좁힌다. 전용 도메인(P2-3) 뒤에는 기본값을 도메인으로 바꾼다 |
| SSH 키 파일 이름 `~/.ssh/oci_agt001` | 같은 스크립트·문서 | 이름만 보이고 키는 없다. 그대로 둬도 된다. 키 교체(P0-1) 뒤 이름이 바뀌면 같이 고친다 |
| 내부 기획 문서(`docs/hackathon`, `docs/product`의 사업 전략·결정 기록) | 문서 폴더 | 경쟁사가 읽어도 되는지 대표 판단. 숨기려면 공개 전에 별도 비공개 저장소로 옮긴다(이력에서 지우려면 이력 다시 쓰기가 필요해 번거롭다) |

## 3. 다시 돌리는 법

```bash
# gitleaks 받기 (Mac은 brew install gitleaks)
curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz | tar xz gitleaks
git fetch origin '+refs/heads/*:refs/remotes/origin/*'   # 모든 브랜치 이력까지
./gitleaks git --log-opts="--all" -c .gitleaks.toml .    # "no leaks found"면 통과
```

확인된 오탐은 `.gitleaks.toml`에 이유와 함께 좁게 빼 두었다. 새로 걸리는 것이 있으면:

1. 진짜 값이면 **먼저 그 키를 폐기·재발급**한다(이력에서 지워도 이미 복사됐을 수 있다). 그다음 이력에서 지울지 정한다.
2. 오탐이면 `.gitleaks.toml`에 경로나 값을 좁게 추가하고 이유를 적는다.

## 4. 공개 전환 직전 순서

1. P0-1(유출된 서버 키 교체·API 키 재발급)이 끝났는지 확인.
2. §3을 다시 돌려 통과.
3. §2-2의 문서 공개 여부 결정.
4. GitHub 설정 → Danger Zone → Change visibility (대표).
