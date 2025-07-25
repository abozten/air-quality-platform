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

// --- NEW: Fetch Heatmap Data ---
/**
 * Fetches aggregated air quality data specifically for heatmap rendering
 * based on the current map view bounds and zoom level.
 * @param {number} minLat
 * @param {number} maxLat
 * @param {number} minLon
 * @param {number} maxLon
 * @param {number} zoom Current map zoom level
 * @param {string} window Time window (e.g., '1h', '24h')
 * @returns {Promise<AggregatedAirQualityPoint[]>}
 */
export const fetchHeatmapData = async (minLat, maxLat, minLon, maxLon, zoom, window = '1h') => {
  const params = new URLSearchParams({
    min_lat: minLat,
    max_lat: maxLat,
    min_lon: minLon,
    max_lon: maxLon,
    window: window
  });
  // Add zoom only if it's a valid number
  if (typeof zoom === 'number' && !isNaN(zoom)) {
      params.append('zoom', zoom);
  }

  console.log(`API: Fetching heatmap data with params: ${params.toString()}`);
  const response = await fetch(`${API_BASE_URL}/air_quality/heatmap_data?${params.toString()}`);
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

// --- NEW: Fetch Location History ---
/**
 * Fetches historical air quality data for a specific location (geohash) and parameter.
 * @param {string} geohash The geohash representing the location.
 * @param {string} parameter The pollution parameter (e.g., 'pm25', 'no2').
 * @param {string} window Time window (e.g., '24h', '7d').
 * @param {string} aggregate Aggregation interval (e.g., '10m', '1h').
 * @returns {Promise<HistoricalDataPoint[]>} Array of { timestamp, value } objects.
 */
export const fetchLocationHistory = async (geohash, parameter, window = '24h', aggregate = '1h') => {
  if (!geohash || !parameter) {
    console.error("Geohash and parameter are required for fetching history.");
    return []; // Return empty array if required params are missing
  }
  const params = new URLSearchParams({
    parameter: parameter,
    window: window,
    aggregate: aggregate
  });

  console.log(`API: Fetching history for ${parameter} at ${geohash} with params: ${params.toString()}`);
  const response = await fetch(`${API_BASE_URL}/air_quality/location_history/${geohash}?${params.toString()}`);
  // Handle potential errors more gracefully for history, maybe return empty array
  try {
      return await handleResponse(response);
  } catch (error) {
      console.error(`API: Failed to fetch history for ${parameter} at ${geohash}:`, error);
      return []; // Return empty array on fetch error
  }
};

// --- Fetch location history using coordinates ---
/**
 * Fetches historical time series data for a specific parameter at the given coordinates
 * @param {number} lat Latitude
 * @param {number} lon Longitude
 * @param {string} parameter The pollutant parameter to fetch history for (e.g., 'pm25', 'no2')
 * @param {number} precision Geohash precision to use (determines cell size)
 * @param {string} window Time window to look back (e.g., '24h', '7d')
 * @param {string} aggregate Aggregation time window (e.g., '10m', '1h')
 * @returns {Promise<Array<TimeSeriesDataPoint>>} Array of time series data points
 */
export const fetchLocationHistoryByCoordinates = async (lat, lon, parameter, precision = 5, window = '24h', aggregate = '10m') => {
  if (lat === undefined || lon === undefined || !parameter) {
    console.error("Missing required parameters for history request");
    return [];
  }
  
  const params = new URLSearchParams({
    lat: lat,
    lon: lon,
    geohash_precision: precision,
    window: window,
    aggregate: aggregate
  });
  
  console.log(`API: Fetching history data for ${parameter} at (${lat.toFixed(4)}, ${lon.toFixed(4)})`);
  const response = await fetch(`${API_BASE_URL}/air_quality/history/coordinates/${parameter}?${params.toString()}`);
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

