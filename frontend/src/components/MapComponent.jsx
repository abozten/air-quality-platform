// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Tooltip, ZoomControl, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat';
import MarkerClusterGroup from 'react-leaflet-markercluster'; // Import MarkerClusterGroup
import 'leaflet.markercluster/dist/MarkerCluster.css'; // Import MarkerCluster CSS
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'; // Import MarkerCluster Default CSS
import * as api from '../services/api';
import HeatmapLayer from './HeatmapLayer';

// Fix for default marker icons
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: iconRetinaUrl, iconUrl: iconUrl, shadowUrl: shadowUrl,
});

// Custom alert icon
const alertIcon = L.divIcon({
  className: 'alert-marker',
  html: '<i class="fas fa-exclamation-triangle"></i>',
  iconSize: [24, 24],
  iconAnchor: [12, 24],
});

// Component to display anomaly markers within a cluster group
const AnomalyMarkers = ({ anomalies }) => {
  if (!anomalies || anomalies.length === 0) return null;

  return (
    <MarkerClusterGroup
      // Options for MarkerClusterGroup can be added here if needed
      // e.g., maxClusterRadius={50} // Adjust clustering radius (pixels)
    >
      {anomalies.map(anomaly => (
        <Marker
          key={anomaly.id}
          position={[anomaly.latitude, anomaly.longitude]}
          icon={alertIcon}
        >
          <Tooltip permanent={false} direction="top">
            <div>
              <strong>{anomaly.parameter.toUpperCase()} Alert</strong><br/>
              {anomaly.description}<br/>
              Value: {anomaly.value.toFixed(1)}
            </div>
          </Tooltip>
        </Marker>
      ))}
    </MarkerClusterGroup>
  );
};

