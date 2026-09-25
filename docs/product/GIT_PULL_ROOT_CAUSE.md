# GIT_PULL 근본 원인 조사 (GIT_PULL_ROOT_CAUSE)

> 작성일: 2026-09-25 (UTC) / 성격: 근본 원인 조사 문서. **코드는 수정하지 않는다.**
> 범위: 로컬 개발 머신 + OCI 인스턴스(`ubuntu@144.24.91.250`, `~/agt001`)에서 **읽기 전용 명령만** 사용.
> 제약: `git add/commit/push` 없음, OCI에서 설정 변경·키 생성·파일 수정·clone 덮어쓰기·docker·배포 스크립트 실행 없음,
> `.env`/토큰 미열람. 임시 디렉터리(`/tmp/gitprobe-*`)의 공개 저장소 `ls-remote`만 예외적으로 허용됨.
> 관련 기존 추정: `docs/hackathon/EFFICIENCY_PLAN.md` §4-③, `docs/hackathon/DEPLOYMENT_STRATEGY.md` §1-1
> ("Oracle 무료티어 IP가 GitHub에서 차단" — 본 조사에서 검증, 아래 결론 참조).

## 0. 결론 요약 (3줄)

- **근본 원인: 저장소 `kyungsikjeung/agt001`이 private인데 OCI 인스턴스에 GitHub 인증 수단이 전혀 없어서 발생한 정상적인 인증 실패다.**
  GitHub는 인증 없는 private 저장소 요청에 `404`를 반환하고, 자격증명 없이 `git pull/fetch`를 하면
  `fatal: could not read Username for 'https://github.com'`이 난다. 차단·DNS·프록시·URL 오타가 아니다.
- **기존 추정("Oracle 무료티어 IP 차단")은 기각.** OCI에서 공개 저장소는 API·git 모두 정상 도달한다.
- **추천 해결책: (a) 읽기 전용 Deploy Key 1개 등록 + OCI 원격을 SSH로 전환 후 `git pull`.**
  저장소 1개 한정·읽기 전용·사용자 계정과 무관·만료 관리 불필요라 (b) PAT보다 안전하고 운영 부담이 적다.

---

## 1. 가설별 검증 (실제 명령 + 결과 + 판정)

### H1. 저장소가 실제로는 private이다 → ✅ 확인 (근본 원인)

| # | 명령 (실행 위치) | 결과 |
|---|---|---|
| H1-1 | 로컬: `gh repo view kyungsikjeung/agt001 --json visibility,isPrivate,nameWithOwner,url` | `{"isPrivate":true, "visibility":"PRIVATE", "nameWithOwner":"kyungsikjeung/agt001"}` — **저장소는 private 확정** |
| H1-2 | 로컬 익명: `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy curl -s -o /dev/null -w '%{http_code}' https://api.github.com/repos/kyungsikjeung/agt001` | `404` |
| H1-3 | 로컬 프록시 경유: `curl -s -o /dev/null -w '%{http_code}' https://api.github.com/repos/kyungsikjeung/agt001` (env의 `HTTPS_PROXY=http://127.0.0.1:49532` 그대로) | `404` — **프록시가 인증을 붙여주지 않는다. "로컬에서는 프록시 덕에 공개처럼 보였다"는 부가설은 기각.** 로컬에서 정상 동작하는 이유는 프록시가 아니라 아래 H1-6/H1-7의 저장된 자격증명이다 |
| H1-4 | OCI: `curl -s -m 15 -o /dev/null -w "private:%{http_code}\n" https://api.github.com/repos/kyungsikjeung/agt001` | `private:404` — 로컬 익명(H1-2)과 동일 |
| H1-5 | OCI: `curl ... https://raw.githubusercontent.com/kyungsikjeung/agt001/main/README.md` | `raw:404` — 보고된 "codeload·raw 404"와 일치. private 저장소의 인증 없는 접근에 대한 GitHub의 정상 응답이다 |
| H1-6 | 로컬: `GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/kyungsikjeung/agt001.git HEAD` (osxkeychain 자격증명 사용) | `7474d5bd... HEAD` 성공 — **같은 URL이 자격증명만 있으면 정상.** URL 오타(H4)도 함께 기각되는 증거 |
| H1-7 | 로컬: `gh auth status` | `Logged in to github.com account kyungsikjeung (keyring)`, `Git operations protocol: https` — 로컬 git 인증 경로(`credential.helper=osxkeychain` + keyring의 `gh` 토큰) 확인. 토큰 값은 출력·열람하지 않음 |
| H1-8 | **OCI에서 보고된 오류의 직접 재현:** `GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/kyungsikjeung/agt001.git HEAD` | `fatal: could not read Username for 'https://github.com': terminal prompts disabled` — **보고된 오류와 정확히 일치.** OCI의 git이 2.25.1(구버전)이라 메시지가 `could not read Username` 형태이며, 신버전 git의 `Authentication failed`와 같은 의미다 |
| H1-9 | 로컬 대조군(자격증명 제거 시뮬레이션): `GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=echo git -c credential.helper= ls-remote https://github.com/kyungsikjeung/agt001.git HEAD` | `remote: Invalid username or token... / fatal: Authentication failed` — 자격증명만 제거해도 실패. 인증 부재가 원인임을 로컬에서도 재확인 |

