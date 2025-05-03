// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Tooltip, ZoomControl, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat'; // Provides L.heatLayer
import MarkerClusterGroup from 'react-leaflet-markercluster'; // Import MarkerClusterGroup
import 'leaflet.markercluster/dist/MarkerCluster.css'; // Import MarkerCluster CSS
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'; // Import MarkerCluster Default CSS
import * as api from '../services/api'; // Use updated api service
import HeatmapLayer from './HeatmapLayer'; // Use updated HeatmapLayer
import { debounce } from 'lodash'; // Import debounce

// Fix for default marker icons issue with webpack/vite
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: iconRetinaUrl,
  iconUrl: iconUrl,
  shadowUrl: shadowUrl,
});

// Custom alert icon using Font Awesome (ensure Font Awesome is included in your project)
const alertIcon = L.divIcon({
  className: 'alert-marker', // Add custom class for styling if needed
  html: '<i class="fas fa-exclamation-triangle" style="color: red; font-size: 20px;"></i>', // Inline style for simplicity
  iconSize: [24, 24], // Size of the icon
  iconAnchor: [12, 24], // Point of the icon which will correspond to marker's location
  popupAnchor: [0, -24] // Point from which the popup should open relative to the iconAnchor
});

// ========================================================================
// Sub-component: AnomalyMarkers
// ========================================================================
const AnomalyMarkers = ({ anomalies }) => {
  if (!anomalies || anomalies.length === 0) {
    console.log("AnomalyMarkers: No anomalies to display.");
    return null;
  }
  console.log(`AnomalyMarkers: Rendering ${anomalies.length} anomalies.`);

  return (
    // Using MarkerClusterGroup to handle large numbers of markers
    <MarkerClusterGroup
      chunkedLoading // Helps performance with many markers
      maxClusterRadius={60} // Adjust clustering radius (pixels)
      // Other options: spiderfyOnMaxZoom={true}, showCoverageOnHover={false}
    >
      {anomalies.map(anomaly => (
        <Marker
          key={anomaly.id} // Use unique anomaly ID as key
          position={[anomaly.latitude, anomaly.longitude]}
          icon={alertIcon} // Use the custom alert icon
        >
          {/* Tooltip shown on hover */}
          <Tooltip permanent={false} direction="top" offset={[0, -20]}>
            <div>
              <strong>{anomaly.parameter ? anomaly.parameter.toUpperCase() : 'Anomaly'} Alert</strong><br/>
              {anomaly.description || 'No description available.'}<br/>
              Value: {typeof anomaly.value === 'number' ? anomaly.value.toFixed(1) : 'N/A'}
            </div>
          </Tooltip>
        </Marker>
      ))}
    </MarkerClusterGroup>
  );
};


