// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import MapComponent from './components/MapComponent';
import AnomalyPanel from './components/AnomalyPanel';
import * as api from './services/api'; // Import API service
import './App.css';

function App() {
  const [mapPoints, setMapPoints] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [selectedLocationData, setSelectedLocationData] = useState(null);
  const [selectedParam, setSelectedParam] = useState('pm25'); // Default to PM2.5
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
        const pointsData = await api.fetchAirQualityPoints(200); // Fetch 200 points
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
         // Fetch anomalies for the last 24 hours (default in API)
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
  }, []); // Empty dependency array means this runs once on mount

  // Function to handle clicks on map markers
  const handleMarkerClick = async (point) => {
    console.log("Marker clicked:", point);
    // Optional: Fetch more detailed data for the clicked point if needed
    // setSelectedLocationData(point); // Simple display of clicked data
    // Or make a new API call:
    // const detailedData = await api.fetchAirQualityForLocation(point.latitude, point.longitude);
    // setSelectedLocationData(detailedData);
  };

  const handleParamChange = (event) => {
    setSelectedParam(event.target.value);
  };

   // Function to handle clicks directly on the map (optional)
   const handleMapClick = (latlng) => {
       console.log("Map clicked at:", latlng);
       // You could potentially fetch data for this clicked coordinate
       // Or trigger adding a new manual data point entry form etc.
   }

  return (
    <div className="App">
      <header className="App-header">
        <h1>World Air Quality Monitor</h1>
      </header>

      <div className="main-content">
        <div className="map-container-wrapper">

          {/* **************************************** */}
          {/* Parameter Selection Dropdown */}
          <div className="parameter-selector">
            <label htmlFor="param-select">Heatmap Parameter: </label>
            <select id="param-select" value={selectedParam} onChange={handleParamChange}>
              <option value="pm25">PM2.5</option>
              <option value="pm10">PM10</option>
              <option value="no2">NO₂</option>
              <option value="so2">SO₂</option>
              <option value="o3">O₃</option>
            </select>
          </div>
          {/* **************************************** */}

          <h2>Air Quality Heatmap ({selectedParam.toUpperCase()})</h2> {/* Dynamic Title */}
          {isLoadingPoints && <p>Loading map data...</p>}
          {errorPoints && <p style={{ color: 'red' }}>Error loading map data: {errorPoints}</p>}

          {/* **************************************** */}
          {/* Pass selectedParam down to MapComponent */}
          <MapComponent
            points={mapPoints}
            selectedParam={selectedParam} // Pass the state down
          />
          {/* **************************************** */}

        </div>

        <div className="sidebar">
          <AnomalyPanel
            anomalies={anomalies}
            isLoading={isLoadingAnomalies}
            error={errorAnomalies}
          />
          {/* ... other sidebar content ... */}
        </div>
      </div>
    </div>
  );
}

export default App;
