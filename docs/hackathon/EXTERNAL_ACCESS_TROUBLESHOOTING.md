# 외부 접속 불가 문제 조사 (EXTERNAL_ACCESS_TROUBLESHOOTING)

- 조사일: 2026-09-23
- 현상: 제작자 본인은 `http://144.24.91.250:8643` 접속 가능(로컬 curl 수차례 검증)이나,
  외부 사용자(경영진 등)는 같은 링크로 접속 불가 보고.
- 방식: 웹 검색 + 서버 읽기 전용 점검. **코드·서버 설정 변경 없음.**

---

## 가장 유력한 원인 Top 3

| 순위 | 원인 | 근거 |
|---|---|---|
| **1** | **접속자 측 네트워크에서 비표준 포트(8643) 아웃바운드 차단** | 회사·기관·공공 와이파이는 아웃바운드를 80/443만 허용하는 구성이 흔함. Cisco 커뮤니티 실증("We only allow 80/443 outbound but we receive many requests ... to access client sites that include a random port") 및 FortiSASE 공식 문서("Block applications detected on non-default ports" 기능 — 비표준 포트 HTTP를 정책으로 차단)가 이를 뒷받침. 경영진이 사내망에서 접속했을 가능성이 높음. 서버 측은 정상이므로(아래 점검 결과) 클라이언트 측 차단이 가장 정합적. |
| **2** | **평문 HTTP에 대한 최신 브라우저 경고/기업 정책 차단** | Chrome이 "Always Use Secure Connections"(HTTPS-First)를 2026-04 Chrome 147에서 Enhanced Safe Browsing 사용자(10억+)에게, **2026-10 Chrome 154에서 전체 기본값**으로 전환 (BleepingComputer, 2025-10-30). 조사 시점(2026-09-23)이 전환 직전이라, 상대방 브라우저는 "안전하지 않음" 확인 페이지 또는 기업 정책(`HttpAllowlist` 미등록 시 차단)을 마주했을 수 있음. 경고 페이지를 보고 "접속 안 됨"으로 보고했을 가능성. |
| **3 (추정)** | **접속자 측 DNS에서 `sslip.io` 해석 실패/차단** | 와일드카드 DNS는 피싱·스캠 악용 사례가 실재함 — sslip.io 운영자가 abuse 신고 대응용 blocklist를 실제로 운영 중이며("Blocked Site!" 페이지 실재, `metrics.status`에 `Blocked` 카운터 존재), 보안 업계는 와일드카드 DNS를 "untrusted infrastructure indicator"로 취급. 기업·공공기관 DNS 필터링이 이런 도메인을 분류·차단할 수 있음. 다만 **sslip.io 자체가 특정 기업망에서 차단된다는 직접 사례는 찾지 못했으므로 추정.** IP 직접 접속(`http://144.24.91.250:8643`)과 도메인 접속을 분리 테스트하면 판별 가능 (아래 "지금 할 수 있는 것" 참고). |

> 핵심 판단: 서버 측(OCI Security List, OS 방화벽, Docker, 라우팅)은 전부 정상으로 실측됨.
> 즉 **서버가 막고 있는 게 아니라, 보는 사람 쪽 환경(사내망 방화벽·브라우저 정책·DNS)이 막고 있을 가능성**이 가장 크다.

---

## 1. OCI 네트워크 레벨 (웹 검색 + 실측)

### 1-1. 웹 검색: 외부 접속이 막히는 흔한 원인

- OCI 공식 문서(Security Lists, OCI CLI `security-list` 레퍼런스)는 명시한다:
  > "If there are issues with some type of access to an instance, make sure **both** the security lists associated with the instance's subnet **and the instance's firewall rules** are set correctly."
  즉 Security List를 열어도 인스턴스 안의 OS 방화벽(iptables/firewalld/ufw)이 별도로 막을 수 있다는 것이 공식 입장.
- 커뮤니티 정설(ORACLE-BASE "Amend Firewall Rules", Reddit r/oraclecloud 다수 글):
  VCN Security List 인그레스 추가 **+** VM 로컬 방화벽 개방(예: `firewall-cmd --add-port=8080/tcp`) **둘 다** 해야 하며,
  초보자가 가장 흔히 빠지는 함정이 "Security List만 열고 로컬 방화벽을 잊은 경우".
