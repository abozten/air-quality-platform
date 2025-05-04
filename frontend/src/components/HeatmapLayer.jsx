// frontend/src/components/HeatmapLayer.jsx
import { useEffect, useRef, useState } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';

// Add custom canvas setup function to set willReadFrequently attribute
// Still potentially useful for performance even without complex reads.
const createCustomHeatLayer = (options) => {
  const heatLayer = L.heatLayer([], options); // Start with empty data

  // Override the _initCanvas method to set willReadFrequently
  const originalInitCanvas = heatLayer._initCanvas;
  heatLayer._initCanvas = function() {
    originalInitCanvas.call(this);
    if (this._canvas) {
      // Standard way to get context without triggering warnings
      const ctx = this._canvas.getContext('2d', { willReadFrequently: true });
      // Note: Setting the attribute directly might also work but getContext is preferred
      // if (ctx && typeof this._canvas.setAttribute === 'function') {
      //  this._canvas.setAttribute('willReadFrequently', 'true');
      //}
    }
  };

  return heatLayer;
};

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */
// Define maximum expected values for normalization (adjust as needed)
const getMaxIntensity = param => {
  switch (param) {
    case 'pm10': return 150; // Higher typical max for PM10
    case 'no2' : return 100; // Increased slightly
    case 'so2' : return 60;  // Increased slightly
    case 'o3'  : return 180; // Higher typical max for O3
    case 'pm25':
    default    : return 100; // Increased max for PM2.5 for better gradient spread
  }
};

// Define base radius and blur, potentially adjust by zoom later if needed
const BASE_RADIUS = 80; // Increased significantly for global spread
const BASE_BLUR = 60;  // Increased significantly for smoother look

/* ------------------------------------------------------------------ */
/* Component                                                          */
/* ------------------------------------------------------------------ */
const HeatmapLayer = ({ points = [], selectedParam = 'pm25' }) => {
  const map = useMap();
  const heatLayerRef = useRef(null);
  const [mapReady, setMapReady] = useState(!!map); // Initialize based on map existence

  /* ----- listen map load event ------------------------------------ */
  useMapEvents({
    load: () => {
      console.log("Heatmap: Map loaded event received.");
      setMapReady(true);
    },
    // Optional: Can listen to zoom to adjust radius/blur later
     zoomend: () => { /* update radius/blur based on map.getZoom() */ }
  });

  /* ----- once: create the layer ----------------------------------- */
  useEffect(() => {
    // Guard against map not being ready yet
    if (!map) {
      console.log("Heatmap: Map not available on initial effect.");
      return;
    }
     if (!mapReady) {
       console.log("Heatmap: Map not ready on initial effect.");
       return; // Explicitly wait for mapReady state
     }

    console.log("Heatmap: Creating heatmap layer.");
    // Use our custom function to create heat layers
    heatLayerRef.current = createCustomHeatLayer({
      minOpacity: 0.3, // Start slightly visible
      radius: BASE_RADIUS,
      blur: BASE_BLUR,
      maxZoom: 18, // Adjust as needed
      max: 1.0,    // Intensity will be normalized between 0 and 1
       gradient: { // Example gradient (adjust colors for desired look)
          0.0: 'rgba(0, 0, 255, 0)', // Fully transparent blue start
          0.1: 'blue',
          0.2: 'cyan',
          0.4: 'lime',
          0.6: 'yellow',
          0.8: 'orange',
          1.0: 'red'
        }
    }).addTo(map);


    return () => {
       console.log("Heatmap: Cleaning up heatmap layer.");
      if (heatLayerRef.current && map.hasLayer(heatLayerRef.current)) {
         map.removeLayer(heatLayerRef.current);
         heatLayerRef.current = null; // Clear ref on cleanup
      }
    };
  }, [map, mapReady]); // Depend on map instance and mapReady state

  /* ----- update data when points / parameter change --------------- */
  useEffect(() => {
    // Ensure map and layer are ready
    if (!map || !heatLayerRef.current || !mapReady) {
       console.log(`Heatmap: Skipping update (Map: ${!!map}, Layer: ${!!heatLayerRef.current}, Ready: ${mapReady})`);
       return;
    }

    console.log(`Heatmap: Updating with ${points.length} points for param ${selectedParam}`);

    try {
      // The backend provides aggregated points (AggregatedAirQualityPoint)
      // We need the average value for the selected parameter.
      const valueKey = `avg_${selectedParam}`;
      const maxIntensity = getMaxIntensity(selectedParam);

      const heatPoints = points
        .map(p => {
          const value = p[valueKey];

          // Basic validation for required fields
          if (value == null || isNaN(value) || p.latitude == null || p.longitude == null) {
            // console.warn("Skipping point due to missing data:", p);
            return null; // Skip points with missing essential data
          }

          // Normalize intensity: value relative to maxIntensity, clamped between 0 and 1
          const intensity = Math.min(Math.max(value / maxIntensity, 0), 1.0);

          // Return leaflet.heat compatible array: [lat, lng, intensity]
          return [p.latitude, p.longitude, intensity];
        })
        .filter(p => p !== null); // Filter out skipped points

      console.log(`Heatmap: Processed ${heatPoints.length} valid points for rendering.`);

      // Update the heatmap layer's data
      heatLayerRef.current.setLatLngs(heatPoints);

      // Optional: Adjust radius/blur based on current zoom?
      // const currentZoom = map.getZoom();
      // const radius = calculateRadiusForZoom(currentZoom); // Implement this function if needed
      // const blur = calculateBlurForZoom(currentZoom); // Implement this function if needed
      // heatLayerRef.current.setOptions({ radius, blur });


    } catch (error) {
      console.error('Error updating heatmap layer:', error);
    }
  }, [points, selectedParam, map, heatLayerRef.current, mapReady]); // Add mapReady dependency


  return null; // This component only adds a layer to the map
};

export default HeatmapLayer;