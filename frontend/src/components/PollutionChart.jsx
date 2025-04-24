// frontend/src/components/PollutionChart.jsx
import React from 'react';

const PollutionChart = ({ pollutionData }) => {
  // Function to generate a random wave pattern for visualization
  const generateRandomWave = (min, max) => {
    const numPoints = 50;
    const waveHeight = Math.random() * 20 + 10;
    const waveFrequency = Math.random() * 0.5 + 0.2;
    
    let pathData = `M 0,${max/2}`;
    
    for (let i = 0; i < numPoints; i++) {
      const x = (i / (numPoints - 1)) * 100;
      const y = max/2 + Math.sin(i * waveFrequency) * waveHeight;
      pathData += ` L ${x},${y}`;
    }
    
    return pathData;
  };
  
  return (
    <div className="air-pollution-panel">
      <div className="panel-header">
        <h3>Air Pollution Levels</h3>
      </div>
      
      <div className="pollution-charts">
        {/* PM2.5 Chart */}
        <div className="chart-line">
          <div className="chart-label">PM 2.5</div>
          <div className="chart-visual">
            <svg width="100%" height="30" viewBox="0 0 100 30">
              <path 
                d={generateRandomWave(5, 25)} 
                stroke="#8a2be2" 
                strokeWidth="2" 
                fill="none" 
              />
            </svg>
          </div>
        </div>
        
        {/* NO2 Chart */}
        <div className="chart-line">
          <div className="chart-label">NO₂</div>
          <div className="chart-visual">
            <svg width="100%" height="30" viewBox="0 0 100 30">
              <path 
                d={generateRandomWave(5, 25)} 
                stroke="#4CAF50" 
                strokeWidth="2" 
                fill="none" 
              />
            </svg>
          </div>
        </div>
        
        {/* O3 Chart */}
        <div className="chart-line">
          <div className="chart-label">O₃</div>
          <div className="chart-visual">
            <svg width="100%" height="30" viewBox="0 0 100 30">
              <path 
                d={generateRandomWave(5, 25)} 
                stroke="#ffc107" 
                strokeWidth="2" 
                fill="none" 
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PollutionChart;