// frontend/src/services/api.js
const API_BASE_URL = 'http://localhost:8000/api/v1'; // Your FastAPI backend URL

// Helper function to handle fetch responses
const handleResponse = async (response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({})); // Try to parse error details
    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

// Fetch multiple air quality data points for the map
export const fetchAirQualityPoints = async (limit = 50) => {
  const response = await fetch(`${API_BASE_URL}/air_quality/points?limit=${limit}`);
  return handleResponse(response);
};

// Fetch air quality for a specific location (e.g., when clicking a marker)
export const fetchAirQualityForLocation = async (lat, lon) => {
    if (lat === undefined || lon === undefined) {
        console.error("Latitude or Longitude is undefined");
        return null; // Or throw an error
    }
    const response = await fetch(`${API_BASE_URL}/air_quality/location?lat=${lat}&lon=${lon}`);
    return handleResponse(response);
};


// Fetch anomalies within a time range
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

// Fetch pollution density for a region (Placeholder - needs region input)
export const fetchPollutionDensity = async (region) => {
    if (!region) {
        console.error("Region is required for pollution density fetch");
        return null; // Or throw an error
    }
    const response = await fetch(`${API_BASE_URL}/pollution_density?region=${encodeURIComponent(region)}`);
    return handleResponse(response);
};