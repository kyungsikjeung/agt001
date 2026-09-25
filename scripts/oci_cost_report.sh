#!/usr/bin/env bash
# OCI 비용 모니터링 리포트.
# 읽기 전용 조회만 수행한다 (list/get/request-summarized-usages).
# 사용법: ./scripts/oci_cost_report.sh [--days N] [--json] [--help]
# 종료코드: 0 정상(비용 0), 2 경고(과금 발생), 1 조회 실패.
set -euo pipefail

export SUPPRESS_LABEL_WARNING=True

DAYS=30
JSON_OUT=0

usage() {
  cat <<'EOF'
사용법: oci_cost_report.sh [--days N] [--json] [--help]

  --days N   조회 기간(일). 기본값 30. 이번 달 누계는 항상 함께 조회.
  --json     기계가 읽을 요약 JSON 출력 (텍스트 표 대신).
  --help     이 도움말 출력.

종료코드:
  0  정상 (비용 합계 0)
  2  경고: 과금 발생 (비용 합계 > 0)
  1  조회 실패

비고:
  - 테넌시 OCID는 ~/.oci/config에서 읽어 CLI 호출에만 사용하고 출력하지 않는다.
  - 출력에는 OCID·키·이메일을 포함하지 않는다 (리소스 이름과 수치만).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --days)
      DAYS="${2:-}"; shift 2
      ;;
    --days=*)
      DAYS="${1#--days=}"; shift
      ;;
    --json)
      JSON_OUT=1; shift
      ;;
    -h|--help)
      usage; exit 0
      ;;
    *)
      echo "알 수 없는 옵션: $1" >&2; usage >&2; exit 1
      ;;
  esac
done

case "$DAYS" in
  ''|*[!0-9]*|0)
    echo "오류: --days에는 1 이상의 정수를 지정하라." >&2; exit 1
    ;;
esac

if ! command -v oci >/dev/null 2>&1; then
  echo "오류: oci CLI를 찾을 수 없다." >&2; exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "오류: python3을 찾을 수 없다." >&2; exit 1
fi
if [ ! -f "$HOME/.oci/config" ]; then
  echo "오류: ~/.oci/config 파일을 찾을 수 없다." >&2; exit 1
fi

TENANCY="$(grep '^tenancy=' "$HOME/.oci/config" | cut -d= -f2 | tr -d ' ')"
REGION="$(grep '^region=' "$HOME/.oci/config" | cut -d= -f2 | tr -d ' ')"
if [ -z "${TENANCY:-}" ]; then
  echo "오류: ~/.oci/config에서 tenancy를 읽을 수 없다." >&2; exit 1
fi

# macOS(BSD date)와 GNU date 둘 다 지원.
date_days_ago() {
  local n="$1"
  date -u -v-"${n}"d "+%Y-%m-%dT00:00:00Z" 2>/dev/null \
    || date -u -d "$n days ago" "+%Y-%m-%dT00:00:00Z"
}
month_start() {
  date -u -v1d "+%Y-%m-01T00:00:00Z" 2>/dev/null \
    || date -u "+%Y-%m-01T00:00:00Z"
}
today_start() {
  date -u "+%Y-%m-%dT00:00:00Z"
}

START="$(date_days_ago "$DAYS")"
END="$(today_start)"
MSTART="$(month_start)"

TMPDIR_REQ="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_REQ"' EXIT

# 조회 실패 시 종료코드 1.
query_cost() {
  local s="$1" e="$2" out="$3"
  if ! oci usage-api usage-summary request-summarized-usages \
    --tenant-id "$TENANCY" \
    --time-usage-started "$s" \
    --time-usage-ended "$e" \
    --granularity DAILY \
    --query-type COST \
    --group-by '["service"]' >"$out" 2>"$TMPDIR_REQ/err.log"; then
    echo "오류: 비용 조회 실패 ($s ~ $e)." >&2
    cat "$TMPDIR_REQ/err.log" >&2 || true
    exit 1
  fi
}

query_cost "$START" "$END" "$TMPDIR_REQ/period.json"
query_cost "$MSTART" "$END" "$TMPDIR_REQ/mtd.json"

# ---- 리소스 인벤토리 (읽기 전용, 실패해도 리포트는 계속하되 상태를 표시) ----
INST_JSON="$TMPDIR_REQ/inst.json"
BOOT_JSON="$TMPDIR_REQ/boot.json"
VOL_JSON="$TMPDIR_REQ/vol.json"
PUB_JSON="$TMPDIR_REQ/pub.json"
BUCKET_JSON="$TMPDIR_REQ/bucket.json"

