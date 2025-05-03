// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import './App.css';
import MapComponent from './components/MapComponent';
import PollutionChart from './components/PollutionChart';
import AnomalyPanel from './components/AnomalyPanel';
import * as api from './services/api';

function App() {
  // Removed mapPoints, isLoadingPoints, errorPoints, currentZoom states
  const [anomalies, setAnomalies] = useState([]);
  const [selectedLocationData, setSelectedLocationData] = useState(null); // For the chart
  const [selectedParam, setSelectedParam] = useState('pm25'); // Default heatmap/chart param
  const [isLoadingAnomalies, setIsLoadingAnomalies] = useState(false);
  const [errorAnomalies, setErrorAnomalies] = useState(null);

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
    // Removed dependency array content, runs only once on mount
  }, []);

  // Callback function for when a location is selected on the map (via click)
  const handleLocationSelect = (data) => {
    console.log("App: Location selected/data received:", data);
    setSelectedLocationData(data); // Update state for PollutionChart
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
           {/* Map component now fetches its own data */}
           {/* Pass selectedParam for heatmap and anomaly markers */}
           {/* Pass the new onLocationSelect callback */}
          <MapComponent
            selectedParam={selectedParam}
            anomalies={anomalies}
            onLocationSelect={handleLocationSelect} // Pass the handler function
            // Removed points and onDataUpdate props
          />
        </div>

        <div className="sidebar">
          {/* Anomaly Panel: Selects an anomaly, updating selectedLocationData */}
          <AnomalyPanel
            anomalies={anomalies}
            isLoading={isLoadingAnomalies}
            error={errorAnomalies}
            onSelectAnomaly={(anomaly) => {
                console.log("App: Anomaly selected from panel:", anomaly);
                // We expect the anomaly object itself might contain the necessary fields
                // or we might need another fetch if it only has basic info.
                // Assuming Anomaly model has lat, lon, timestamp, value, parameter etc.
                // Format it slightly like the AirQualityReading for the chart if needed
                const chartData = {
                    latitude: anomaly.latitude,
                    longitude: anomaly.longitude,
                    timestamp: anomaly.timestamp,
                    [anomaly.parameter]: anomaly.value, // Set the specific parameter's value
                    // Add other fields as null/undefined if PollutionChart expects them
                    pm25: anomaly.parameter === 'pm25' ? anomaly.value : undefined,
                    pm10: anomaly.parameter === 'pm10' ? anomaly.value : undefined,
                    no2: anomaly.parameter === 'no2' ? anomaly.value : undefined,
                    so2: anomaly.parameter === 'so2' ? anomaly.value : undefined,
                    o3: anomaly.parameter === 'o3' ? anomaly.value : undefined,
                };
                setSelectedLocationData(chartData);
            }}
          />
          {/* Pollution Chart: Displays data for the selected location/anomaly */}
          <PollutionChart
            pollutionData={selectedLocationData} // Pass the data selected via map click or anomaly panel
            isDensityView={false} // Indicate it's showing single point data
            // selectedParam prop removed from PollutionChart previously, it uses all available data in pollutionData
          />
        </div>
      </div>
    </div>
  );
}

export default App;