// Air Quality Click Menu Component
const MapClickHandler = ({ selectedParam, points }) => {
  const [clickPosition, setClickPosition] = useState(null);
  const [airQualityInfo, setAirQualityInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const popupRef = useRef(null);
  
  const map = useMapEvents({
    click: async (e) => {
      const { lat, lng } = e.latlng;
      setClickPosition([lat, lng]);
      
      // Show loading popup
      if (popupRef.current) {
        popupRef.current.remove();
      }
      
      popupRef.current = L.popup()
        .setLatLng([lat, lng])
        .setContent(createLoadingPopup())
        .openOn(map);
      
      setIsLoading(true);
      
      try {
        // Fetch air quality data from API for the clicked location with current zoom level
        const data = await api.fetchAirQualityForLocation(lat, lng, map.getZoom());
        setAirQualityInfo(data);
        
        // Update popup with the fetched data
        if (popupRef.current) {
          popupRef.current.setContent(createPopupContent(data, selectedParam, lat, lng));
        }
      } catch (error) {
        console.error('Error fetching location data:', error);
        // Show error popup
        if (popupRef.current) {
          popupRef.current.setContent(createErrorPopup(lat, lng));
        }
      } finally {
        setIsLoading(false);
      }
    }
  });
  
  // Create loading popup content
  const createLoadingPopup = () => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup';
    div.innerHTML = `
      <div class="popup-loading">
        <div>Loading air quality data...</div>
        <div class="popup-loader"></div>
      </div>
    `;
    return div;
  };
  
  // Create error popup content
  const createErrorPopup = (lat, lng) => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup';
    div.innerHTML = `
      <div class="popup-error">
        <strong>No data available</strong>
        <div class="popup-location">
          <small>Lat: ${lat.toFixed(4)}, Lon: ${lng.toFixed(4)}</small>
        </div>
      </div>
    `;
    return div;
  };
  
  // Create popup content based on the data point and selected parameter
  const createPopupContent = (point, selectedParam, lat, lng) => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup';
    
    // Parameter display name mapping
    const paramNames = {
      'pm25': 'PM₂.₅',
      'pm10': 'PM₁₀',
      'no2': 'NO₂',
      'so2': 'SO₂',
      'o3': 'O₃'
    };
    
    // Parameter units
    const paramUnits = {
      'pm25': 'μg/m³',
      'pm10': 'μg/m³',
      'no2': 'μg/m³',
      'so2': 'μg/m³',
      'o3': 'μg/m³'
    };
    
    // Header with selected parameter
    const header = document.createElement('div');
    header.className = 'popup-header';
    header.innerHTML = `<strong>${paramNames[selectedParam] || selectedParam.toUpperCase()}</strong>`;
    div.appendChild(header);
    
    // If no data available
    if (!point) {
      const noData = document.createElement('div');
      noData.className = 'popup-value';
      noData.innerHTML = 'N/A';
      div.appendChild(noData);
      
      // Location
      const location = document.createElement('div');
      location.className = 'popup-location';
      location.innerHTML = `<small>Lat: ${lat.toFixed(4)}, Lon: ${lng.toFixed(4)}</small>`;
      div.appendChild(location);
      
      return div;
    }
    
    // Value with units
    const value = document.createElement('div');
    value.className = 'popup-value';
    const paramValue = point[selectedParam];
    if (paramValue !== null && paramValue !== undefined) {
      value.innerHTML = `${paramValue.toFixed(2)} ${paramUnits[selectedParam]}`;
    } else {
      value.innerHTML = 'N/A';
    }
    div.appendChild(value);
    
    // Location
    const location = document.createElement('div');
    location.className = 'popup-location';
    location.innerHTML = `<small>Lat: ${point.latitude.toFixed(4)}, Lon: ${point.longitude.toFixed(4)}</small>`;
    div.appendChild(location);
    
    // Add other parameters if available
    const otherParams = document.createElement('div');
    otherParams.className = 'popup-other-params';
    
    let otherParamsHtml = '<hr style="margin: 5px 0;"><small>';
    let hasOtherData = false;
    
    Object.keys(paramNames).forEach(param => {
      if (param !== selectedParam) {
        const otherValue = point[param];
        
        if (otherValue !== null && otherValue !== undefined) {
          hasOtherData = true;
          otherParamsHtml += `${paramNames[param]}: ${otherValue.toFixed(1)} ${paramUnits[param]}<br>`;
        }
      }
    });
    
    otherParamsHtml += '</small>';
    
    if (hasOtherData) {
      otherParams.innerHTML = otherParamsHtml;
      div.appendChild(otherParams);
    }
    
    return div;
  };
  
  // Add custom styles for the popup
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      .air-quality-popup {
        min-width: 150px;
        text-align: center;
        padding: 5px 0;
      }
      .popup-header {
        font-size: 14px;
        margin-bottom: 2px;
      }
      .popup-value {
        font-size: 22px;
        font-weight: bold;
        color: #fff;
        margin: 2px 0;
      }
      .popup-location {
        color: #aaa;
        font-size: 10px;
        margin-top: 2px;
      }
      .popup-other-params {
        text-align: left;
        color: #bbb;
        margin-top: 5px;
      }
      .popup-loading {
        text-align: center;
        padding: 10px;
        color: #ddd;
      }
      .popup-loader {
        border: 3px solid rgba(255,255,255,0.2);
        border-top: 3px solid #3498db;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        animation: spin 1s linear infinite;
        margin: 8px auto 0;
      }
      .popup-error {
        color: #e74c3c;
        padding: 5px;
      }
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
      .leaflet-popup-content-wrapper {
        background: rgba(40, 44, 52, 0.9);
        color: #ffffff;
        border-radius: 4px;
        box-shadow: 0 3px 14px rgba(0,0,0,0.4);
      }
      .leaflet-popup-tip {
        background: rgba(40, 44, 52, 0.9);
      }
      .leaflet-popup-close-button {
        color: #aaa;
      }
    `;
    document.head.appendChild(style);
    
    return () => {
      document.head.removeChild(style);
    };
  }, []);
  
  // Clean up popup on unmount
  useEffect(() => {
    return () => {
      if (popupRef.current) {
        popupRef.current.remove();
      }
    };
  }, []);

  return null;
};


// Map style customization component
const MapStyleCustomization = () => {
  const map = useMap();
  
  useEffect(() => {
    // Apply dark mode styling to the map
    map.getContainer().classList.add('dark-mode-map');
    
    // Reduce zoom controls opacity for minimalist look
    const zoomControl = document.querySelector('.leaflet-control-zoom');
    if (zoomControl) {
      zoomControl.style.opacity = '0.7';
    }
    
    // Reduce attribution opacity
    const attribution = document.querySelector('.leaflet-control-attribution');
    if (attribution) {
      attribution.style.opacity = '0.5';
      attribution.style.background = 'rgba(0, 0, 0, 0.5)';
      attribution.style.color = '#aaa';
      attribution.style.padding = '2px 5px';
      attribution.style.fontSize = '9px';
    }
  }, [map]);
  
  return null;
};

// Component to track zoom level and update data accordingly
const ZoomHandler = ({ onZoomChange }) => {
  const map = useMapEvents({
    zoomend: () => {
      const currentZoom = map.getZoom();
      onZoomChange(currentZoom);
    }
  });
  
  return null;
};

// Main MapComponent
const MapComponent = ({ points = [], anomalies = [], selectedParam = 'pm25', onDataUpdate }) => {
  const initialPosition = [20, 0];
  const initialZoom = 2;
  const [currentPoints, setCurrentPoints] = useState(points);
  const [isLoading, setIsLoading] = useState(false);
  const [currentZoom, setCurrentZoom] = useState(initialZoom);
  
  // Update current points when prop points change
  useEffect(() => {
    setCurrentPoints(points);
  }, [points]);
  
  // Handle zoom change
  const handleZoomChange = async (newZoom) => {
    // Only fetch new data if the zoom level meaningfully changed
    // (i.e., crossed a threshold that would result in a different geohash precision)
    const oldPrecision = api.zoomToGeohashPrecision(currentZoom);
    const newPrecision = api.zoomToGeohashPrecision(newZoom);
    
    setCurrentZoom(newZoom);
    
    if (oldPrecision !== newPrecision && onDataUpdate) {
      setIsLoading(true);
      try {
        // Request data at the new zoom level
        const newData = await api.fetchAirQualityPoints(200, newZoom);
        setCurrentPoints(newData);
        if (onDataUpdate) {
          onDataUpdate(newData);
        }
      } catch (err) {
        console.error("Failed to fetch data for new zoom level:", err);
      } finally {
        setIsLoading(false);
      }
    }
  };
  
  return (
    <>
      {isLoading && (
        <div style={{
          position: 'absolute',
          top: 10,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 1000,
          background: 'rgba(40,44,52,0.9)',
          color: '#fff',
          padding: '8px 16px',
          borderRadius: '4px',
          fontSize: '16px'
        }}>
          Loading...
        </div>
      )}
      <MapContainer 
        center={initialPosition} 
        zoom={initialZoom} 
        style={{ height: '70vh', width: '100%' }}
        worldCopyJump={true}
        zoomControl={false} // Disable default zoom control to reposition it
      >
        {/* Dark mode tile layer */}
        <TileLayer
          attribution='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a>'
          url="https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png"
        />
        <ZoomHandler onZoomChange={handleZoomChange} />
        <HeatmapLayer points={currentPoints} selectedParam={selectedParam} />
        <AnomalyMarkers anomalies={anomalies} />
        <MapClickHandler selectedParam={selectedParam} points={currentPoints} />
        <MapStyleCustomization />
        <ZoomControl position="bottomright" />
      </MapContainer>
    </>
  );
};

export default MapComponent;
