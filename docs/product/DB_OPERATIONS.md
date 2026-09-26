# DB 운영 절차 (PostgreSQL 16, WP 0-2c)

> 대상: OCI 운영 서버(`~/agt001`). compose `db` 서비스 + 이름 있는 볼륨 `pg_data`.

## 1. 비밀번호 설정

비밀번호는 서버의 `.env`에만 넣는다. compose 파일·git에는 절대 넣지 않는다.

```bash
# 서버에서 1회: .env에 추가 (값은 openssl rand -hex 24 등으로 생성)
POSTGRES_PASSWORD=<생성한_비밀번호>
```

`POSTGRES_PASSWORD`가 비어 있으면 compose가 기동 시
`POSTGRES_PASSWORD를 .env에 설정하세요` 오류로 실패한다.
앱(`backend`)은 `DATABASE_URL=postgresql+psycopg://agt001:<비밀번호>@db:5432/agt001`을
compose가 주입하므로 별도 설정이 필요 없다.

## 2. 최초 기동

```bash
cd ~/agt001
sudo docker compose up -d --build   # db가 healthy가 된 뒤 backend가 기동된다
sudo docker compose exec db pg_isready -U agt001 -d agt001
sudo docker compose logs backend | tail -20
```

볼륨 `pg_data`에 데이터가 저장되므로 컨테이너를 내렸다 올려도 유지된다.
초기 스키마 적용·기존 JSON 이전 절차는 0-2a/0-2b 산출물(Alembic, `migrate_json_to_pg.py`)을 따른다.

## 3. 백업 cron 등록

매일 03:30 KST = 18:30 UTC에 실행한다.

```bash
crontab -e
# 다음 줄 추가:
30 18 * * * ~/agt001/scripts/backup_db.sh >> ~/agt001-backups/backup.log 2>&1
```

백업 파일: `~/agt001-backups/agt001-<UTC타임스탬프>.dump` (pg_dump custom 형식).
최근 14개만 보관되고 나머지는 스크립트가 자동 삭제한다.

수동 실행: `~/agt001/scripts/backup_db.sh` (인자로 compose 디렉토리 지정 가능, 기본 `~/agt001`).

## 4. 복원 절차

```bash
cd ~/agt001
# 1. 덤프를 db 컨테이너 안으로 넣는다
sudo docker compose cp ./agt001-<타임스탬프>.dump db:/tmp/restore.dump
# 2. 기존 객체를 지우고 복원한다
sudo docker compose exec -T db pg_restore -U agt001 -d agt001 --clean --if-exists /tmp/restore.dump
# 3. backend 재기동 후 헬스체크
sudo docker compose restart backend
curl -sf http://localhost:8643/health
```

## 5. 용량 확인

```bash
# DB 크기
sudo docker compose exec -T db psql -U agt001 -d agt001 -c "SELECT pg_size_pretty(pg_database_size('agt001'));"
# 테이블별 크기
sudo docker compose exec -T db psql -U agt001 -d agt001 -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC;"
# 볼륨·디스크 사용량
docker system df -v | grep -A3 pg_data
df -h ~/agt001-backups
```

## 6. 서버 밖 보관 (Mac 오프사이트, USER_DB_PLAN.md U-6)

서버 디스크(`~/agt001-backups/`, §3)만 두면 디스크 손상·인스턴스 장애 때
백업도 함께 잃는다. Mac에 1부를 더 둔다 (수동 E-2를 자동화한 형태).

```bash
# 1회 가져오기 (Mac에서, 서버 원본은 지우지 않는다)
scripts/pull_backups.sh
# 미리보기
scripts/pull_backups.sh --dry-run

# 매일 13:00 KST 자동 실행 등록 (서버 백업 03:30 KST 이후)
# 실제 등록은 사용자가 직접 실행한다
scripts/install_backup_pull.sh
# 예약 해제
scripts/install_backup_pull.sh --uninstall
```

| 항목 | 값 |
|---|---|
| 가져오기 | `rsync`로 서버 `~/agt001-backups/agt001-*.dump`만 가져온다 (`--delete` 없음, 서버 원본 유지) |
| 서버 접속 | `SSH_KEY`(기본 `~/.ssh/oci_agt001`)·`REMOTE_HOST`(기본 `ubuntu@144.24.91.250`) 환경변수 (`deploy.sh`와 같은 방식) |
| 로컬 보관 | `~/agt001-backups-offsite/`에 최근 30개만 (넘치는 것은 오래된 것부터 삭제) |
| 무결성 | 파일마다 `pg_restore --list`로 읽힘 확인 (`pg_restore`가 없으면 크기로만 확인) |
| 권한 | 폴더 `700`, 덤프 파일 `600` (사용자 데이터가 들어 있다) |
| 기록 | 1줄씩 `~/agt001-backups-offsite/pull.log`에 남긴다 (시각·정상 수·깨짐 수·보관 수) |
| 예약 | `~/Library/LaunchAgents/com.agt001.backup-pull.plist`, 매일 13:00 KST, 출력은 `pull-launchd.log` |

로컬 덤프에서 복원할 때는 파일을 서버로 올린 뒤 §4와 같은 순서로 복원한다.
복구 연습(분기 1회, 스테이징에만 복원)은 USER_DB_PLAN.md §A-3 절차를 따른다.