// ========================================================================
// Sub-component: MapClickHandler
// Handles clicks on the map, fetches data, shows popup, calls callback
// ========================================================================
const MapClickHandler = ({ selectedParam, onLocationDataLoaded }) => {
  const popupRef = useRef(null); // To manage the popup instance

  // Create loading popup content dynamically
  const createLoadingPopup = () => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup popup-loading'; // Add base and specific class
    div.innerHTML = `
      <div>Loading air quality data...</div>
      <div class="popup-loader"></div>
    `;
    return div;
  };

  // Create error popup content dynamically
  const createErrorPopup = (lat, lng) => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup popup-error'; // Add base and specific class
    div.innerHTML = `
      <strong>No data available</strong>
      <div class="popup-location">
        <small>Lat: ${lat.toFixed(4)}, Lon: ${lng.toFixed(4)}</small>
      </div>
    `;
    return div;
  };

  // Create popup content based on the data point and selected parameter
  const createPopupContent = (point, selectedParam, lat, lng) => {
    const div = document.createElement('div');
    div.className = 'air-quality-popup'; // Base class

    // Parameter display name mapping
    const paramNames = { pm25: 'PM₂.₅', pm10: 'PM₁₀', no2: 'NO₂', so2: 'SO₂', o3: 'O₃' };
    const paramUnits = { pm25: 'µg/m³', pm10: 'µg/m³', no2: 'µg/m³', so2: 'µg/m³', o3: 'µg/m³' };

    // Header with selected parameter name
    const header = document.createElement('div');
    header.className = 'popup-header';
    header.innerHTML = `<strong>${paramNames[selectedParam] || selectedParam.toUpperCase()}</strong>`;
    div.appendChild(header);

    // If no data point found by API
    if (!point) {
      const noData = document.createElement('div');
      noData.className = 'popup-value';
      noData.innerHTML = 'N/A';
      div.appendChild(noData);
    } else {
      // Display the value for the selected parameter
      const valueDiv = document.createElement('div');
      valueDiv.className = 'popup-value';
      const paramValue = point[selectedParam];
      valueDiv.innerHTML = (paramValue !== null && paramValue !== undefined)
        ? `${paramValue.toFixed(2)} <span class="popup-unit">${paramUnits[selectedParam] || ''}</span>`
        : 'N/A';
      div.appendChild(valueDiv);

      // Display location from the fetched point
      const location = document.createElement('div');
      location.className = 'popup-location';
      location.innerHTML = `<small>Lat: ${point.latitude?.toFixed(4)}, Lon: ${point.longitude?.toFixed(4)}</small>`;
      div.appendChild(location);

      // Display other available parameters
      const otherParamsDiv = document.createElement('div');
      otherParamsDiv.className = 'popup-other-params';
      let otherParamsHtml = '<hr style="margin: 5px 0;"><small>';
      let hasOtherData = false;
      Object.keys(paramNames).forEach(param => {
        if (param !== selectedParam && point[param] !== null && point[param] !== undefined) {
          hasOtherData = true;
          otherParamsHtml += `${paramNames[param]}: ${point[param].toFixed(1)} ${paramUnits[param]}<br>`;
        }
      });
      otherParamsHtml += '</small>';
      if (hasOtherData) {
        otherParamsDiv.innerHTML = otherParamsHtml;
        div.appendChild(otherParamsDiv);
      }
    }

    // Always show clicked coordinates if no point data
     if (!point) {
        const clickedLocation = document.createElement('div');
        clickedLocation.className = 'popup-location';
        clickedLocation.innerHTML = `<small>Clicked: ${lat.toFixed(4)}, ${lng.toFixed(4)}</small>`;
        div.appendChild(clickedLocation);
    }


    return div;
  };

  // Hook to handle map click events
  const map = useMapEvents({
    click: async (e) => {
      const { lat, lng } = e.latlng;
      console.log(`MapClick: Clicked at ${lat.toFixed(4)}, ${lng.toFixed(4)}`);

      // Close existing popup if any
      if (popupRef.current) {
        popupRef.current.remove();
      }

      // Create and open loading popup
      popupRef.current = L.popup({ closeButton: true, minWidth: 150 })
        .setLatLng([lat, lng])
        .setContent(createLoadingPopup())
        .openOn(map);

      try {
        const zoom = map.getZoom(); // Get current zoom for the API call
        console.log(`MapClick: Fetching for ${lat.toFixed(4)},${lng.toFixed(4)} at zoom ${zoom}`);
        const data = await api.fetchAirQualityForLocation(lat, lng, zoom); // Fetch specific data
        console.log(`MapClick: Received data:`, data);

        // Update popup content with fetched data or error message
        if (popupRef.current) {
            popupRef.current.setContent(createPopupContent(data, selectedParam, lat, lng));
        }

        // Call the callback function passed from parent (App.jsx)
        if (onLocationDataLoaded) {
          onLocationDataLoaded(data); // Pass fetched data (can be null) upwards
        }

      } catch (error) {
        console.error('MapClick: Error fetching location data:', error);
        // Update popup to show error
        if (popupRef.current) {
            popupRef.current.setContent(createErrorPopup(lat, lng));
        }
         // Call callback with null on error
         if (onLocationDataLoaded) {
          onLocationDataLoaded(null);
        }
      }
    }
  });

  // Effect to add dynamic CSS for the popup styling
  useEffect(() => {
    const styleId = 'air-quality-popup-styles';
    if (document.getElementById(styleId)) return; // Style already added

    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      .air-quality-popup { padding: 8px; line-height: 1.4; }
      .popup-header { font-size: 1.0em; font-weight: bold; margin-bottom: 4px; text-align: center; border-bottom: 1px solid #555; padding-bottom: 4px;}
      .popup-value { font-size: 1.6em; font-weight: bold; color: #fff; margin: 4px 0; text-align: center;}
      .popup-unit { font-size: 0.6em; opacity: 0.8; }
      .popup-location { color: #bbb; font-size: 0.75em; margin-top: 4px; text-align: center;}
      .popup-other-params { text-align: left; color: #ccc; margin-top: 8px; font-size: 0.8em; border-top: 1px solid #555; padding-top: 6px; }
      .popup-other-params small { line-height: 1.5; }
      .popup-loading { text-align: center; padding: 15px; color: #ddd; }
      .popup-loader { border: 4px solid rgba(255,255,255,0.2); border-top: 4px solid #3498db; border-radius: 50%; width: 25px; height: 25px; animation: spin 1s linear infinite; margin: 10px auto 0; }
      .popup-error { text-align: center; color: #ff8a8a; padding: 10px; }
      .popup-error strong { font-size: 1.1em; display: block; margin-bottom: 5px; }
      @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      .leaflet-popup-content-wrapper { background: rgba(40, 44, 52, 0.85); color: #ffffff; border-radius: 5px; box-shadow: 0 3px 14px rgba(0,0,0,0.4); backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px); border: 1px solid rgba(255, 255, 255, 0.1);}
      .leaflet-popup-tip { background: rgba(40, 44, 52, 0.85); }
      .leaflet-popup-close-button { color: #aaa !important; padding: 4px 4px 0 0 !important; border: none !important; background: transparent !important; }
      .leaflet-popup-close-button:hover { color: #fff !important; }
    `;
    document.head.appendChild(style);

    // Cleanup function to remove the style when the component unmounts
    return () => {
      const existingStyle = document.getElementById(styleId);
      if (existingStyle) {
        document.head.removeChild(existingStyle);
      }
    };
  }, []); // Run only once on mount

  // Effect for cleaning up the popup instance when the component unmounts
  useEffect(() => {
    return () => {
      if (popupRef.current) {
        popupRef.current.remove();
        popupRef.current = null;
      }
    };
  }, []);

  return null; // This component does not render any direct UI elements
};


// ========================================================================
// Sub-component: MapStyleCustomization
// Applies dark mode class and styles controls
// ========================================================================
const MapStyleCustomization = () => {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    // Apply dark mode styling to the map container
    const container = map.getContainer();
    if (!container.classList.contains('dark-mode-map')) {
        container.classList.add('dark-mode-map');
    }

    // Style Zoom controls
    const zoomControl = container.querySelector('.leaflet-control-zoom');
    if (zoomControl) {
      zoomControl.style.opacity = '0.8';
      zoomControl.style.border = '1px solid rgba(255, 255, 255, 0.2)';
      zoomControl.style.background = 'rgba(40, 44, 52, 0.7)';
      const links = zoomControl.querySelectorAll('a');
      links.forEach(link => {
          link.style.color = '#ccc';
          link.style.background = 'transparent';
          link.style.borderBottom = '1px solid rgba(255, 255, 255, 0.2)';
      });
       links[links.length-1].style.borderBottom = 'none'; // remove border from last link
    }

    // Style Attribution control
    const attribution = container.querySelector('.leaflet-control-attribution');
    if (attribution) {
      attribution.style.opacity = '0.6';
      attribution.style.background = 'rgba(0, 0, 0, 0.6)';
      attribution.style.color = '#aaa';
      attribution.style.padding = '2px 5px';
      attribution.style.fontSize = '10px';
      attribution.style.borderRadius = '3px';
    }
    // Cleanup function optional, styles likely persist fine
  }, [map]);

  return null; // Component doesn't render anything
};


// ========================================================================
// Sub-component: MapInteractionHandler
// Listens to map move/zoom events and triggers debounced data fetch
// ========================================================================
const MapInteractionHandler = ({ onMapIdle }) => {
  const map = useMap();

  // Create a debounced version of the idle handler
  // Waits 750ms after the last move/zoom event before calling onMapIdle
  const debouncedIdleHandler = useCallback(
    debounce(() => {
      if (!map) return;
      console.log("MapInteractionHandler: Map idle event triggered.");
      const bounds = map.getBounds();
      const zoom = map.getZoom();
      onMapIdle(bounds, zoom); // Call the callback passed from parent
    }, 750), // Adjust debounce delay (milliseconds) as needed
    [map, onMapIdle] // Dependencies for useCallback
  );

  // Hook to register map event listeners
  useMapEvents({
    // 'moveend' covers both panning and zooming finishes
    moveend: debouncedIdleHandler,
    // 'load' triggers fetch on initial map load
    load: () => {
        console.log("MapInteractionHandler: Map loaded, initial fetch trigger.");
        // Use timeout to ensure map state (bounds, zoom) is stable after load
        setTimeout(debouncedIdleHandler, 100);
    },
  });

  // Effect to cancel any pending debounced calls on unmount
   useEffect(() => {
    return () => {
      console.log("MapInteractionHandler: Cancelling debounced call on unmount.");
      debouncedIdleHandler.cancel();
    };
  }, [debouncedIdleHandler]);


  return null; // Component doesn't render anything
};


// ========================================================================
// Main MapComponent
// ========================================================================
const MapComponent = ({
    anomalies = [],       // Array of anomaly objects
    selectedParam = 'pm25', // Currently selected parameter for heatmap/popup focus
    onLocationSelect    // Callback function: (data) => void - Called with data from map click
}) => {
  const initialPosition = [20, 0]; // Initial map center (latitude, longitude)
  const initialZoom = 3;           // Initial map zoom level

  // State for the heatmap data points
  const [heatmapPoints, setHeatmapPoints] = useState([]);
  // State for loading indicator during heatmap data fetch
  const [isLoading, setIsLoading] = useState(false);
  // State for storing errors during heatmap data fetch
  const [error, setError] = useState(null);

  // Callback function triggered by MapInteractionHandler when map becomes idle
  const handleMapIdle = useCallback(async (bounds, zoom) => {
    if (!bounds) {
        console.warn("handleMapIdle: Invalid bounds received.");
        return;
    }

    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();

    // Validate bounds (basic check)
    if (!ne || !sw || Math.abs(ne.lat) > 90 || Math.abs(sw.lat) > 90 ) {
        console.warn("handleMapIdle: Invalid bounds detected after check, skipping fetch.", {ne, sw});
        setError("Invalid map bounds.");
        return;
    }

    console.log(`handleMapIdle: Fetching heatmap data for bounds: SW(${sw.lat.toFixed(4)}, ${sw.lng.toFixed(4)}) NE(${ne.lat.toFixed(4)}, ${ne.lng.toFixed(4)}), Zoom: ${zoom}`);
    setIsLoading(true);
    setError(null); // Clear previous errors

    try {
      // Call the API to fetch aggregated data for the current view
      const data = await api.fetchHeatmapData(
        sw.lat, ne.lat, sw.lng, ne.lng, zoom, '1h' // Using 1h window for heatmap
      );
      console.log(`handleMapIdle: Received ${data.length} aggregated points.`);
      setHeatmapPoints(data || []); // Ensure state is always an array
       if (!data || data.length === 0) {
            // Optional: show message or just log if no data
            console.log("handleMapIdle: No heatmap data returned from API for current view.")
       }
    } catch (err) {
      console.error("handleMapIdle: Failed to fetch heatmap data:", err);
      setError(err.message || "Failed to load heatmap data");
      setHeatmapPoints([]); // Clear data on error
    } finally {
      setIsLoading(false);
    }
  }, []); // useCallback dependencies are empty as it defines the function based on imports


  // JSX rendering the map and its layers/controls
  return (
    <>
      {/* Loading Indicator */}
      {isLoading && (
        <div className="map-loading-indicator">
          Loading Map Data...
        </div>
      )}
      {/* Error Indicator */}
       {error && (
        <div className="map-error-indicator">
          Error: {error}
        </div>
      )}

      {/* Leaflet Map Container */}
      <MapContainer
        center={initialPosition}
        zoom={initialZoom}
        minZoom={3} // Set a minimum zoom level
        style={{ height: '100%', width: '100%' }} // Make map fill its container
        worldCopyJump={true} // Prevents map from repeating infinitely when panning horizontally
        zoomControl={false} // Disable default zoom control to reposition it
      >
        {/* Base Tile Layer (Dark Mode) */}
        <TileLayer
          attribution='© <a href="https://stadiamaps.com/" target="_blank" rel="noopener">Stadia Maps</a>, © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
          url="https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png"
          maxZoom={18} // Set max zoom for tile layer
        />

        {/* Component to handle map interactions (pan/zoom) and trigger data fetch */}
        <MapInteractionHandler onMapIdle={handleMapIdle} />

        {/* Heatmap Layer: Displays aggregated data visually */}
        <HeatmapLayer points={heatmapPoints} selectedParam={selectedParam} />

        {/* Anomaly Markers Layer: Displays clustered markers for detected anomalies */}
        <AnomalyMarkers anomalies={anomalies} />

        {/* Component to apply custom map styling */}
        <MapStyleCustomization />

        {/* Repositioned Zoom Control */}
        <ZoomControl position="bottomright" />

        {/* Component to handle clicks directly on the map */}
        <MapClickHandler
            selectedParam={selectedParam}
            onLocationDataLoaded={onLocationSelect} // Pass the callback down
        />
      </MapContainer>
    </>
  );
};



export default MapComponent;