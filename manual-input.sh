#!/bin/bash

# Simple script to send a single air quality reading to the API
# Usage: ./manual-input.sh <latitude> <longitude> <parameter> <value>
# Example: ./manual-input.sh 51.5 -0.1 pm25 25.5

# --- Configuration ---
# Use environment variable or default
API_URL="${API_BASE_URL:-http://localhost:8000/api/v1}/air_quality/ingest"

# --- Input Validation ---
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <latitude> <longitude> <parameter> <value>"
    echo "Parameters can be: pm25, pm10, no2, so2, o3"
    exit 1
fi

LATITUDE=$1
LONGITUDE=$2
PARAMETER=$(echo "$3" | tr '[:upper:]' '[:lower:]') # Convert param to lowercase
VALUE=$4

# Basic validation for latitude and longitude (adjust regex as needed)
if ! [[ "$LATITUDE" =~ ^-?[0-9]{1,2}(\.[0-9]+)?$ ]] || \
   ! [[ "$LONGITUDE" =~ ^-?[0-9]{1,3}(\.[0-9]+)?$ ]]; then
   echo "Error: Invalid latitude or longitude format."
   exit 1
fi
# Basic validation for value
 if ! [[ "$VALUE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
   echo "Error: Invalid numeric value for parameter."
   exit 1
fi

# Check parameter validity
case "$PARAMETER" in
    pm25|pm10|no2|so2|o3)
        # Parameter is valid
        ;;
    *)
        echo "Error: Invalid parameter '$PARAMETER'. Must be one of pm25, pm10, no2, so2, o3."
        exit 1
        ;;
esac

# --- Construct JSON Payload ---
# Uses jq if available for cleaner JSON construction, otherwise uses simple string concat
if command -v jq &> /dev/null; then
    JSON_PAYLOAD=$(jq -n \
        --arg lat "$LATITUDE" \
        --arg lon "$LONGITUDE" \
        --arg param "$PARAMETER" \
        --argjson val "$VALUE" \
        '{latitude: ($lat | tonumber), longitude: ($lon | tonumber), ($param): $val}')
else
    # Fallback without jq (less robust for types)
    JSON_PAYLOAD="{\"latitude\": ${LATITUDE}, \"longitude\": ${LONGITUDE}, \"${PARAMETER}\": ${VALUE}}"
fi

echo "Sending data to: $API_URL"
echo "Payload: $JSON_PAYLOAD"

# --- Send Data using curl ---
curl -X POST \
     -H "Content-Type: application/json" \
     -d "$JSON_PAYLOAD" \
     "$API_URL"

# Print newline after curl output
echo ""

exit 0