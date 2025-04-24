// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import MapComponent from './components/MapComponent';
import AnomalyPanel from './components/AnomalyPanel';
import PollutionChart from './components/PollutionChart';
import * as api from './services/api';
import './App.css';

function App() {
  const [mapPoints, setMapPoints] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [pollutionData, setPollutionData] = useState({});
  const [selectedParam, setSelectedParam] = useState('pm25');
  const [isLoadingPoints, setIsLoadingPoints] = useState(false);
  const [isLoadingAnomalies, setIsLoadingAnomalies] = useState(false);
  const [errorPoints, setErrorPoints] = useState(null);
  const [errorAnomalies, setErrorAnomalies] = useState(null);

  // Fetch initial map points and anomalies on component mount
  useEffect(() => {
    const loadInitialData = async () => {
      // Fetch points for map
      setIsLoadingPoints(true);
      setErrorPoints(null);
      try {
        const pointsData = await api.fetchAirQualityPoints(200);
        setMapPoints(pointsData);
      } catch (err) {
        console.error("Failed to fetch map points:", err);
        setErrorPoints(err.message);
      } finally {
        setIsLoadingPoints(false);
      }

      // Fetch anomalies
      setIsLoadingAnomalies(true);
      setErrorAnomalies(null);
      try {
        const anomalyData = await api.fetchAnomalies();
        setAnomalies(anomalyData);
      } catch (err) {
        console.error("Failed to fetch anomalies:", err);
        setErrorAnomalies(err.message);
      } finally {
        setIsLoadingAnomalies(false);
      }
    };

    loadInitialData();
    
    // Auto-refresh data every 5 minutes
    const refreshInterval = setInterval(() => {
      loadInitialData();
    }, 5 * 60 * 1000);
    
    return () => clearInterval(refreshInterval);
  }, []);

  // Handle parameter change for the heatmap
  const handleParamChange = (event) => {
    setSelectedParam(event.target.value);
  };

  return (
    <div className="App">
      {/* Header & Navigation */}
      <header className="App-header">
        <h1>AirMon</h1>
        <div className="nav-links">
          <a href="#" className="active">Home</a>
          <a href="#">Detailed Analysis</a>
          <a href="#">About</a>
          <a href="#">API Docs</a>
        </div>
      </header>

      {/* Main Content */}
      <div className="main-content">
        {/* Hero Section */}
        <section className="hero-section">
          <h2>Air Monitoring Platform</h2>
          <p>A web-based platform for collecting, analyzing, and visualizing air pollution data worldwide.</p>
        </section>

        {/* Map Section */}
        <div className="map-container">
          {isLoadingPoints && <div className="loading-overlay">Loading map data...</div>}
          {errorPoints && <div className="error-message">Error loading map data: {errorPoints}</div>}
          
          <div className="map-controls">
            <label htmlFor="param-select">Display Parameter: </label>
            <select id="param-select" value={selectedParam} onChange={handleParamChange}>
              <option value="pm25">PM2.5</option>
              <option value="pm10">PM10</option>
              <option value="no2">NO₂</option>
              <option value="so2">SO₂</option>
              <option value="o3">O₃</option>
            </select>
          </div>
          
          <MapComponent 
            points={mapPoints} 
            anomalies={anomalies} 
            selectedParam={selectedParam}
          />
        </div>

        {/* Panels Section */}
        <div className="panels-section">
          {/* Air Pollution Level Charts */}
          <PollutionChart pollutionData={pollutionData} />
          
          {/* Anomaly Panel */}
          <AnomalyPanel 
            anomalies={anomalies}
            isLoading={isLoadingAnomalies}
            error={errorAnomalies}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
