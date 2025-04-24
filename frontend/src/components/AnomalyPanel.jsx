// frontend/src/components/AnomalyPanel.jsx
import React from 'react';

const AnomalyPanel = ({ anomalies = [], isLoading, error }) => {
  return (
    <div className="anomaly-panel">
      <div className="panel-header">
        <h3>Anomaly Alerts</h3>
      </div>
      
      {isLoading && <p>Loading anomalies...</p>}
      {error && <p style={{ color: '#ff6b6b' }}>Error loading anomalies: {error}</p>}
      
      {!isLoading && !error && anomalies.length === 0 && (
        <p>No anomalies detected recently.</p>
      )}
      
      {!isLoading && !error && anomalies.length > 0 && (
        <ul className="anomaly-list">
          {anomalies.map((anomaly) => (
            <li key={anomaly.id} className="anomaly-item">
              <div className="anomaly-time">
                {new Date(anomaly.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
              <div className="anomaly-description">
                {anomaly.parameter === 'pm25' 
                  ? `High PM₂.₅ level detected` 
                  : anomaly.parameter === 'pm10'
                    ? `High PM₁₀ value detected`
                    : `Elevated ${anomaly.parameter.toUpperCase()} level detected`}
              </div>
              <div className="anomaly-location">
                {getLocationName(anomaly.latitude, anomaly.longitude)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// Helper function to get a city name based on coordinates
// In a real app, you would use reverse geocoding or a location database
const getLocationName = (lat, lon) => {
  // This is a simplified example - in reality you would use a geocoding service
  // or a database lookup to find the city name based on coordinates
  
  // Some hardcoded examples for demo purposes
  if (Math.abs(lat - 40.71) < 1 && Math.abs(lon - (-74.01)) < 1) return "New York, USA";
  if (Math.abs(lat - 34.05) < 1 && Math.abs(lon - (-118.24)) < 1) return "Los Angeles, USA";
  if (Math.abs(lat - 19.43) < 1 && Math.abs(lon - (-99.13)) < 1) return "Mexico City, Mexico";
  if (Math.abs(lat - 28.61) < 1 && Math.abs(lon - 77.21) < 1) return "New Delhi, India";
  if (Math.abs(lat - 39.91) < 1 && Math.abs(lon - 116.40) < 1) return "Beijing, China";
  if (Math.abs(lat - 35.68) < 1 && Math.abs(lon - 139.69) < 1) return "Tokyo, Japan";
  if (Math.abs(lat - (-33.87)) < 1 && Math.abs(lon - 151.21) < 1) return "Sydney, Australia";
  
  // Default fallback - just show coordinates
  return `${lat.toFixed(2)}°, ${lon.toFixed(2)}°`;
};

export default AnomalyPanel;