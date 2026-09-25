#!/usr/bin/env bash
# 카카오·구글 로그인 키를 서버 .env에 넣는다 (DECISIONS.md D10).
#
# 입력값은 화면에 보이지 않고(read -s), 셸 기록·로그·이 저장소에 남지 않는다.
# 서버 .env의 같은 이름 줄은 바꾸고, 없으면 추가한다. 넣은 뒤 backend만 다시 띄운다.
#
# 사용법: scripts/set_oauth_secrets.sh [kakao|google|all]
#   각 값은 Enter만 누르면 건너뛴다(기존 값 유지).
# 터미널 붙여넣기가 잘 안 되면 파일로:
#   scripts/set_oauth_secrets.sh --template   # 빈 양식을 만들어 텍스트 편집기로 연다
#   (편집기에서 값을 붙여 넣고 저장)
#   scripts/set_oauth_secrets.sh --file       # 양식 파일을 서버로 보내고 내 컴퓨터에서 지운다
set -euo pipefail

KEY_FILE="${KEY_FILE:-$HOME/Desktop/agt001_oauth_keys.txt}"
ALLOWED="KAKAO_REST_API_KEY KAKAO_CLIENT_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_agt001}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@144.24.91.250}"
REMOTE_DIR="${REMOTE_DIR:-~/agt001}"
WHICH="${1:-all}"

if [ "$WHICH" = "--template" ]; then
  umask 077
  if [ ! -f "$KEY_FILE" ]; then
    {
      echo "# = 뒤에 값을 붙여 넣고 저장하세요. 모르는 줄은 비워 두면 건너뜁니다(기존 값 유지)."
      echo "# 카카오: 개발자 콘솔 > 앱 > 앱 키(REST API 키), 카카오 로그인 > 보안(Client Secret)"
      echo "# 구글: Google 인증 플랫폼 > 클라이언트 > agt001 web (클라이언트 ID, 새 보안 비밀번호)"
      for n in $ALLOWED; do echo "$n="; done
    } > "$KEY_FILE"
  fi
  chmod 600 "$KEY_FILE"
  echo "양식: $KEY_FILE (저장한 뒤 scripts/set_oauth_secrets.sh --file 실행)"
  open -e "$KEY_FILE" 2>/dev/null || true
  exit 0
fi

case "$WHICH" in
  -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
  --file) NAMES=() ;;
  kakao) NAMES=(KAKAO_REST_API_KEY KAKAO_CLIENT_SECRET) ;;
  google) NAMES=(GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET) ;;
  all) NAMES=(KAKAO_REST_API_KEY KAKAO_CLIENT_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET) ;;
  *) echo "알 수 없는 인자: $WHICH (kakao|google|all)" >&2; exit 1 ;;
esac

[ -f "$SSH_KEY" ] || { echo "SSH 키가 없습니다: $SSH_KEY" >&2; exit 1; }

PAYLOAD=""
if [ "$WHICH" = "--file" ]; then
  [ -f "$KEY_FILE" ] || { echo "양식 파일이 없습니다: $KEY_FILE (먼저 --template)" >&2; exit 1; }
  while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$line" in ''|\#*) continue ;; esac
    name="$(printf '%s' "${line%%=*}" | sed 's/[[:space:]]*$//')"; value="${line#*=}"
    value="$(printf '%s' "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//')"
    case " $ALLOWED " in *" $name "*) ;; *) echo "  모르는 이름 건너뜀: $name" >&2; continue ;; esac
    [ -n "$value" ] || { echo "  $name 비어 있어 건너뜀"; continue; }
    case "$value" in
      *[!A-Za-z0-9._~+/=-]*) echo "  $name 값에 허용되지 않는 문자가 있어 건너뜀(앞뒤 공백·따옴표 확인)" >&2; continue ;;
    esac
    PAYLOAD+="$name=$value"$'\n'
    echo "  $name 받음 (${#value}자)"
  done < "$KEY_FILE"
fi
for name in "${NAMES[@]+"${NAMES[@]}"}"; do
  printf '%s 붙여넣기 (화면에 보이지 않음, 건너뛰려면 Enter): ' "$name"
  IFS= read -rs value
  echo
  value="$(printf '%s' "$value" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -n "$value" ] || { echo "  $name 건너뜀"; continue; }
  case "$value" in
    *[!A-Za-z0-9._~+/=-]*) echo "  $name 값에 허용되지 않는 문자가 있어 건너뜀" >&2; continue ;;
  esac
  PAYLOAD+="$name=$value"$'\n'
  echo "  $name 받음 (${#value}자)"
done

[ -n "$PAYLOAD" ] || { echo "넣을 값이 없습니다."; exit 0; }

# 값은 ssh 표준 입력으로만 보낸다(명령줄 인자·원격 셸 기록에 남지 않게).
printf '%s' "$PAYLOAD" | ssh -i "$SSH_KEY" "$REMOTE_HOST" "
  set -euo pipefail
  cd $REMOTE_DIR
  umask 077
  touch .env
  while IFS= read -r line; do
    [ -n \"\$line\" ] || continue
    key=\"\${line%%=*}\"
    grep -v \"^\${key}=\" .env > .env.tmp || true
    printf '%s\n' \"\$line\" >> .env.tmp
    mv .env.tmp .env
  done
  chmod 600 .env
  sudo docker compose up -d backend >/dev/null 2>&1
  echo '서버 .env 갱신, backend 재기동 완료'
"
if [ "$WHICH" = "--file" ]; then
  rm -f "$KEY_FILE" && echo "내 컴퓨터의 양식 파일을 지웠습니다: $KEY_FILE"
fi