ResErr=""
oci compute instance list -c "$TENANCY" >"$INST_JSON" 2>/dev/null || { echo '{"data":[]}' >"$INST_JSON"; ResErr="${ResErr} compute"; }
oci bv boot-volume list -c "$TENANCY" >"$BOOT_JSON" 2>/dev/null || { echo '{"data":[]}' >"$BOOT_JSON"; ResErr="${ResErr} boot-volume"; }
# 빈 테넌시에서 volume list는 빈 출력으로 끝날 수 있어 정상(0개)으로 처리.
if ! oci bv volume list -c "$TENANCY" >"$VOL_JSON" 2>/dev/null; then
  echo '{"data":[]}' >"$VOL_JSON"; ResErr="${ResErr} volume"
fi
if [ ! -s "$VOL_JSON" ]; then
  echo '{"data":[]}' >"$VOL_JSON"
fi
# 예약 공인 IP (REGION scope). 비어 있으면 0개.
if ! oci network public-ip list -c "$TENANCY" --scope REGION >"$PUB_JSON" 2>/dev/null; then
  echo '{"data":[]}' >"$PUB_JSON"; ResErr="${ResErr} public-ip"
fi
if [ ! -s "$PUB_JSON" ]; then
  echo '{"data":[]}' >"$PUB_JSON"
fi
# 오브젝트 스토리지 버킷 수 (네임스페이스는 조회용, 출력하지 않음).
NS="$(oci os ns get 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('data',''))" 2>/dev/null || true)"
if [ -n "${NS:-}" ]; then
  if ! oci os bucket list --namespace "$NS" --compartment-id "$TENANCY" >"$BUCKET_JSON" 2>/dev/null; then
    echo '{"data":[]}' >"$BUCKET_JSON"; ResErr="${ResErr} bucket"
  fi
  if [ ! -s "$BUCKET_JSON" ]; then
    echo '{"data":[]}' >"$BUCKET_JSON"
  fi
else
  echo '{"data":[]}' >"$BUCKET_JSON"; ResErr="${ResErr} bucket-ns"
fi

# ---- 집계 + 출력 (python3; OCID·이메일은 절대 출력하지 않음) ----
export TMPDIR_REQ DAYS START END MSTART JSON_OUT ResErr REGION
python3 - <<'PY'
import json, os, sys
from collections import defaultdict

req = os.environ["TMPDIR_REQ"]
days = int(os.environ["DAYS"])
start = os.environ["START"]
end = os.environ["END"]
mstart = os.environ["MSTART"]
json_out = os.environ.get("JSON_OUT") == "1"
res_err = os.environ.get("ResErr", "").strip()
region = os.environ.get("REGION", "?")

def load(path):
    try:
        with open(path) as f:
            raw = f.read()
        if not raw.strip():
            return {"data": []}
        return json.loads(raw)
    except Exception:
        return None

period = load(os.path.join(req, "period.json"))
mtd = load(os.path.join(req, "mtd.json"))
if period is None or mtd is None:
    print("오류: 비용 응답을 해석할 수 없다.", file=sys.stderr)
    sys.exit(1)

def field(i, *names):
    for n in names:
        v = i.get(n)
        if v is not None:
            return v
    return None

def summarize(doc):
    items = (doc.get("data", {}) or {}).get("items", []) or []
    # OCI CLI는 하이픈 키(computed-amount 등)로 응답하므로 양쪽 표기를 모두 지원.
    total = sum((field(i, "computedAmount", "computed-amount") or 0) for i in items)
    cur = items[0].get("currency") if items else "N/A"
    by_svc = defaultdict(float)
    by_day = defaultdict(float)
    for i in items:
        svc = i.get("service") or "Unknown"
        amt = field(i, "computedAmount", "computed-amount") or 0
        day = (field(i, "timeUsageStarted", "time-usage-started") or "")[:10]
        by_svc[svc] += amt
        by_day[day] += amt
    return items, total, cur, dict(sorted(by_svc.items())), dict(sorted(by_day.items()))

p_items, p_total, p_cur, p_svc, p_day = summarize(period)
m_items, m_total, m_cur, m_svc, m_day = summarize(mtd)
currency = p_cur if p_cur != "N/A" else m_cur

# --- 인벤토리 (이름·수치만) ---
inst = load(os.path.join(req, "inst.json")) or {"data": []}
boot = load(os.path.join(req, "boot.json")) or {"data": []}
vol = load(os.path.join(req, "vol.json")) or {"data": []}
pub = load(os.path.join(req, "pub.json")) or {"data": []}
bkt = load(os.path.join(req, "bucket.json")) or {"data": []}

instances = inst.get("data", []) or []
boot_vols = boot.get("data", []) or []
blk_vols = vol.get("data", []) or []
pub_ips = pub.get("data", []) or []
buckets = bkt.get("data", []) or []

