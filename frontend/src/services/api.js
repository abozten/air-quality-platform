// frontend/src/services/api.js
const API_BASE_URL = 'http://localhost:8000/api/v1'; // Your FastAPI backend URL

// Helper function to handle fetch responses
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

// Fetch aggregated air quality points for the map visualization
export const fetchAirQualityPoints = async (limit = 200, precision = 6) => {
  const response = await fetch(`${API_BASE_URL}/air_quality/points?limit=${limit}&geohash_precision=${precision}`);
  return handleResponse(response);
};

// Fetch specific location data (when clicking on a point)
export const fetchAirQualityForLocation = async (lat, lon) => {
  if (lat === undefined || lon === undefined) {
    console.error("Latitude or Longitude is undefined");
    return null;
  }
  const response = await fetch(`${API_BASE_URL}/air_quality/location?lat=${lat}&lon=${lon}`);
  return handleResponse(response);
};

// Fetch anomalies within a time range (defaults to last 24h in API)
export const fetchAnomalies = async (startTime = null, endTime = null) => {
  let url = `${API_BASE_URL}/anomalies`;
  const params = new URLSearchParams();
  if (startTime) params.append('start_time', startTime.toISOString());
  if (endTime) params.append('end_time', endTime.toISOString());
  
  if (params.toString()) {
    url += `?${params.toString()}`;
  }
  
  const response = await fetch(url);
  return handleResponse(response);
};

// Fetch pollution density for a specific bounding box region
export const fetchPollutionDensity = async (minLat, maxLat, minLon, maxLon, window = '24h') => {
  const params = new URLSearchParams({
    min_lat: minLat,
    max_lat: maxLat,
    min_lon: minLon,
    max_lon: maxLon,
    window: window
  });
  
  const response = await fetch(`${API_BASE_URL}/pollution_density?${params.toString()}`);
  return handleResponse(response);
};

// Optional: Function to ingest new data points (for testing/demo purposes)
export const ingestAirQualityData = async (data) => {
  const response = await fetch(`${API_BASE_URL}/air_quality/ingest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  });
  
  return handleResponse(response);
};