#!/bin/bash

# Script to send predetermined air quality data points to the ingest API.

# --- Configuration ---
# Set the target API endpoint URL. Default is http://localhost:8000.
# You can override this by setting the environment variable:
# export API_BASE_URL="http://your-api-host:port"
# ./auto-ingest.sh
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
INGEST_ENDPOINT="${API_BASE_URL}/api/v1/air_quality/ingest"

# Define predetermined data points as JSON strings in an array
# Adjust the JSON structure and values as needed for your API
declare -a DATA_POINTS=(
  '{"latitude": 51.5074, "longitude": -0.1278, "pm25": 15.2, "pm10": 25.5, "no2": 30.1, "so2": 5.3, "o3": 45.8}' # London
  '{"latitude": 40.7128, "longitude": -74.0060, "pm25": 22.8, "pm10": 35.1, "no2": 42.5, "so2": 8.1, "o3": 55.2}' # New York
  '{"latitude": 35.6895, "longitude": 139.6917, "pm25": 12.1, "pm10": 18.9, "no2": 25.6, "so2": 4.0, "o3": 60.5}' # Tokyo
  '{"latitude": -33.8688, "longitude": 151.2093, "pm25": 8.5, "pm10": 15.3, "no2": 15.0, "so2": 2.1, "o3": 38.7}' # Sydney (Cleaner)
  '{"latitude": 28.6139, "longitude": 77.2090, "pm25": 180.7, "pm10": 310.2, "no2": 95.3, "so2": 15.8, "o3": 70.1}' # Delhi (Higher Pollution)
)

# --- Script Logic ---
echo "--- Starting Data Ingestion Test ---"
echo "Target Endpoint: ${INGEST_ENDPOINT}"
echo ""

# Counter for successful requests
success_count=0
total_count=${#DATA_POINTS[@]}

# Loop through the data points and send POST requests
for data_json in "${DATA_POINTS[@]}"; do
  echo "Sending data: ${data_json}"

  # Use curl to send the POST request
  # -X POST: Specify POST method
  # -H "Content-Type: application/json": Set header for JSON data
  # -d "$data_json": Send the JSON string as the request body
  # -s: Silent mode (no progress meter)
  # -o /dev/null: Discard the response body (we only care about the status code here)
  # -w "%{http_code}": Print only the HTTP status code to stdout
  http_status=$(curl -X POST \
       -H "Content-Type: application/json" \
       -d "$data_json" \
       -s -o /dev/null -w "%{http_code}" \
       "${INGEST_ENDPOINT}")

  echo "Response Status Code: ${http_status}"

  # Check if the status code is 202 (Accepted) as expected
  if [ "$http_status" -eq 202 ]; then
    echo "Status: SUCCESS (Accepted)"
    ((success_count++))
  else
    echo "Status: FAILED (Expected 202, Got ${http_status})"
    # Optional: Exit on first failure?
    # exit 1
  fi
  echo "-------------------------------------"
  sleep 0.5 # Optional: Short delay between requests
done

echo ""
echo "--- Ingestion Test Complete ---"
echo "Total Requests Sent: ${total_count}"
echo "Successful (202 Accepted): ${success_count}"
echo "Failed: $((total_count - success_count))"

# Exit with success status if all requests were accepted
if [ "$success_count" -eq "$total_count" ]; then
  exit 0
else
  exit 1 # Exit with error status if any request failed
fi