total_ocpu = 0.0
total_mem = 0.0
inst_rows = []
for i in instances:
    name = i.get("display-name") or "(이름 없음)"
    shape = i.get("shape") or "?"
    state = i.get("lifecycle-state") or "?"
    cfg = i.get("shape-config") or {}
    try:
        ocpu = float(cfg.get("ocpus") or 0)
    except Exception:
        ocpu = 0.0
    try:
        mem = float(cfg.get("memory-in-gbs") or 0)
    except Exception:
        mem = 0.0
    total_ocpu += ocpu
    total_mem += mem
    inst_rows.append({"name": name, "shape": shape, "state": state,
                      "ocpu": ocpu, "mem": mem})

def vol_size(items):
    tot = 0
    for v in items:
        try:
            tot += int(v.get("size-in-gbs") or 0)
        except Exception:
            pass
    return tot

boot_gb = vol_size(boot_vols)
blk_gb = vol_size(blk_vols)
storage_gb = boot_gb + blk_gb

# 예약(RESERVED) 공인 IP만 집계 (임시/EPHEMERAL는 인스턴스 VNIC에 붙은 1개가 정상).
reserved_ips = [x for x in pub_ips if (x.get("lifetime") or "").upper() == "RESERVED"]
reserved_count = len(reserved_ips)

# VNIC 경유 임시 공인 IP 개수 (읽기 전용 보조 정보는 생략하고 예약 IP만 표에 둠).
bucket_count = len(buckets)

# 무료 한도 (공식 문서 기준. 불확실 항목은 확인 필요 표기).
LIMIT_A1_OCPU = 4.0
LIMIT_A1_MEM = 24.0
LIMIT_BLOCK_GB = 200

result = {
    "period_days": days,
    "period_start": start,
    "period_end": end,
    "period_total": round(p_total, 4),
    "mtd_start": mstart,
    "mtd_total": round(m_total, 4),
    "currency": currency,
    "by_service": {k: round(v, 4) for k, v in p_svc.items()},
    "by_day": {k: round(v, 4) for k, v in p_day.items()},
    "mtd_by_service": {k: round(v, 4) for k, v in m_svc.items()},
    "inventory": {
        "instances": inst_rows,
        "total_ocpu": total_ocpu,
        "total_mem_gb": total_mem,
        "limit_a1_ocpu": LIMIT_A1_OCPU,
        "limit_a1_mem_gb": LIMIT_A1_MEM,
        "boot_gb": boot_gb,
        "block_gb": blk_gb,
        "storage_total_gb": storage_gb,
        "limit_block_gb": LIMIT_BLOCK_GB,
        "reserved_public_ips": reserved_count,
        "buckets": bucket_count,
    },
    "resource_query_warnings": res_err,
    "region": region,
}

warn = p_total > 0 or m_total > 0

if json_out:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2 if warn else 0)

# 텍스트 표 출력
print(f"OCI 비용 리포트 (최근 {days}일: {start[:10]} ~ {end[:10]}, 리전: {region})")
print(f"통화 단위: {currency}")
print()
print(f"최근 {days}일 합계: {p_total:.4f} {currency}")
print(f"이번 달 누계 ({mstart[:10]} ~ {end[:10]}): {m_total:.4f} {currency}")
print()
print("[서비스별 합계 (조회 기간)]")
if p_svc:
    for k, v in p_svc.items():
        print(f"  - {k}: {v:.4f} {currency}")
else:
    print("  (내역 없음)")
print()
print("[일별 합계 (0이 아닌 날만)]")
nz = [(k, v) for k, v in p_day.items() if v != 0]
if nz:
    for k, v in nz:
        print(f"  - {k}: {v:.4f} {currency}")
else:
    print("  (전일 0원)")
print()
print("[무료 한도 대비 현재 사용량]")
print(f"  - 인스턴스 수: {len(inst_rows)}")
for r in inst_rows:
    print(f"    · {r['name']} [{r['shape']}/{r['state']}] OCPU {r['ocpu']}, 메모리 {r['mem']}GB")
print(f"  - OCPU 합계: {total_ocpu} / {LIMIT_A1_OCPU} (Ampere A1 한도 기준)")
print(f"  - 메모리 합계: {total_mem}GB / {LIMIT_A1_MEM}GB (Ampere A1 한도 기준)")
print(f"  - 블록 스토리지 합계: {storage_gb}GB (부트 {boot_gb}GB + 블록 {blk_gb}GB) / {LIMIT_BLOCK_GB}GB")
print(f"  - 예약 공인 IP: {reserved_count}개 (임시 IP는 인스턴스에 1개 부착이 정상, 예약 IP는 과금 주의)")
print(f"  - 오브젝트 스토리지 버킷: {bucket_count}개")
if res_err:
    print(f"  ※ 일부 리소스 조회 경고:{res_err} (수치가 비어 있을 수 있음)")
print()
if warn:
    print("경고: 과금 발생")
    sys.exit(2)
else:
    print("정상: 과금 없음 (합계 0원)")
    sys.exit(0)
PY