**판정: H1 확인.** 모든 증상(`git pull/fetch`의 Username 오류, api·codeload·raw의 404)은 "인증 없는 private 저장소 접근" 한 가지로 전부 설명된다.

### H2. OCI IP/대역이 GitHub에서 차단 → ❌ 기각

| # | 명령 (OCI) | 결과 |
|---|---|---|
| H2-1 | `curl ... https://api.github.com/repos/git/git` (공개 저장소) | `public:200` — 차단 상태라면 공개 저장소도 막히거나 rate-limit 응답이어야 하는데 정상 |
| H2-2 | `curl ... https://api.github.com/zen` | `zen:200` |
| H2-3 | `curl ... https://github.com` | `200`, `time:0.04s` — github.com 본체도 정상·고속 도달 |
| H2-4 | `mkdir -p /tmp/gitprobe-agt001 && git ls-remote https://github.com/git/git.git HEAD` | `0f8e75ab... HEAD` 성공 (로컬 동일 명령의 SHA와 일치) — **git 스마트 프로토콜(443/TLS)도 차단 없음** |
| H2-5 | `getent hosts github.com / api.github.com` | 정상 해석 (`20.200.245.247`, `20.200.245.245`) |

**판정: H2 기각.** API·웹·git 프로토콜 모두 OCI에서 GitHub에 정상 도달한다. "무료티어 IP 차단"이라면 공개 리소스도 실패해야 하는데 전부 성공하므로 성립하지 않는다.

### H3. DNS/IPv6/MTU/프록시 설정 문제 → ❌ 기각

| # | 명령 (OCI) | 결과 |
|---|---|---|
| H3-1 | `getent hosts github.com` / `api.github.com` | 정상 해석 (H2-5와 동일) — DNS 정상 |
| H3-2 | `curl -v https://github.com` 요약 | `Connected to github.com (20.200.245.247) port 443`, `SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256` — TCP·TLS 핸드셰이크 정상 |
| H3-3 | `env \| grep -i proxy` | `(no proxy env)` — 프록시 없음. 잘못된 프록시 설정 가능성 없음 |
| H3-4 | `git config --list --show-origin` | **출력 없음.** `credential.helper`, `url.insteadOf`, `http.proxy` 설정이 전무 — 즉 프롬프트 불가 환경에서 인증 방법이 아예 없는 상태. 이는 "설정 문제"라기보다 H1(인증 수단 미등록)의 직접 증거다 |

**판정: H3 기각.** DNS·TLS·프록시 모두 정상이며, 텅 빈 git 설정은 차단이 아니라 미인증 상태를 가리킨다.

### H4. 원격 URL 오타·리네임 → ❌ 기각

| # | 명령 | 결과 |
|---|---|---|
| H4-1 | OCI: `git -C ~/agt001 remote -v` | `origin https://github.com/kyungsikjeung/agt001.git (fetch/push)` |
| H4-2 | 로컬: `git remote -v` | 동일 URL. 양쪽 일치 |
| H4-3 | `gh repo view ... --json nameWithOwner,url` | `kyungsikjeung/agt001`, `https://github.com/kyungsikjeung/agt001` — 원격 URL과 저장소 정식명이 일치, 리네임 흔적 없음 |
| H4-4 | H1-6: 같은 URL로 로컬(인증 있음) `ls-remote` 성공 | URL 자체는 유효 |

**판정: H4 기각.**

---

## 2. 근본 원인 (확정)

1. `kyungsikjeung/agt001`은 **private 저장소**다 (`gh repo view` 실측).
2. OCI 인스턴스의 git 설정은 **완전히 비어 있고**(`git config --list` 출력 없음 → credential helper 없음),
   프록시도 없으며, SSH 키·PAT 등 어떤 GitHub 자격증명도 등록되어 있지 않다.
3. GitHub는 **인증 없는 private 저장소 접근에 404를 반환**하도록 설계되어 있다
   (존재 여부 노출 방지). 그래서 `api`·`codeload`·`raw` 요청이 전부 404처럼 "차단"처럼 보였다.
