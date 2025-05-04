// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Tooltip, ZoomControl, useMapEvents, Rectangle } from 'react-leaflet'; // Added Rectangle
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat'; // Provides L.heatLayer
import MarkerClusterGroup from 'react-leaflet-markercluster'; // Import MarkerClusterGroup
import 'leaflet.markercluster/dist/MarkerCluster.css'; // Import MarkerCluster CSS
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'; // Import MarkerCluster Default CSS
import * as api from '../services/api'; // Use updated api service
import HeatmapLayer from './HeatmapLayer'; // Use updated HeatmapLayer
import { debounce } from 'lodash'; // Import debounce
import './MapComponent.css'; // Import the CSS file

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
// Sub-component: AreaSelectorHandler
// Handles drawing a rectangle for area selection and fetching density data
// ========================================================================
const AreaSelectorHandler = ({ onBoundsSelected, isEnabled }) => { // Added isEnabled prop
  const map = useMap();
  const [startPos, setStartPos] = useState(null);
  const [endPos, setEndPos] = useState(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const selectionRectangleRef = useRef(null);

  const handleMouseDown = (e) => {
    // Only start selection if the mode is enabled
    if (!isEnabled) return;

    // Prevent interfering with map drag
    map.dragging.disable();
    setStartPos(e.latlng);
    setEndPos(e.latlng); // Initialize endPos
    setIsSelecting(true);
    console.log("AreaSelect: Mouse Down", e.latlng);

    // Remove previous rectangle if exists
    if (selectionRectangleRef.current) {
      map.removeLayer(selectionRectangleRef.current);
      selectionRectangleRef.current = null;
    }
  };

  const handleMouseMove = (e) => {
    // Only track mouse if selecting
    if (!isSelecting || !isEnabled) return;
    setEndPos(e.latlng);

    // Draw/update rectangle
    if (selectionRectangleRef.current) {
      selectionRectangleRef.current.setBounds(L.latLngBounds(startPos, e.latlng));
    } else {
      selectionRectangleRef.current = L.rectangle(L.latLngBounds(startPos, e.latlng), {
        color: "#3388ff",
        weight: 1,
        fillOpacity: 0.2,
      }).addTo(map);
    }
  };

  const handleMouseUp = (e) => {
    // Only finish selection if selecting
    if (!isSelecting || !isEnabled) return;

    map.dragging.enable(); // Re-enable map drag
    setIsSelecting(false);
    console.log("AreaSelect: Mouse Up", e.latlng);

    // Ensure startPos and endPos are valid
    if (!startPos || !endPos) {
        console.warn("AreaSelect: Invalid start or end position on mouse up.");
        if (selectionRectangleRef.current) {
            map.removeLayer(selectionRectangleRef.current);
            selectionRectangleRef.current = null;
        }
        setStartPos(null);
        setEndPos(null);
        return;
    }

    const bounds = L.latLngBounds(startPos, endPos);

    // Check if the area is reasonably large (prevent accidental tiny selections)
    const southWest = bounds.getSouthWest();
    const northEast = bounds.getNorthEast();
    const areaThreshold = 0.001; // Adjust as needed (degrees squared)
    if (Math.abs(northEast.lat - southWest.lat) * Math.abs(northEast.lng - southWest.lng) < areaThreshold) {
        console.log("AreaSelect: Selection too small, treating as click.");
        if (selectionRectangleRef.current) {
            map.removeLayer(selectionRectangleRef.current);
            selectionRectangleRef.current = null;
        }
        setStartPos(null);
        setEndPos(null);
        // Don't call onBoundsSelected for small selections
        return;
    }

    console.log("AreaSelect: Bounds selected", bounds);
    onBoundsSelected(bounds);

    // Reset positions for next selection
    setStartPos(null);
    setEndPos(null);
  };

  useMapEvents({
    mousedown: handleMouseDown,
    mousemove: handleMouseMove,
    mouseup: handleMouseUp,
  });

  // Cleanup rectangle on unmount or if mode is disabled during selection
  useEffect(() => {
    return () => {
      if (selectionRectangleRef.current) {
        map.removeLayer(selectionRectangleRef.current);
        selectionRectangleRef.current = null;
      }
      // Ensure dragging is enabled if component unmounts or mode changes mid-drag
      if (isSelecting) {
          map.dragging.enable();
          setIsSelecting(false);
          setStartPos(null);
          setEndPos(null);
      }
    };
  }, [map, isSelecting, isEnabled]); // Add isEnabled to dependencies

  // Change cursor style when selection mode is active
  useEffect(() => {
    const mapContainer = map.getContainer();
    if (isEnabled) {
      mapContainer.style.cursor = 'crosshair';
    } else {
      mapContainer.style.cursor = ''; // Reset to default
    }
    // Cleanup cursor style on unmount or when isEnabled changes
    return () => {
        mapContainer.style.cursor = '';
    };
  }, [map, isEnabled]);

  return null; // This component doesn't render anything itself
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

  // State for Area Selection / Density Data
  const [isAreaSelectionMode, setIsAreaSelectionMode] = useState(false); // State for toggling mode
  const [selectedBounds, setSelectedBounds] = useState(null);
  const [densityData, setDensityData] = useState(null);
  const [isDensityLoading, setIsDensityLoading] = useState(false);
  const [densityError, setDensityError] = useState(null);
  const densityRectangleRef = useRef(null); // Ref to keep track of the displayed density rectangle
  const mapRef = useRef(); // Ref for the MapContainer instance

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

  // Callback function for AreaSelectorHandler
  const handleBoundsSelected = useCallback((bounds) => {
    console.log("MapComponent: Received selected bounds", bounds);
    setSelectedBounds(bounds);
    setDensityData(null); // Clear previous density data
    setDensityError(null); // Clear previous errors

    // Remove the previous density rectangle if it exists
    if (densityRectangleRef.current && mapRef.current) {
        try {
            mapRef.current.removeLayer(densityRectangleRef.current);
        } catch (e) {
            console.warn("Could not remove previous density rectangle:", e);
        }
        densityRectangleRef.current = null;
    }

    // Draw the final selected rectangle and store its reference
    if (mapRef.current) {
        densityRectangleRef.current = L.rectangle(bounds, {
            color: "#ff7800", // Different color for final selection
            weight: 2,
            fillOpacity: 0.1,
            dashArray: '5, 5' // Dashed line
        }).addTo(mapRef.current);
    }

    // IMPORTANT: Turn off selection mode after a successful selection
    setIsAreaSelectionMode(false);

  }, [mapRef]); // Dependency on mapRef

  // Effect to fetch density data when selectedBounds changes
  useEffect(() => {
    if (!selectedBounds) {
      return;
    }

    const fetchDensity = async () => {
      setIsDensityLoading(true);
      setDensityError(null);
      const ne = selectedBounds.getNorthEast();
      const sw = selectedBounds.getSouthWest();

      console.log(`MapComponent: Fetching density for SW(${sw.lat.toFixed(4)}, ${sw.lng.toFixed(4)}) NE(${ne.lat.toFixed(4)}, ${ne.lng.toFixed(4)})`);

      try {
        const data = await api.fetchPollutionDensity(sw.lat, ne.lat, sw.lng, ne.lng);
        console.log("MapComponent: Received density data:", data);
        setDensityData(data);
      } catch (err) {
        console.error("MapComponent: Failed to fetch density data:", err);
        setDensityError(err.message || "Failed to load density data");
        setDensityData(null); // Clear data on error
      } finally {
        setIsDensityLoading(false);
      }
    };

    fetchDensity();

  }, [selectedBounds]);

  // Effect to add dynamic CSS for the density display and toggle button
  useEffect(() => {
    const styleId = 'density-display-styles';
    if (document.getElementById(styleId)) return; // Style already added

    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      .density-display-panel {
        position: absolute;
        bottom: 40px; /* Adjust as needed, above zoom controls */
        left: 10px;
        background: rgba(40, 44, 52, 0.85);
        color: #fff;
        padding: 8px 12px;
        border-radius: 5px;
        z-index: 1000; /* Ensure it's above map layers */
        font-size: 0.9em;
        max-width: 250px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        backdrop-filter: blur(3px);
        -webkit-backdrop-filter: blur(3px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        line-height: 1.5;
      }
      .density-display-panel h4 {
        margin: 0 0 5px 0;
        font-size: 1.1em;
        border-bottom: 1px solid #555;
        padding-bottom: 3px;
      }
       .density-display-panel .loading,
       .density-display-panel .error {
         font-style: italic;
         color: #aaa;
       }
       .density-display-panel .error {
         color: #ff8a8a;
       }
       .density-display-panel .param-value {
         margin-left: 5px;
       }
       .density-display-panel .param-unit {
         font-size: 0.8em;
         opacity: 0.7;
         margin-left: 2px;
       }
       .density-display-panel .data-count {
         margin-top: 5px;
         font-size: 0.9em;
         color: #ccc;
         border-top: 1px dashed #555;
         padding-top: 5px;
       }

      .area-select-toggle-button {
        position: absolute;
        top: 80px; /* Position below other controls */
        left: 10px;
        z-index: 1000;
        padding: 6px 10px;
        font-size: 12px;
        background-color: rgba(40, 44, 52, 0.7);
        color: #ccc;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        cursor: pointer;
        opacity: 0.8;
        transition: background-color 0.2s ease, opacity 0.2s ease;
      }
      .area-select-toggle-button:hover {
        background-color: rgba(60, 64, 72, 0.8);
        opacity: 1;
      }
      .area-select-toggle-button.active {
        background-color: #3498db;
        color: white;
        border-color: rgba(255, 255, 255, 0.4);
        opacity: 1;
      }
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

  // Function to toggle area selection mode
  const toggleAreaSelectionMode = () => {
    setIsAreaSelectionMode(prev => !prev);
    // Clear previous selection results when toggling mode
    setSelectedBounds(null);
    setDensityData(null);
    setDensityError(null);
    // Remove the density rectangle if it exists
    if (densityRectangleRef.current && mapRef.current) {
        try {
            mapRef.current.removeLayer(densityRectangleRef.current);
        } catch (e) {
             console.warn("Could not remove density rectangle on toggle:", e);
        }
        densityRectangleRef.current = null;
    }
  };

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

      {/* Area Selection Toggle Button */}
      <button
        className={`area-select-toggle-button ${isAreaSelectionMode ? 'active' : ''}`}
        onClick={toggleAreaSelectionMode}
        title={isAreaSelectionMode ? "Disable Area Selection" : "Enable Area Selection (Drag on Map)"}
      >
        {isAreaSelectionMode ? 'Selecting Area' : 'Select Area'}
      </button>

      {/* Leaflet Map Container */}
      <MapContainer
        ref={mapRef} // Assign ref to MapContainer
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

        {/* Component to handle area selection - pass isEnabled state */}
        <AreaSelectorHandler
            onBoundsSelected={handleBoundsSelected}
            isEnabled={isAreaSelectionMode}
        />

      </MapContainer>

      {/* Density Display Panel - Show only when bounds are selected or loading/error occurs */}
      {(selectedBounds || isDensityLoading || densityError) && (
        <div className="density-display-panel">
          <h4>Area Density</h4>
          {isDensityLoading && <div className="loading">Loading density data...</div>}
          {densityError && <div className="error">Error: {densityError}</div>}
          {!isDensityLoading && !densityError && densityData && densityData.count > 0 && (
            <div>
              {/* Display average values - adjust parameters as needed based on API response */}
              {Object.entries(densityData.average_values || {}).map(([param, value]) => (
                <div key={param}>
                  <strong>{param.toUpperCase()}:</strong>
                  <span className="param-value">{value !== null ? value.toFixed(2) : 'N/A'}</span>
                  {/* Add units if available/needed */}
                  {/* <span className="param-unit">µg/m³</span> */}
                </div>
              ))}
              <div className="data-count">
                Based on {densityData.count || 0} data points.
              </div>
            </div>
          )}
          {!isDensityLoading && !densityError && (!densityData || densityData.count === 0) && (
            <div className="no-data">No density data available for the selected area.</div>
          )}
        </div>
      )}
    </>
  );
};

export default MapComponent;