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
        const pointsData = await api.fetchAirQualityPoints(50); // Fetch 50 points
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
          <h2>Air Quality Map</h2>
          {isLoadingPoints && <p>Loading map data...</p>}
          {errorPoints && <p style={{ color: 'red' }}>Error loading map data: {errorPoints}</p>}
          <MapComponent
                points={mapPoints}
                onMarkerClick={handleMarkerClick}
                // onMapClick={handleMapClick} // Pass handler if using map click events
           />
           {/* Placeholder for selected location details */}
           {/* {selectedLocationData && (
               <div className="selected-location-details">
                   <h3>Details for Clicked Location</h3>
                   <pre>{JSON.stringify(selectedLocationData, null, 2)}</pre>
               </div>
           )} */}
        </div>

        <div className="sidebar">
           <AnomalyPanel
              anomalies={anomalies}
              isLoading={isLoadingAnomalies}
              error={errorAnomalies}
           />
           {/* Placeholder for graphs or other controls */}
           <div className="density-placeholder">
                <h2>Pollution Density (Future)</h2>
                <p>Region selection and density display will go here.</p>
                {/* Example button to test density endpoint */}
                <button onClick={async () => {
                    try {
                        const density = await api.fetchPollutionDensity("London");
                        alert(`Fetched Density for London: ${JSON.stringify(density)}`);
                    } catch (error) {
                        alert(`Error fetching density: ${error.message}`);
                    }
                }}>Test Fetch Density (London)</button>
           </div>
        </div>
      </div>
    </div>
  );
}

export default App;