#!/usr/bin/env bash
# 오프사이트 백업 가져오기를 Mac launchd에 매일 실행으로 등록한다.
# 서버 백업이 매일 03:30 KST이므로 그 뒤인 매일 13:00 KST에 가져온다.
#
# 사용법: scripts/install_backup_pull.sh [--uninstall] [--help]
#   (인자 없음)  plist를 만들고 실행 예약한다
#   --uninstall  예약을 걷고 plist를 지운다
#   --help       이 도움말을 출력한다
#
# 실제 등록은 사용자가 직접 실행한다. 이 스크립트는 예약 내용만 만든다.
set -euo pipefail

usage() {
  echo "사용법: $(basename "$0") [--uninstall] [--help]"
  echo "  (인자 없음)  매일 13:00 실행 예약을 등록한다"
  echo "  --uninstall  예약을 걷고 plist를 지운다"
  echo "  --help       이 도움말을 출력한다"
}

MODE="install"
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "$arg" in
      --uninstall) MODE="uninstall" ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "알 수 없는 인자: $arg (scripts/install_backup_pull.sh --help 참고)" >&2
        exit 1
        ;;
    esac
  done
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_SCRIPT="$REPO_ROOT/scripts/pull_backups.sh"
# launchd 작업은 macOS 개인정보 보호(TCC) 때문에 ~/Documents 안 파일을 못 읽는다
# ("Operation not permitted"). 그래서 보호 폴더 밖에 사본을 두고 그것을 실행한다.
# pull_backups.sh를 고치면 이 스크립트를 다시 실행해 사본을 갱신한다.
INSTALL_DIR="$HOME/.agt001"
PULL_SCRIPT="$INSTALL_DIR/pull_backups.sh"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/com.agt001.backup-pull.plist"
LABEL="com.agt001.backup-pull"
LOG_DIR="$HOME/agt001-backups-offsite"

[ -n "${PLIST:-}" ] || { echo "PLIST 경로가 비어 있습니다" >&2; exit 1; }
[ -n "${PULL_SCRIPT:-}" ] || { echo "PULL_SCRIPT 경로가 비어 있습니다" >&2; exit 1; }

if [ "$MODE" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST" "$PULL_SCRIPT"
  echo "예약 해제 완료: $PLIST (가져온 덤프는 $LOG_DIR에 그대로 둔다)"
  exit 0
fi

if [ ! -f "$SOURCE_SCRIPT" ]; then
  echo "가져오기 스크립트가 없습니다: $SOURCE_SCRIPT" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR"
install -m 700 "$SOURCE_SCRIPT" "$PULL_SCRIPT"

mkdir -p "$PLIST_DIR"
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"

# 예약을 갈아끼울 때는 기존 예약을 먼저 걷는다 (중복 등록 방지)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PULL_SCRIPT</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>13</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/pull-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/pull-launchd.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" >/dev/null

echo "예약 등록 완료: 매일 13:00 KST ($PLIST)"
echo "가져오기 스크립트(사본): $PULL_SCRIPT  (원본 $SOURCE_SCRIPT 를 고치면 이 스크립트를 다시 실행)"
echo "예약 확인: launchctl list | grep $LABEL"
echo "지금 바로 1회 실행: /bin/bash $PULL_SCRIPT"
