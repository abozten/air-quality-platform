// frontend/src/components/PollutionChart.jsx
import React from 'react';
import './PollutionChart.css'; // We'll add some basic CSS

// Define approximate max values for scaling bars (can be adjusted based on AQI levels)
// Units are typically µg/m³
const POLLUTANT_MAX_VALUES = {
  pm25: 100, // Example max for PM2.5
  no2: 80,   // Example max for NO2
  o3: 120,   // Example max for O3
};

// Define colors (can be expanded for AQI levels)
const POLLUTANT_COLORS = {
  pm25: '#8a2be2', // Purple
  no2: '#4CAF50',  // Green
  o3: '#ffc107',   // Amber
};

const PollutionChart = ({ pollutionData }) => {
  // Helper function to render a single pollutant line with a bar
  const renderPollutantLine = (pollutantKey, label, unit) => {
    const value = pollutionData ? pollutionData[pollutantKey] : null;
    const maxValue = POLLUTANT_MAX_VALUES[pollutantKey];
    const color = POLLUTANT_COLORS[pollutantKey];

    // Calculate bar width percentage, handle null/undefined/zero values
    let barWidthPercent = 0;
    if (value !== null && value !== undefined && maxValue > 0 && value > 0) {
      barWidthPercent = Math.min((value / maxValue) * 100, 100); // Cap at 100%
    }

    const displayValue = (value !== null && value !== undefined)
      ? value.toFixed(1) // Format to one decimal place
      : 'N/A'; // Display 'N/A' if data is missing

    return (
      <div className="chart-line" key={pollutantKey}>
        <div className="chart-label">{label}</div>
        <div className="chart-visual">
          <svg width="100%" height="20" viewBox="0 0 100 20" preserveAspectRatio="none">
            {/* Background bar (optional) */}
            <rect x="0" y="5" width="100%" height="10" fill="#e0e0e0" rx="3" ry="3" />
            {/* Data bar */}
            {barWidthPercent > 0 && (
               <rect
                 x="0"
                 y="5"
                 width={`${barWidthPercent}%`}
                 height="10"
                 fill={color}
                 rx="3" // Rounded corners
                 ry="3"
               />
            )}
          </svg>
        </div>
        <div className="chart-value">
          {displayValue} <span className="chart-unit">{unit}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="air-pollution-panel">
      <div className="panel-header">
        <h3>Air Quality Reading</h3>
        {pollutionData?.timestamp && (
          <span className="timestamp">
            Last updated: {new Date(pollutionData.timestamp).toLocaleString()}
          </span>
        )}
         {!pollutionData && (
           <span className="timestamp">No data available for selected location.</span>
         )}
      </div>

      <div className="pollution-charts">
        {renderPollutantLine('pm25', 'PM 2.5', 'µg/m³')}
        {renderPollutantLine('no2', 'NO₂', 'µg/m³')}
        {renderPollutantLine('o3', 'O₃', 'µg/m³')}
        {/* Add other pollutants if needed and available in your data */}
        {/* e.g., renderPollutantLine('pm10', 'PM 10', 'µg/m³') */}
        {/* e.g., renderPollutantLine('co', 'CO', 'µg/m³') */}
        {/* e.g., renderPollutantLine('so2', 'SO₂', 'µg/m³') */}
      </div>
       {pollutionData?.geohash && (
          <div className="location-info">
              Geohash: {pollutionData.geohash} ({pollutionData.latitude?.toFixed(4)}, {pollutionData.longitude?.toFixed(4)})
          </div>
       )}
    </div>
  );
};

export default PollutionChart;