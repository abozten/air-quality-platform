import React, { useEffect, useRef } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  TimeSeriesScale
} from 'chart.js';
import 'chartjs-adapter-date-fns';
import './PollutionChart.css';

// Register necessary Chart.js components including TimeScale
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  TimeSeriesScale
);

// Mapping for display names and units
const POLLUTANT_NAMES = {
    pm25: 'PM 2.5',
    no2: 'NO₂',
    o3: 'O₃',
    pm10: 'PM 10',
    so2: 'SO₂',
    co: 'CO',
};
const POLLUTANT_UNITS = 'µg/m³';

// Define colors for line charts
const POLLUTANT_COLORS = {
  pm25: 'rgba(138, 43, 226, 0.8)', // Purple
  no2: 'rgba(76, 175, 80, 0.8)',  // Green
  o3: 'rgba(255, 193, 7, 0.8)',   // Amber
  pm10: 'rgba(255, 99, 132, 0.8)', // Pink/Red
  so2: 'rgba(54, 162, 235, 0.8)', // Blue
  co: 'rgba(153, 102, 255, 0.8)', // Indigo
};

const LocationHistoryChart = ({ historyData, parameter, geohash }) => {
  const chartRef = useRef(null);
  
  // Debug logging to verify data
  useEffect(() => {
    console.log(`Chart for ${parameter} received data:`, historyData);
  }, [historyData, parameter]);

  if (!historyData || historyData.length === 0) {
    return <div className="no-chart-data">No history data for {POLLUTANT_NAMES[parameter] || parameter}.</div>;
  }

  // Make sure all data points have properly formatted timestamps
  const validData = historyData.filter(point => 
    point && point.timestamp && !isNaN(new Date(point.timestamp).getTime()) && 
    typeof point.value === 'number'
  );

  if (validData.length === 0) {
    return <div className="no-chart-data">Invalid data format for {POLLUTANT_NAMES[parameter] || parameter} history.</div>;
  }

  // Sort data by timestamp to ensure proper visualization
  const sortedData = [...validData].sort((a, b) => 
    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const chartLabels = sortedData.map(point => new Date(point.timestamp));
  const chartValues = sortedData.map(point => point.value);
  const color = POLLUTANT_COLORS[parameter] || 'rgba(201, 203, 207, 0.8)';

  const chartData = {
    labels: chartLabels,
    datasets: [
      {
        label: `${POLLUTANT_NAMES[parameter] || parameter} (${POLLUTANT_UNITS})`,
        data: chartValues,
        borderColor: color,
        backgroundColor: color.replace('0.8', '0.3'),
        tension: 0.1,
        pointRadius: 2,
        pointHoverRadius: 4,
        fill: true,
        parsing: false, // For performance when working with timestamps directly
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          color: '#ccc'
        }
      },
      title: {
        display: true,
        text: `${POLLUTANT_NAMES[parameter] || parameter} Trend for ${geohash}`,
        color: '#eee',
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
        type: 'time',
        time: {
          unit: 'hour',
          tooltipFormat: 'PPpp', // More precise format for tooltip
          displayFormats: {
            hour: 'HH:mm'
          }
        },
        title: {
          display: true,
          text: 'Time',
          color: '#ccc'
        },
        ticks: {
          color: '#ccc',
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 6
        },
        grid: {
          display: false,
        },
      }
    },
    animation: {
      duration: 800 // Smoother animation
    }
  };

  return (
    <div className="location-history-chart-container" style={{ height: '250px', width: '100%', position: 'relative', display: 'block', marginBottom: '20px' }}>
      <Line ref={chartRef} options={chartOptions} data={chartData} />
    </div>
  );
};

export default LocationHistoryChart;
