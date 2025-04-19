#!/bin/bash

# Script to automatically send random (and potentially anomalous) air quality data
# to the API endpoint to simulate load and test scenarios.

# --- Configuration ---
API_ENDPOINT="${API_BASE_URL:-http://localhost:8000/api/v1}/air_quality/ingest"
PARAMETERS=("pm25" "pm10" "no2" "so2" "o3")
NUM_PARAMS=${#PARAMETERS[@]}

# Default values
DEFAULT_DURATION=30      # seconds
DEFAULT_RATE=5           # requests per second
DEFAULT_ANOMALY_CHANCE=10 # percentage (0-100)

# --- Helper Functions ---
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $@"
}

# Function to generate random float using awk (more portable than other methods)
# Usage: random_float MIN MAX
random_float() {
    local min=$1
    local max=$2
    # Seed awk's rand() using nanoseconds for better randomness per call
    awk -v min="$min" -v max="$max" 'BEGIN{srand(); print min+rand()*(max-min)}'
}

# --- Parse Command Line Arguments ---
DURATION=$DEFAULT_DURATION
RATE=$DEFAULT_RATE
ANOMALY_CHANCE=$DEFAULT_ANOMALY_CHANCE

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --duration=*) DURATION="${1#*=}";;
        --rate=*) RATE="${1#*=}";;
        --anomaly-chance=*) ANOMALY_CHANCE="${1#*=}";;
        -h|--help)
            echo "Usage: $0 [--duration=<seconds>] [--rate=<requests_per_second>] [--anomaly-chance=<percentage>]"
            echo "Defaults: duration=${DEFAULT_DURATION}s, rate=${DEFAULT_RATE}/s, anomaly_chance=${DEFAULT_ANOMALY_CHANCE}%"
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Input validation
if ! [[ "$DURATION" =~ ^[0-9]+$ ]] || [ "$DURATION" -le 0 ]; then
    log "Error: Invalid duration. Must be a positive integer."
    exit 1
fi
if ! [[ "$RATE" =~ ^[0-9]+(\.[0-9]+)?$ ]] || (( $(echo "$RATE <= 0" | bc -l) )); then
    log "Error: Invalid rate. Must be a positive number."
    exit 1
fi
if ! [[ "$ANOMALY_CHANCE" =~ ^[0-9]+$ ]] || [ "$ANOMALY_CHANCE" -lt 0 ] || [ "$ANOMALY_CHANCE" -gt 100 ]; then
    log "Error: Invalid anomaly chance. Must be an integer between 0 and 100."
    exit 1
fi

# Calculate sleep time between requests
# Use bc for floating point division
if (( $(echo "$RATE > 0" | bc -l) )); then
    SLEEP_TIME=$(echo "scale=4; 1 / $RATE" | bc)
else
    SLEEP_TIME=1 # Avoid division by zero, default to 1s if rate is somehow 0
fi


log "Starting auto-test..."
log "Duration: ${DURATION} seconds"
log "Rate: ${RATE} requests/second (sleep ${SLEEP_TIME}s between requests)"
log "Anomaly Chance: ${ANOMALY_CHANCE}%"
log "Target API: ${API_ENDPOINT}"

# --- Main Loop ---
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION))
REQUEST_COUNT=0

while [ $(date +%s) -lt $END_TIME ]; do
    REQUEST_COUNT=$((REQUEST_COUNT + 1))
    # Generate random location
    LAT=$(random_float -90 90)
    LON=$(random_float -180 180)

    # Select random parameter
    PARAM_INDEX=$(( RANDOM % NUM_PARAMS ))
    PARAM_NAME=${PARAMETERS[$PARAM_INDEX]}

    # Decide if this request is an anomaly
    IS_ANOMALY=false
    RAND_CHANCE=$(( RANDOM % 100 )) # 0-99
    if [ "$RAND_CHANCE" -lt "$ANOMALY_CHANCE" ]; then
        IS_ANOMALY=true
    fi

    # Generate value based on parameter and anomaly status
    case "$PARAM_NAME" in
        pm25)
            if $IS_ANOMALY; then
                VALUE=$(random_float 250.1 500.0) # High anomalous value
                log ">>> Generating ANOMALY for PM2.5: ${VALUE}"
            else
                VALUE=$(random_float 5.0 80.0)   # Normal range
            fi
            ;;
        pm10)
             if $IS_ANOMALY; then
                VALUE=$(random_float 420.1 800.0) # High anomalous value
                log ">>> Generating ANOMALY for PM10: ${VALUE}"
            else
                VALUE=$(random_float 10.0 150.0)  # Normal range
            fi
            ;;
        no2)
             if $IS_ANOMALY; then
                VALUE=$(random_float 200.1 400.0) # High anomalous value
                log ">>> Generating ANOMALY for NO2: ${VALUE}"
            else
                VALUE=$(random_float 10.0 100.0)  # Normal range
            fi
            ;;
        so2)
             if $IS_ANOMALY; then
                VALUE=$(random_float 50.1 150.0) # High anomalous value (adjust threshold as needed)
                log ">>> Generating ANOMALY for SO2: ${VALUE}"
            else
                VALUE=$(random_float 1.0 20.0)   # Normal range
            fi
            ;;
        o3)
             if $IS_ANOMALY; then
                VALUE=$(random_float 240.1 400.0) # High anomalous value (adjust threshold as needed)
                log ">>> Generating ANOMALY for O3: ${VALUE}"
            else
                VALUE=$(random_float 20.0 180.0)  # Normal range
            fi
            ;;
        *)
            VALUE=$(random_float 0.0 100.0) # Default fallback
            ;;
    esac

    # Construct JSON Payload (using jq if available, fallback otherwise)
    JSON_PAYLOAD=""
    if command -v jq &> /dev/null; then
        JSON_PAYLOAD=$(jq -n \
            --arg lat "$LAT" \
            --arg lon "$LON" \
            --arg param "$PARAM_NAME" \
            --argjson val "$VALUE" \
            '{latitude: ($lat | tonumber), longitude: ($lon | tonumber), ($param): $val}')
    else
        JSON_PAYLOAD="{\"latitude\": ${LAT}, \"longitude\": ${LON}, \"${PARAM_NAME}\": ${VALUE}}"
    fi

    # Send data using curl IN BACKGROUND (&) to achieve desired rate
    # Use -s for silent, -o /dev/null to discard output, optionally -w for status code
    # Add timeout options for robustness
    curl -X POST \
         -H "Content-Type: application/json" \
         -d "$JSON_PAYLOAD" \
         --connect-timeout 5 \
         --max-time 10 \
         -s -o /dev/null \
         "$API_ENDPOINT" &

    # Sleep to maintain the target rate
    sleep "$SLEEP_TIME"
done

log "Test duration reached. Waiting for background requests to complete..."
# Wait for all background curl processes to finish
wait
CURRENT_TIME=$(date +%s)
ACTUAL_DURATION=$((CURRENT_TIME - START_TIME))
log "Auto-test finished after ${ACTUAL_DURATION} seconds. Sent ${REQUEST_COUNT} requests."

exit 0