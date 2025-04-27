// frontend/src/services/api.js
const API_BASE_URL = 'http://localhost:8000/api/v1'; // Your FastAPI backend URL
export { API_BASE_URL }; // Export API_BASE_URL for use in other components

// Helper function to handle fetch responses
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

/**
 * Convert map zoom level to appropriate geohash precision
 * Zoom levels:
 * 0-3: world/continent view (precision 2)
 * 4-6: country view (precision 3)
 * 7-10: region/city view (precision 4)
 * 11-14: neighborhood view (precision 5)
 * 15+: street level view (precision 6)
 */
export const zoomToGeohashPrecision = (zoom) => {
  if (zoom === undefined) return 3; // Default
  
  if (zoom <= 3) return 2;
  if (zoom <= 6) return 3;
  if (zoom <= 10) return 4;
  if (zoom <= 14) return 5;
  return 6;
};

// Fetch aggregated air quality points for the map visualization
export const fetchAirQualityPoints = async (limit = 200, zoom = 2) => {
  const precision = zoomToGeohashPrecision(zoom);
  const response = await fetch(`${API_BASE_URL}/air_quality/points?limit=${limit}&geohash_precision=${precision}`);
  return handleResponse(response);
};

// Fetch specific location data (when clicking on a point) also used for the chart.
export const fetchAirQualityForLocation = async (lat, lon, zoom = 10, window = '1h') => {
  if (lat === undefined || lon === undefined) {
    console.error("Latitude or Longitude is undefined");
    return null;
  }
  
  const geohashPrecision = zoomToGeohashPrecision(zoom);
  
  const params = new URLSearchParams({
    lat: lat,
    lon: lon,
    geohash_precision: geohashPrecision,
    window: window
  });
  
  const response = await fetch(`${API_BASE_URL}/air_quality/location?${params.toString()}`);
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

