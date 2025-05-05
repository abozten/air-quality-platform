#!/usr/bin/env bash
#
# Script to scan Europe at ~50 km resolution, send
# all AQ parameters, with anomalies.

set -euo pipefail

# --- Configuration ---
API_ENDPOINT="${API_BASE_URL:-http://localhost:8000/api/v1}/air_quality/ingest"
PARAMETERS=("pm25" "pm10" "no2" "so2" "o3")

# Default values
DEFAULT_RATE=50            # requests per second
DEFAULT_ANOMALY_CHANCE=0.001  # percent

# 50 km ≈ 0.449° (1° lat ≈ 111.32 km)
DELTA_DEG=1.449

# Europe bounding box
LAT_MIN=34
LAT_MAX=72
LON_MIN=-25
LON_MAX=45

# --- Logging ---
log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }

# --- Random float generator ---
random_float() {
  awk -v min="$1" -v max="$2" 'BEGIN{srand(); printf("%.6f\n", min+rand()*(max-min))}'
}

# --- Anomaly decision (0=anomaly, 1=normal) ---
is_anomaly() {
  awk -v c="$1" 'BEGIN{srand(); exit (rand()*100 < c ? 0 : 1)}'
}

# --- Parse args ---
RATE=${DEFAULT_RATE}
ANOMALY_CHANCE=${DEFAULT_ANOMALY_CHANCE}
for arg in "$@"; do
  case $arg in
    --rate=*)           RATE="${arg#*=}"           ;;
    --anomaly-chance=*) ANOMALY_CHANCE="${arg#*=}" ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--rate=<req/sec>] [--anomaly-chance=<percent>]
EOF
      exit 0
      ;;
    *) log "ERROR: Unknown arg: $arg"; exit 1;;
  esac
done

# --- Compute sleep ---
if awk "BEGIN{exit !($RATE>0)}"; then
  SLEEP=$(awk -v r="$RATE" 'BEGIN{printf("%.6f", 1/r)}')
else
  log "ERROR: --rate must be >0"; exit 1
fi

log "Scanning Europe: lat ${LAT_MIN}→${LAT_MAX}, lon ${LON_MIN}→${LON_MAX}"
log "Grid step: ${DELTA_DEG}° (~50 km), Rate: $RATE req/s, Anomaly: ${ANOMALY_CHANCE}%"
log "API endpoint: $API_ENDPOINT"

# --- Main Loop ---
TOTAL=0
for lat in $(seq "$LAT_MIN" "$DELTA_DEG" "$LAT_MAX"); do
  for lon in $(seq "$LON_MIN" "$DELTA_DEG" "$LON_MAX"); do
    # start JSON
    JSON="{\"latitude\":$(printf '%.6f' "$lat"),\"longitude\":$(printf '%.6f' "$lon")}"

    # append each parameter
    for p in "${PARAMETERS[@]}"; do
      if is_anomaly "$ANOMALY_CHANCE"; then
        case $p in
          pm25) v=$(random_float 250.1 500.0);;
          pm10) v=$(random_float 420.1 800.0);;
          no2)  v=$(random_float 200.1 400.0);;
          so2)  v=$(random_float 50.1 150.0);;
          o3)   v=$(random_float 240.1 400.0);;
        esac
      else
        case $p in
          pm25) v=$(random_float 5.0 80.0);;
          pm10) v=$(random_float 10.0 150.0);;
          no2)  v=$(random_float 10.0 100.0);;
          so2)  v=$(random_float 1.0 20.0);;
          o3)   v=$(random_float 20.0 180.0);;
        esac
      fi
      JSON=$(jq -n --argjson base "$(echo "$JSON" | jq '.')" --arg p "$p" --argjson val "$v" '$base + {($p): $val}')
    done

    # send in background
    curl -s -o /dev/null -X POST \
         -H "Content-Type: application/json" \
         -d "$JSON" \
         "$API_ENDPOINT" &

    ((TOTAL++))
    sleep "$SLEEP"
  done
done

wait
log "Done. Sent $TOTAL requests (~$(printf '%.1f' "$((TOTAL/RATE/3600))") hours)."