- Ubuntu 이미지 특이사항: Oracle 공식 블로그에 따르면 Ubuntu 이미지의 UFW는 기본 비활성화 권고
  ("use of UFW is discouraged ... UFW is therefore disabled by default")이나,
  Oracle 제공 이미지에는 기본 iptables 규칙(SSH만 허용 + 나머지 REJECT)이 들어있어
  Docker 미사용 서비스는 여기서 막힐 수 있다.

### 1-2. 실측 (읽기 전용, 2026-09-23)

| 점검 | 명령 | 결과 |
|---|---|---|
| 서비스 생존 (IP) | `curl -sI http://144.24.91.250:8643/health` | **200 OK** (`Werkzeug/3.1.8 Python/3.11.16`) |
| 서비스 생존 (도메인) | `curl -sI http://144.24.91.250.sslip.io:8643/health` | **200 OK** — IP와 동일. DNS 정상 해석됨 |
| DNS 해석 | `nslookup` / `dig` | `144.24.91.250.sslip.io → 144.24.91.250` (조사자 네트워크 기준 정상) |
| ufw | `sudo ufw status verbose` | **inactive** — OS 방화벽 개입 없음 |
| iptables | `sudo iptables -L -n -v` | INPUT: RELATED/ESTABLISHED·icmp·lo·SSH(22) 허용 후 REJECT. **단, Docker 발행 포트는 INPUT이 아니라 PREROUTING DNAT → FORWARD 체인**을 타므로 영향 없음. DOCKER 체인에 `tcp dpt:8643 → 172.18.0.2` ACCEPT 확인. `ss -tlnp`에서 `0.0.0.0:8643` docker-proxy LISTEN, `docker ps`에서 `0.0.0.0:8643->8643/tcp` 매핑 확인 |
| Security List (실제, oci CLI) | `oci network security-list get` | 인스턴스가 속한 서브넷(`agt001-public-subnet`)의 Security List(`...5x6q`) 인그레스: **TCP 22 + ICMP + TCP 8643 (0.0.0.0/0)** — 열려 있음 |
| NSG | `oci network vnic get` | `nsg-ids: []` — NSG 미사용, Security List가 유일한 VCN 레벨 필터 |
| 라우트 테이블 | `oci network route-table list` | `0.0.0.0/0 → IGW` 존재 |
| 인스턴스 체인 정합성 | instance→vnic→subnet→vcn→seclist 추적 | `agt001-hermes-backend`(RUNNING) → public IP `144.24.91.250` → VCN(`...rc7q`) → 8643 오픈된 Security List. **체인 전부 정합** |

### 1-3. 문서 대조 (`docs/hackathon/ENVIRONMENT.md`)

- §3-3(네트워크 표): "기본 보안리스트에 SSH(22) + ICMP 인그레스만 허용" — 8643 추가 **전** 상태의 기록으로 보임.
- §3-5(챗봇 배포): "SSH(22)+ICMP에 더해 **TCP 8643 인바운드 오픈**" + "전부 외부에서 접속 확인" — 8643 추가 **후** 상태.
- 이번 oci CLI 실측으로 §3-5 기록이 사실임을 확인. §3-3은 구(구) 기록이므로 혼동 주의.
- 부기: 동일 표시명(`agt001-vcn`)의 VCN이 2개, Security List도 2개 존재함.
  8643이 없는 쪽(`...kx5na`)은 인스턴스와 연결되지 않은 VCN(추정: 과거 생성분/중복)으로,
  현 문제와 무관하나 나중에 정리 대상.

**결론: OCI 네트워크 레벨은 원인에서 제외. 서버는 외부 인터넷에 정상 노출되어 있다.**

---

## 2. 비표준 포트(8643) 문제 (웹 검색)

- 기업 이그레스 방화벽이 80/443 아웃바운드만 허용하는 구성은 실무에서 흔하다.
  Cisco 커뮤니티(2019, 실무자 글): "We have ASA's in every office as the egress firewall ... **We only allow 80/443 outbound**" —
  `:8080` 같은 랜덤 포트 사이트 접속 요청이 들어올 때마다 방화벽 규칙을 수동 추가해야 했다는 증언.
