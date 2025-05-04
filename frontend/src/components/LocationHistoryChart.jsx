import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, // Keep for time scale if using 'category' type
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale, // Import TimeScale
  TimeSeriesScale // Import TimeSeriesScale
} from 'chart.js';
import 'chartjs-adapter-date-fns'; // Import the date adapter
import './PollutionChart.css'; // Reuse or create new CSS

// Register necessary Chart.js components including TimeScale
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale, // Register TimeScale
  TimeSeriesScale // Register TimeSeriesScale
);

// Mapping for display names and units (reuse from PollutionChart or define here)
const POLLUTANT_NAMES = {
    pm25: 'PM 2.5',
    no2: 'NO₂',
    o3: 'O₃',
    pm10: 'PM 10',
    so2: 'SO₂',
    co: 'CO',
};
const POLLUTANT_UNITS = 'µg/m³'; // Assuming same unit for simplicity

// Define colors (reuse from PollutionChart or define specific line colors)
const POLLUTANT_COLORS = {
  pm25: 'rgba(138, 43, 226, 0.8)', // Purple
  no2: 'rgba(76, 175, 80, 0.8)',  // Green
  o3: 'rgba(255, 193, 7, 0.8)',   // Amber
  pm10: 'rgba(255, 99, 132, 0.8)', // Pink/Red
  so2: 'rgba(54, 162, 235, 0.8)', // Blue
  co: 'rgba(153, 102, 255, 0.8)', // Indigo
};

const LocationHistoryChart = ({ historyData, parameter, geohash }) => {
  if (!historyData || historyData.length === 0) {
    return <div className="no-chart-data">No history data for {POLLUTANT_NAMES[parameter] || parameter}.</div>;
  }

  const chartLabels = historyData.map(point => new Date(point.timestamp)); // Use Date objects for time scale
  const chartValues = historyData.map(point => point.value);
  const color = POLLUTANT_COLORS[parameter] || 'rgba(201, 203, 207, 0.8)'; // Default grey

  const chartData = {
    labels: chartLabels, // Use Date objects as labels
    datasets: [
      {
        label: `${POLLUTANT_NAMES[parameter] || parameter} (${POLLUTANT_UNITS})`,
        data: chartValues,
        borderColor: color,
        backgroundColor: color.replace('0.8', '0.3'), // Lighter fill
        tension: 0.1, // Slight curve to the line
        pointRadius: 2, // Smaller points
        pointHoverRadius: 4,
        fill: true,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true, // Show legend for line charts
        position: 'top',
         labels: {
             color: '#ccc' // Legend text color
         }
      },
      title: {
        display: true,
        text: `${POLLUTANT_NAMES[parameter] || parameter} Trend for ${geohash}`,
        color: '#eee', // Title color
        font: {
            size: 14
        }
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        titleColor: '#fff',
        bodyColor: '#fff',
        callbacks: {
          label: function(context) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            if (context.parsed.y !== null) {
              label += context.parsed.y.toFixed(1) + ` ${POLLUTANT_UNITS}`;
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
          text: `Concentration (${POLLUTANT_UNITS})`,
          color: '#ccc',
        },
        ticks: {
          color: '#ccc',
        },
        grid: {
          color: 'rgba(204, 204, 204, 0.2)',
        },
      },
      x: {
        type: 'time', // Set scale type to 'time'
        time: {
          unit: 'hour', // Adjust based on data range (e.g., 'minute', 'day')
          tooltipFormat: 'PPp', // Format for tooltip (e.g., 'May 5, 2025, 1:30 PM')
          displayFormats: {
             hour: 'HH:mm' // Format for axis labels (e.g., '14:00')
          }
        },
        title: {
            display: true,
            text: 'Time',
            color: '#ccc'
        },
        ticks: {
          color: '#ccc',
          maxRotation: 0, // Prevent label rotation
          autoSkip: true, // Automatically skip labels to prevent overlap
          maxTicksLimit: 6 // Limit the number of ticks shown
        },
        grid: {
          display: false,
        },
      }
    },
  };

  return (
    <div className="location-history-chart-container">
      <Line options={chartOptions} data={chartData} />
    </div>
  );
};

export default LocationHistoryChart;