4. `git pull/fetch`는 HTTPS 원격에 자격증명이 필요하지만, 비대화형 SSH 세션에서 사용자명을 물을 수 없어
   `fatal: could not read Username for 'https://github.com'`으로 실패한다 (OCI git 2.25.1의 메시지).
   OCI에서 `GIT_TERMINAL_PROMPT=0`으로 재현해 **동일 오류를 확인**했다.
5. 로컬에서는 `credential.helper=osxkeychain` + keyring의 `gh` 인증 덕분에 같은 URL이 성공하므로,
   "로컬은 되고 OCI만 안 된다"는 비대칭이 생겼고, 이것이 IP 차단이라는 오인으로 이어졌다.
   로컬 `HTTPS_PROXY(127.0.0.1:49532)`는 curl 실측상 인증을 덧붙이지 않으므로 무관하다.

**기존 추정이 틀리게 보인 메커니즘:** private-404는 겉보기에 "차단"과 구별이 안 된다.
둘을 가르는 검사는 **공개 저장소 대조군**(H2-1~H2-4)이며, 대조군이 전부 성공하므로 차단은 기각된다.

### 참고: OCI 작업 트리의 관측 상태 (원인과 별개, 배포 설계용 메모)

- OCI `~/agt001`의 git HEAD는 `3f88354`로 로컬 `main`(`b1b8f69`)보다 뒤에 있고,
  작업 트리에 변경분도 있다 (`M .gitignore/README.md/docker-compose.yml`, `D backend.py` — FastAPI 이식 이후 rsync 배포와 무관하게 진행된 로컬 커밋이 미반영).
  이는 `git pull` 실패와 별개인 **배포 드리프트**이며, pull 방식으로 전환하면 해소되는 범주다.

---

## 3. 근본 해결책 비교와 추천

| 안 | 개요 | 보안 | 운영 | 적합성 |
|---|---|---|---|---|
| **(a) 읽기 전용 Deploy Key + SSH (추천)** | 해당 저장소 전용 SSH 키 1쌍을 만들고 공개키를 GitHub 저장소 Settings → Deploy keys에 **읽기 전용(Allow write access 미체크)** 으로 등록. OCI 원격을 `git@github.com:kyungsikjeung/agt001.git`로 전환 후 `git pull` | 최상. 저장소 1개 한정, 읽기 전용이라 키 유출 시에도 코드 유출 이상의 피해 없음. 사용자 계정과 무관 | 최상. 만료 없음, PAT처럼 주기 갱신 불필요. 키 1쌍을 OCI `~/.ssh`에만 보관 | private 단일 저장소의 서버 pull이라는 조건에 정확히 맞는 표준 해법 |
| (b) Fine-grained PAT + credential helper | 읽기 전용·저장소 1개 한정·만료 설정 PAT 발급 → OCI에 `git credential helper(store)` 등으로 저장 | 중. 사용자 계정에 귀속되므로 토큰 유출 시 발급자 권한 범위 주의. 만료 설정이 안전장치이자 운영 부담 | 중하. 만료마다 재발급·재배포 필요. 데모·마감 주간에 만료되면 배포가 멈추는 리스크 | (a)가 안 되는 조직 정책이 있을 때의 차선 |
| (c) 저장소를 public으로 전환 | 인증 자체가 불필요해짐 | **하. 비권장.** `git grep` 실측 결과 공개 IP(`144.24.91.250`)가 STATUS·Caddyfile·다수 문서와 커밋 히스토리에 포함되어 있다. public 전환 전 히스토리 전체의 비밀정보(IP·이메일·향후 `.env` 오커밋 가능성) 정밀 점검이 필수이며, 히스토리는 rewrite해도 포크·캐시에 잔존할 수 있다 | 한 번 뒤집으면 되돌리기 어려움(노출은 되돌릴 수 없음) | 보안 점검 없이는 선택 불가. 현 시점 비추천 |
| (d) GitHub Actions에서 OCI로 push 배포 | Actions 러너가 체크아웃 후 SSH/rsync로 OCI에 전송. OCI는 GitHub를 전혀 보지 않음 | 중상. OCI 접속용 SSH 키를 Actions secret에 보관. GitHub 측 secret 관리 필요 | 중. 워크플로 작성·디버깅 비용 | 0-4b 스테이징 → 운영 자동 배포(CD)를 만들 때 함께 검토 |