- Fortinet FortiSASE 공식 문서에는 "Block applications detected on non-default ports" 옵션이 있으며,
  활성화 시 표준 포트(80/443)가 아닌 포트에서 감지된 HTTP 트래픽을 차단한다.
  즉 **비표준 포트 HTTP 차단은 엔터프라이즈 보안 장비의 기본 제공 기능**이다.
- CISA/MITRE ATT&CK(T1571)도 비표준 포트를 C2·유출 벡터로 규정하므로,
  보안 정책이 엄격한 조직일수록 비표준 아웃바운드를 원천 차단하는 경향이 있다 (추정: 일반론).
- 모바일 통신사·가정용 인터넷에서는 8643 아웃바운드 차단 사례를 확인하지 못했으므로,
  **접속자가 회사·학교·공공 와이파이에 있었는지가 관건**이다.

---

## 3. HTTP(비HTTPS) 문제 (웹 검색)

- Chrome "Ask-before-HTTP" / "Always Use Secure Connections":
  - 공지(BleepingComputer, 2025-10-30): Chrome은 공개 HTTP 사이트 첫 방문 시 사용자 확인을 요구하는 방향으로 전환.
  - 일정: **Chrome 147(2026-04)** — Enhanced Safe Browsing 사용자 10억+ 대상 선적용,
    **Chrome 154(2026-10)** — 전체 기본값 전환. 조사 시점(2026-09-23)은 전환 직전.
  - 증상: `http://` 링크 클릭 시 경고/확인 페이지가 먼저 뜨고, 사용자가 "계속"을 눌러야 진입.
    이를 "사이트가 안 열린다"로 오인·보고할 수 있다.
- 기업 관리 Chrome(`HttpAllowlist` 정책 미등록) 또는 평문 HTTP를 차단하는 회사 프록시 환경에서는
  HTTP 사이트 자체가 열리지 않을 수 있다 (추정: 상대방이 사내 PC라는 가정이 성립할 때).
- 참고: HSTS·Mixed Content는 **우리 사이트가 HTTPS일 때** HTTP 하위 리소스를 막는 메커니즘이라
  현 케이스(사이트 자체가 순수 HTTP)에는 직접 해당하지 않음. 사용자가 `https://144.24...:8643`으로
  잘못 입력했다면 TLS 미지원이므로 연결 실패로 보일 수 있다 (추정).

---

## 4. sslip.io 관련 (웹 검색)

- sslip.io/nip.io는 10년 이상 운영된 공개 와일드카드 DNS(GCP·AWS·Azure·IBM 공식 문서에서도 참조)이며,
  조사자 네트워크에서는 정상 해석·정상 접속을 확인했다. 서비스 자체 장애는 아니다.
- 리스크 측면 (추정 근거):
  - 운영자(cunnie/sslip.io)는 abuse 신고 대응용 blocklist(`etc/blocklist.txt`)를 실제 운영 중이고,
    피싱·스캠으로 신고된 호스트는 "Blocked Site!" 페이지로 연결된다. 즉 **이 도메인 대역은 악용 사례가 실재**한다.
  - 보안 업계 레퍼런스는 와일드카드 DNS를 SSRF·URL 필터 우회 수단이자
    "defenders should treat wildcard-DNS domains as untrusted infrastructure indicators"로 기술.
  - 기업·공공기관의 DNS 필터링/프록시가 이런 분류의 도메인을 차단하거나 미해석할 여지가 있다.
- **직접 증거 한계**: "우리 회사망에서 sslip.io가 막혔다"는 식의 구체 사례는 찾지 못했다. 따라서 Top 3 중 유일하게 **추정** 등급.
  판별법은 간단하다: 접속자에게 **IP 직접 주소와 도메인 주소를 각각** 열어보게 하면 된다
  (IP는 되고 도메인만 안 되면 DNS 문제로 확정).

---

## 5. 카카오톡 인앱 브라우저 (웹 검색)

