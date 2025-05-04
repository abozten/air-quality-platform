// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import './App.css';
import MapComponent from './components/MapComponent';
import PollutionChart from './components/PollutionChart';
import AnomalyPanel from './components/AnomalyPanel';
import LocationHistoryChart from './components/LocationHistoryChart'; // Import the new chart
import * as api from './services/api';

function App() {
  const [anomalies, setAnomalies] = useState([]);
  const [selectedLocationData, setSelectedLocationData] = useState(null); // For the bar chart
  const [selectedParam, setSelectedParam] = useState('pm25'); // Default heatmap/chart param
  const [isLoadingAnomalies, setIsLoadingAnomalies] = useState(false);
  const [errorAnomalies, setErrorAnomalies] = useState(null);
  const [locationHistoryData, setLocationHistoryData] = useState({}); // Store history data per parameter { pm25: [...], no2: [...] }
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [errorHistory, setErrorHistory] = useState(null);

  // Fetch anomalies on component mount (only once)
  useEffect(() => {
    const loadAnomalies = async () => {
      setIsLoadingAnomalies(true);
      setErrorAnomalies(null);
      try {
        // Fetch anomalies for the last 24 hours (default in API)
        const anomalyData = await api.fetchAnomalies();
        console.log(`App: Fetched ${anomalyData?.length ?? 0} anomalies.`);
        setAnomalies(anomalyData || []); // Ensure it's an array
      } catch (err) {
        console.error("App: Failed to fetch anomalies:", err);
        setErrorAnomalies(err.message || "Failed to load anomalies");
      } finally {
        setIsLoadingAnomalies(false);
      }
    };

    loadAnomalies();
  }, []);

  // Fetch location details AND history when a location is selected
  const handleLocationSelect = async (data) => {
    console.log("App: handleLocationSelect triggered.");
    console.log("App: Received data:", data); // Log the entire data object

    // Check if data is null or undefined first
    if (!data) {
      console.log("App: Received null or undefined data. Cannot fetch history.");
      setSelectedLocationData(null); // Clear selected data if received data is null/undefined
      setLocationHistoryData({}); // Clear history
      setErrorHistory(null);
      return; // Exit early
    }

    setSelectedLocationData(data); // Update state for PollutionChart (bar chart)

    // Reset history data and errors before potentially fetching new data
    setLocationHistoryData({});
    setErrorHistory(null);

    // Explicitly check for geohash
    if (data.geohash) {
      console.log(`App: Geohash found: ${data.geohash}. Proceeding to fetch history.`);
      setIsLoadingHistory(true);
      const geohash = data.geohash;
      const parametersToFetch = ['pm25', 'pm10', 'no2', 'so2', 'o3']; // Parameters for history charts
      const historyPromises = parametersToFetch.map(param =>
        api.fetchLocationHistory(geohash, param, '24h', '10m') // Fetch 24h history, 10min aggregate
          .then(history => ({ param, history }))
          .catch(err => {
            console.error(`App: Failed to fetch history for ${param} at ${geohash}:`, err);
            // Store error per parameter or a general error
            setErrorHistory(prev => ({ ...prev, [param]: err.message || `Failed to load ${param} history` }));
            return { param, history: [] }; // Return empty on error for this param
          })
      );

      try {
        const results = await Promise.all(historyPromises);
        const newHistoryData = results.reduce((acc, { param, history }) => {
          acc[param] = history;
          return acc;
        }, {});
        setLocationHistoryData(newHistoryData);
        console.log("App: Fetched history data:", newHistoryData);
      } catch (err) {
        console.error("App: Unexpected error fetching all history data:", err);
        setErrorHistory(prev => ({ ...prev, general: "An unexpected error occurred fetching history." }));
      } finally {
        setIsLoadingHistory(false);
      }
    } else {
      console.log("App: No geohash found in the received data. Cannot fetch history.");
      // Keep selectedLocationData for the PollutionChart, but history won't load
    }
  };

  // Handler for parameter selection dropdown
  const handleParamChange = (event) => {
    setSelectedParam(event.target.value);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>World Air Quality Monitor</h1>
        {/* Parameter Selection Dropdown Moved to Header for better layout */}
        <div className="parameter-selector">
          <label htmlFor="param-select">Display Parameter: </label>
          <select id="param-select" value={selectedParam} onChange={handleParamChange}>
            <option value="pm25">PM₂.₅</option>
            <option value="pm10">PM₁₀</option>
            <option value="no2">NO₂</option>
            <option value="so2">SO₂</option>
            <option value="o3">O₃</option>
          </select>
        </div>
      </header>

      <div className="main-content">
        <div className="map-container-wrapper">
          <MapComponent
            selectedParam={selectedParam}
            anomalies={anomalies}
            onLocationSelect={handleLocationSelect} // Pass the combined handler
          />
        </div>

        <div className="sidebar">
          <AnomalyPanel
            anomalies={anomalies}
            isLoading={isLoadingAnomalies}
            error={errorAnomalies}
            onSelectAnomaly={(anomaly) => {
              console.log("App: Anomaly selected from panel:", anomaly);
              const chartData = {
                latitude: anomaly.latitude,
                longitude: anomaly.longitude,
                timestamp: anomaly.timestamp,
                [anomaly.parameter]: anomaly.value,
                pm25: anomaly.parameter === 'pm25' ? anomaly.value : undefined,
                pm10: anomaly.parameter === 'pm10' ? anomaly.value : undefined,
                no2: anomaly.parameter === 'no2' ? anomaly.value : undefined,
                so2: anomaly.parameter === 'so2' ? anomaly.value : undefined,
                o3: anomaly.parameter === 'o3' ? anomaly.value : undefined,
              };
              setSelectedLocationData(chartData);
              handleLocationSelect({
                latitude: anomaly.latitude,
                longitude: anomaly.longitude,
                timestamp: anomaly.timestamp,
                geohash: anomaly.geohash, // Assuming anomaly has geohash
                [anomaly.parameter]: anomaly.value,
                pm25: anomaly.parameter === 'pm25' ? anomaly.value : undefined,
                pm10: anomaly.parameter === 'pm10' ? anomaly.value : undefined,
                no2: anomaly.parameter === 'no2' ? anomaly.value : undefined,
                so2: anomaly.parameter === 'so2' ? anomaly.value : undefined,
                o3: anomaly.parameter === 'o3' ? anomaly.value : undefined,
              });
            }}
          />
          <PollutionChart
            pollutionData={selectedLocationData}
          />
          {selectedLocationData?.geohash && (
            <div className="history-charts-section">
              <h4>Historical Trends (Last 24h)</h4>
              {isLoadingHistory && <p>Loading history...</p>}
              {errorHistory?.general && <p className="error-message">{errorHistory.general}</p>}
              {Object.entries(locationHistoryData)
                .filter(([param, history]) => history && history.length > 0)
                .map(([param, history]) => (
                  <LocationHistoryChart
                    key={param}
                    historyData={history}
                    parameter={param}
                    geohash={selectedLocationData.geohash}
                  />
              ))}
              {errorHistory && Object.entries(errorHistory)
                .filter(([param, errorMsg]) => param !== 'general' && errorMsg && (!locationHistoryData[param] || locationHistoryData[param].length === 0))
                .map(([param, errorMsg]) => (
                  <p key={param} className="error-message">Could not load history for {param}: {errorMsg}</p>
              ))}
              {!isLoadingHistory && Object.values(locationHistoryData).every(h => h.length === 0) && !errorHistory?.general && Object.values(errorHistory || {}).filter(e => e).length === 0 && (
                <p>No historical data available for this location in the last 24 hours.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;