**추천: (a).** 이유 — 최소 권한(저장소 한정·읽기 전용)·최소 운영(무만료)·표준 관행의 세 조건을 동시에 만족하는 유일한 안이다.
현행 rsync 우회로는 (a) 전환 후에도 롤백용으로 남길 수 있으나, 정식 경로는 "OCI에서 `git pull`"로 일원화하는 것이 드리프트(§2 참고) 방지에 유리하다.

### 사용자가 GitHub/OCI에서 직접 해야 할 단계 (본 과제의 읽기 전용 제약을 벗어나므로 사용자가 수행)

> 아래는 모두 쓰기·설정 변경 작업이라 본 조사에서는 실행하지 않았다. 순서대로 수행한다.

**GitHub 측 (브라우저):**

1. 저장소 `kyungsikjeung/agt001` → Settings → Deploy keys → Add deploy key.
2. Title은 식별 가능하게 (예: `oci-agt001-prod-readonly`), Key에 아래 4단계의 공개키(`.pub`) 내용 붙여넣기.
3. **`Allow write access`는 반드시 체크 해제** (읽기 전용).
4. Add key 확정.

**OCI 측 (SSH, 1회성 설정):**

1. `ssh-keygen -t ed25519 -f ~/.ssh/agt001-deploy -N "" -C "oci-agt001-prod-readonly"` (passphrase 없음 — 무인 pull용).
2. `cat ~/.ssh/agt001-deploy.pub` 내용을 위 GitHub 단계에 등록.
3. `~/.ssh/config`에 Host 별칭 추가 (정확한 키 사용 보장):
   `Host github-agt001 / HostName github.com / User git / IdentityFile ~/.ssh/agt001-deploy / IdentitiesOnly yes`.
4. 연결 확인(읽기 전용): `ssh -T github-agt001` (Deploy Key는 shell 불가이므로 "successful authentication but shell access not allowed" 성격의 메시지가 정상).
5. 원격 전환 + pull: `git -C ~/agt001 remote set-url origin github-agt001:kyungsikjeung/agt001.git` 후 (3단계 별칭을 써야 이 키가 쓰인다)
   `git -C ~/agt001 pull --ff-only`. 단, §2의 작업 트리 변경분(`M`/`D`)이 있으면 pull이 거부될 수 있으니
   먼저 `git -C ~/agt001 status --short`로 확인하고, 배포 산출물 덮어쓰기가 의도된 것인지 판단 후
   (`git stash` 보관 또는 `git checkout -- .` 정리 — **판단은 사용자가 직접**) 진행한다.

### `scripts/deploy.sh`를 "OCI에서 git pull" 방식으로 바꿀 때의 변경 요지 (설계만, 코드 수정 없음)

- 현행(읽기 전용 열람 기준, 133줄): 로컬→원격 `rsync --delete`(일부 제외) → `Dockerfile.backend`+`requirements.txt` 해시 비교(`.deploy_build_marker`) → 조건부 `up -d --build`/`restart backend` → warmup 헬스체크.
- 변경 후 스케치: ① rsync 단계를 `ssh ... 'git -C ~/agt001 fetch --prune && git -C ~/agt001 pull --ff-only'`로 교체.
  ② 빌드 조건 판단 기준을 "로컬 `git diff`"에서 "원격 pull 전후 SHA 비교"(`git rev-parse HEAD` 전후 또는 `CHANGELOG` 성격의 출력)로 교체 — 나머지(마커 비교·조건부 빌드·warmup) 로직은 그대로 재사용.
  ③ rsync 제외 규칙(`.env`/`generated`)에 대응해 `.gitignore`·`.git/info/exclude` 정책을 명문화 (pull 방식에서는 제외가 git 추적 여부로 바뀌므로, 원격 전용 파일이 추적 대상에 섞이지 않도록 `.gitignore` 감사 1회 필요).
  ④ `rollback.sh`(스냅샷 tarball 방식, DEPLOYMENT_STRATEGY §3-3 안 C)는 pull 전환 후에도 유효 — 롤백은 `git -C ~/agt001 reset --hard <직전SHA>` + 마커 복원 + 재시작/warmup으로 단순화 가능하나, 디렉터리 스냅샷은 "git 작업 트리가 깨졌을 때"의 보험으로 유지 권장.
  ⑤ SSH 원격 전환 시 `known_hosts`(github.com) 등록 1회가 선행되어야 최초 pull이 비대화형으로 통과한다.

---

## 부록: 원시 결과 로그 (발췌)