- **특정 포트 차단, HTTP 차단 같은 인앱브라우저 고유 제약을 확인하지 못했다.** 포트·프로토콜 레벨의 공식 제한 문서는 없음.
- 대신 확인된 인앱브라우저 특유의 문제 유형 (접속 불가와는 결이 다름):
  - 흰 화면/렌더링 이슈 ("React + tailwind 앱이 Android + 카톡 인앱에서만 흰화면", "홈페이지가 뜨지 않아요" 등 데브톡 민원 다수).
  - Android 인앱 웹뷰는 종료 시 캐시를 삭제함(카카오 공식 답변) — 느리게 보일 수는 있어도 접속 불가 원인은 아님.
  - 팝업 차단: 기존에 겪은 `Cannot read properties of null (reading 'focus')` 건과 동형
    (자동화 클릭이 신뢰된 제스처가 아니라 팝업 차단). 사용자 직접 클릭 시에는 발생하지 않음.
  - 우회 수단 존재: 인앱 우측 상단 `… > 다른 브라우저로 열기`, 또는 OS별 외부 브라우저 강제 열기 스크립트(커뮤니티 공지 패턴).
- 이전 사례(카톡 인앱이 링크를 `data:` URL로 렌더링 → localStorage/crypto 문제)는
  **접속 이후의 앱 동작 문제**이지, TCP 연결 자체가 안 되는 문제와는 무관하다.
- 정리: 카톡 인앱브라우저는 "연결 불가"의 유력 용의자가 아니라 **"열리긴 열리는데 깨져 보인다" 계열의 2차 리스크**로 분류.
  단, 카톡으로 링크를 받은 사람이 사내망+인앱브라우저 조합이었다면 1·2번 원인과 결합될 수 있다 (추정).

---

## 확인/해결을 위해 지금 할 수 있는 것 (제안만, 미실행)

1. **접속자에게 증상 분리 질문** (가장 cheap하고 결정적):
   - `http://144.24.91.250:8643` (IP 직접) vs `http://144.24.91.250.sslip.io:8643` (도메인) 중 어느 것이 안 되는가?
     → IP만 되면 DNS(3순위) 확정, 둘 다 안 되면 포트/HTTP(1·2순위)로 좁혀짐.
   - 어느 네트워크인가 (사내 와이파이/유선 vs 휴대폰 LTE/5G vs 집 와이파이)?
     → 사내망에서만 안 되면 1순위 확정적.
   - 브라우저에 뜬 화면이 무엇인가 (연결 시간초과 vs "안전하지 않음" 경고 vs 흰 화면)?
     → 시간초과=포트 차단, 경고=HTTP 정책, 흰 화면=인앱 렌더링 문제.
   - 카톡 인앱 vs 크롬/사파리 직접 입력 결과가 다른가?
2. **근본 해결책 (제안)**: 서비스를 **표준 포트(80/443) + HTTPS**로 이전.
   - 1순위(포트 차단)와 2순위(HTTP 경고)를 동시에 제거하는 유일한 근본책.
   - sslip.io 도메인으로 Let's Encrypt 인증서 발급(HTTP-01 챌린지)이 가능하다는 것이 운영자 측 주장이나,
     보다 안정적으로는 정식 도메인 확보 후 443/HTTPS 전환을 권장 (추정: sslip.io+80 조합도 기업망에서 막힐 여지는 남음).
3. **임시 완화책 (제안)**: 당장 포트를 못 옮기면 —
   - 공유 링크를 IP 직접 주소로도 함께 제공 (DNS 변수 제거).
   - 카톡 공유 시 "… > 다른 브라우저로 열기" 안내 문구를 링크와 함께 전달.
   - 접속자에게 모바일 데이터망에서 재시도 요청 (사내망 방화벽 우회 확인용).
4. **문서 정합성 (제안)**: `ENVIRONMENT.md` §3-3의 "SSH+ICMP만 허용" 구(구) 기록에
   "(8643 추가 전)" 같은 시점 주석을 달아 혼동을 방지. 미연결 VCN(`...kx5na`) 1개는 나중에 정리 검토.
5. **하지 않은 것**: ufw/iptables/Security List 변경 없음, `.env` 미열람, git 커밋·푸시 없음.
