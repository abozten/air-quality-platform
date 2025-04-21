# Ensure your backend services are running before executing these commands.
# The API is typically accessible at http://localhost:8000

echo "Injecting data point for Istanbul (moderate pollution)..."
curl -X POST http://localhost:8000/api/v1/air_quality/ingest \
-H "Content-Type: application/json" \
-d '{
  "latitude": 41.0,
  "longitude": 28.9,
  "pm25": 35.5,
  "pm10": 60.2,
  "no2": 45.1
}'
echo "" # New line for readability

echo "Injecting data point for Ankara (slightly higher)..."
curl -X POST http://localhost:8000/api/v1/air_quality/ingest \
-H "Content-Type: application/json" \
-d '{
  "latitude": 39.9,
  "longitude": 32.8,
  "pm25": 48.0,
  "pm10": 85.5,
  "so2": 15.3
}'
echo ""

echo "Injecting data point for Izmir (relatively clean)..."
curl -X POST http://localhost:8000/api/v1/air_quality/ingest \
-H "Content-Type: application/json" \
-d '{
  "latitude": 38.4,
  "longitude": 27.1,
  "pm25": 18.2,
  "pm10": 35.9,
  "o3": 70.4
}'
echo ""

echo "Injecting data point for Antalya (triggering a PM2.5 anomaly)..."
# This value (260.0) is above the default threshold_pm25_hazardous (250.0)
curl -X POST http://localhost:8000/api/v1/air_quality/ingest \
-H "Content-Type: application/json" \
-d '{
  "latitude": 36.8,
  "longitude": 30.7,
  "pm25": 260.0,
  "pm10": 120.0,
  "no2": 50.0
}'
echo ""

echo "Injecting data point for Erzurum (some values)..."
curl -X POST http://localhost:8000/api/v1/air_quality/ingest \
-H "Content-Type: application/json" \
-d '{
  "latitude": 39.9,
  "longitude": 41.3,
  "pm25": 75.0,
  "pm10": 155.0
}'
echo ""

echo "Data ingestion requests sent. Please wait a moment for the worker to process the queue."