```
# 로컬
gh repo view → {"isPrivate":true,"nameWithOwner":"kyungsikjeung/agt001","visibility":"PRIVATE"}
anon  api private → 404        proxied api private → 404        anon raw private → 404
anon  api public git/git → 200   proxied public → 200           anon zen → 200
git ls-remote private (keychain) → 7474d5bd... HEAD (성공)
git ls-remote private (helper 제거) → "Authentication failed" (실패)
git ls-remote public (helper 제거) → 0f8e75ab... HEAD (성공)

# OCI (ssh ubuntu@144.24.91.250, 전부 읽기 전용)
git remote -v → https://github.com/kyungsikjeung/agt001.git (양방향)
git config --list --show-origin → (출력 없음)
env proxy → (없음)
getent github.com → 20.200.245.247 / api.github.com → 20.200.245.245
curl github.com → 200 (0.04s) / zen → 200 / api private → 404 / api public → 200 / raw private → 404
curl -v → Connected ... port 443, TLSv1.3 / TLS_AES_128_GCM_SHA256
git 2.25.1
GIT_TERMINAL_PROMPT=0 git ls-remote private → "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
GIT_TERMINAL_PROMPT=0 git ls-remote public (git/git, /tmp/gitprobe-agt001) → 0f8e75ab... HEAD (성공)
git log (OCI HEAD) → 3f88354 / status → M .gitignore, M README.md, D backend.py, M docker-compose.yml
```


---

## 4. 실행 계획 (Claude 검토 반영, 2026-09-25)

위 추천 (a)를 채택하되, 검토에서 발견한 세 가지를 보완한다.

| 보완점 | 문제 | 조치 |
|---|---|---|
| 호스트 키 검증 | 첫 접속 때 `known_hosts`를 그대로 신뢰(TOFU)하면 그 한 번을 가로채 가짜 GitHub로 연결될 수 있다 | `https://api.github.com/meta`의 `ssh_keys`로 `known_hosts`를 만들고, 지문을 GitHub 문서의 공개 지문(ed25519 `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`)과 대조한 뒤 등록 |
| 키 선택 | 별칭(`github-agt001`)을 만들고 원격은 `git@github.com`으로 두면 별칭이 쓰이지 않는다 | 원격 URL을 `github-agt001:kyungsikjeung/agt001.git`로 설정 (위 절차 수정 완료) |
| 볼륨 보존 | compose 프로젝트 이름이 디렉터리 이름에서 나오므로, 새 경로에 clone하면 DB·인증서 볼륨이 새로 생긴다 | 디렉터리는 `~/agt001` 그대로 두고 제자리 전환. `docker-compose.yml`에 `name: agt001` 고정 (반영 완료) |

### 4.1 단계

| # | 작업 | 누가 | 되돌리기 |
|---|---|---|---|
| 1 | 서버에서 전용 키 생성(`~/.ssh/agt001-deploy`, ed25519, 권한 600), `~/.ssh/config` 별칭, 검증된 `known_hosts` 등록 | Claude (사용자 승인 후) | 키·설정 파일 삭제 |
| 2 | 공개키를 저장소 Deploy keys에 **읽기 전용**으로 등록 | 사용자(브라우저) 또는 Claude가 `gh repo deploy-key add`로 (승인 시) | GitHub에서 키 삭제 |
| 3 | 연결 확인: `ssh -T github-agt001`, `git ls-remote` | Claude | — |
| 4 | 제자리 전환: 배포 스냅샷을 먼저 뜬 뒤 `git remote set-url` → `git fetch` → `git reset --hard <배포할 SHA>`. `.env`·`generated/`는 `.gitignore` 대상이라 보존된다 | Claude | `scripts/rollback.sh` |
| 5 | `deploy.sh`를 git 방식으로 전환: 로컬 HEAD가 push돼 있는지 확인 → 서버에서 그 **정확한 SHA**로 `checkout --detach` → 빌드 판단(마커) → 재시작 → 헬스체크 → 실패 시 직전 SHA로 자동 복귀. 기존 rsync는 `--rsync` 옵션으로 남긴다(GitHub 장애 시 대비) | Claude | 이전 deploy.sh로 되돌림 |

`main`을 pull하지 않고 SHA를 지정하는 이유: 배포 시점에 확인한 커밋과 서버가 실행하는 커밋이 정확히 같아야 롤백 기준이 분명하다.

### 4.2 보안 메모

- Deploy Key는 이 저장소 하나에 대한 읽기 권한만 가진다. 서버가 뚫리면 코드 열람이 가능해지지만, 비밀값은 저장소에 없다(`.env`는 추적 제외).
- 교체 절차: GitHub에서 키 삭제 → 서버에서 새 키 생성·등록. 서버 재구축·담당자 변경 때 수행한다.
- 저장소를 public으로 바꾸는 안(c)은 채택하지 않는다.
