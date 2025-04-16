// frontend/src/components/AnomalyPanel.jsx
import React from 'react';

const AnomalyPanel = ({ anomalies = [], isLoading, error }) => {
  return (
    <div className="anomaly-panel">
      <h2>Detected Anomalies (Last 24h)</h2>
      {isLoading && <p>Loading anomalies...</p>}
      {error && <p style={{ color: 'red' }}>Error loading anomalies: {error}</p>}
      {!isLoading && !error && anomalies.length === 0 && <p>No anomalies detected recently.</p>}
      {!isLoading && !error && anomalies.length > 0 && (
        <ul>
          {anomalies.map((anomaly) => (
            <li key={anomaly.id}>
              <strong>{anomaly.parameter.toUpperCase()} Alert:</strong> {anomaly.description}
              <br />
              Value: {anomaly.value.toFixed(1)} at ({anomaly.latitude.toFixed(2)}, {anomaly.longitude.toFixed(2)})
              <br />
              Time: {new Date(anomaly.timestamp).toLocaleString()}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default AnomalyPanel;