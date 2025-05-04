// frontend/src/components/PollutionChart.jsx
import React from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import './PollutionChart.css';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

// Define colors for various pollutants
const POLLUTANT_COLORS = {
  pm25: 'rgba(138, 43, 226, 0.7)', // Purple
  no2: 'rgba(76, 175, 80, 0.7)',  // Green
  o3: 'rgba(255, 193, 7, 0.7)',   // Amber
  pm10: 'rgba(255, 99, 132, 0.7)', // Pink/Red
  so2: 'rgba(54, 162, 235, 0.7)', // Blue
  co: 'rgba(153, 102, 255, 0.7)', // Indigo
};

const POLLUTANT_BORDER_COLORS = {
  pm25: 'rgba(138, 43, 226, 1)',
  no2: 'rgba(76, 175, 80, 1)',
  o3: 'rgba(255, 193, 7, 1)',
  pm10: 'rgba(255, 99, 132, 1)',
  so2: 'rgba(54, 162, 235, 1)',
  co: 'rgba(153, 102, 255, 1)',
};

// Mapping for display names
const POLLUTANT_NAMES = {
    pm25: 'PM 2.5',
    no2: 'NO₂',
    o3: 'O₃',
    pm10: 'PM 10',
    so2: 'SO₂',
    co: 'CO',
};

const PollutionChart = ({ pollutionData }) => {

  // Dynamically generate chart data based on available pollutants
  const availablePollutants = pollutionData
    ? Object.keys(pollutionData).filter(key =>
        POLLUTANT_NAMES[key] && pollutionData[key] !== null && pollutionData[key] !== undefined
      )
    : [];

  const chartLabels = availablePollutants.map(key => POLLUTANT_NAMES[key]);
  const chartValues = availablePollutants.map(key => pollutionData[key] ?? 0);
  const backgroundColors = availablePollutants.map(key => POLLUTANT_COLORS[key] || 'rgba(201, 203, 207, 0.7)'); // Default grey
  const borderColors = availablePollutants.map(key => POLLUTANT_BORDER_COLORS[key] || 'rgba(201, 203, 207, 1)');

  const chartData = {
    labels: chartLabels,
    datasets: [
      {
        label: 'Concentration (µg/m³)', // This label might not be shown if legend is off
        data: chartValues,
        backgroundColor: backgroundColors,
        borderColor: borderColors,
        borderWidth: 1,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      title: {
        display: false,
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.8)', // Dark tooltip
        titleColor: '#fff',
        bodyColor: '#fff',
        callbacks: {
          label: function(context) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            if (context.parsed.y !== null) {
              // Assuming all these pollutants use µg/m³
              label += context.parsed.y.toFixed(1) + ' µg/m³';
            }
            return label;
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Concentration (µg/m³)',
          color: '#ccc', // Light color for axis title
        },
        ticks: {
          color: '#ccc', // Light color for axis labels (ticks)
        },
        grid: {
          color: 'rgba(204, 204, 204, 0.2)', // Lighter grid lines for dark mode
        },
      },
      x: {
         ticks: {
             color: '#ccc', // Light color for axis labels (ticks)
         },
         grid: {
             display: false // Keep vertical grid lines hidden
         }
      }
    },
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

      <div className="pollution-chart-container">
        {pollutionData && availablePollutants.length > 0 ? (
            <Bar options={chartOptions} data={chartData} />
        ) : (
            <div className="no-chart-data">
                {pollutionData ? 'No pollutant data to display.' : 'Select a location on the map to see details.'}
            </div>
        )}
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