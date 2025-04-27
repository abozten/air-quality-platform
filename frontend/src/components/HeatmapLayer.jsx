// frontend/src/components/HeatmapLayer.jsx
import { useEffect, useRef, useState } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';

// Add custom canvas setup function to set willReadFrequently attribute
const createCustomHeatLayer = (options) => {
  const originalHeatLayer = L.heatLayer([], options);
  
  // Override the _initCanvas method to set willReadFrequently
  const originalInitCanvas = originalHeatLayer._initCanvas;
  originalHeatLayer._initCanvas = function() {
    originalInitCanvas.call(this);
    if (this._canvas) {
      const ctx = this._canvas.getContext('2d');
      if (ctx && typeof ctx.canvas.setAttribute === 'function') {
        ctx.canvas.setAttribute('willReadFrequently', 'true');
      }
    }
  };
  
  return originalHeatLayer;
};

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */
const getGridSize = z =>
  z <= 3 ? 0.5 :
  z <= 5 ? 0.2 :
  z <= 7 ? 0.1 :
  z <= 9 ? 0.05 :
  z <= 11 ? 0.02 : 0.01;

const getMaxIntensity = param => {
  switch (param) {
    case 'pm10': return 100;
    case 'no2' : return 80;
    case 'so2' : return 40;
    case 'o3'  : return 150;
    default    : return 50; // pm25
  }
};

/* ------------------------------------------------------------------ */
/* Component                                                          */
/* ------------------------------------------------------------------ */
const HeatmapLayer = ({ points, selectedParam }) => {
  const map                = useMap();
  const heatLayerRef       = useRef(null);
  const noDataLayerRef     = useRef(null);
  const [zoom, setZoom]    = useState(map ? map.getZoom() : 10); // Add null check
  const [mapReady, setMapReady] = useState(false); // Track if map is ready

  /* ----- listen for zoom changes ---------------------------------- */
  useMapEvents({
    zoomend: () => {
      if (map) setZoom(map.getZoom());
    },
    load: () => {
      setMapReady(true);
    }
  });

  /* ----- once: create the two layers ------------------------------ */
  useEffect(() => {
    // Only add layers when map is available
    if (!map) return;
    
    // Use our custom function to create heat layers with willReadFrequently set to true
    heatLayerRef.current = createCustomHeatLayer({ minOpacity: 0.4 }).addTo(map);
    noDataLayerRef.current = createCustomHeatLayer({ minOpacity: 0.3 }).addTo(map);

    setMapReady(true);

    return () => {
      if (heatLayerRef.current && map) map.removeLayer(heatLayerRef.current);
      if (noDataLayerRef.current && map) map.removeLayer(noDataLayerRef.current);
    };
  }, [map]);

  /* ----- update data every time zoom / points / parameter change -- */
  useEffect(() => {
    // Make sure map and layers are ready
    if (!map || !heatLayerRef.current || !mapReady) return;
    
    try {
      const bounds = map.getBounds();
      if (!bounds) return; // If bounds aren't available yet, skip this update
      
      const gSize     = getGridSize(zoom);
      const minLat    = bounds.getSouth();
      const maxLat    = bounds.getNorth();
      const minLng    = bounds.getWest();
      const maxLng    = bounds.getEast();

      /* --- build a hash of visible grid cells ----------------------- */
      const cells = Object.create(null);
      for (let lat = Math.floor(minLat / gSize) * gSize; lat <= maxLat; lat += gSize) {
        for (let lng = Math.floor(minLng / gSize) * gSize; lng <= maxLng; lng += gSize) {
          const key     = `${lat.toFixed(4)}_${lng.toFixed(4)}`;
          cells[key]    = { lat: lat + gSize / 2, lng: lng + gSize / 2,
                            tot: 0, cnt: 0       };
        }
      }

      /* --- aggregate measurement points into those cells ------------ */
      const valueKey = `avg_${selectedParam}`;
      for (const p of points) {
        const v = p[valueKey];
        if (v == null || isNaN(v)) continue;

        const cLat  = Math.floor(p.latitude  / gSize) * gSize;
        const cLng  = Math.floor(p.longitude / gSize) * gSize;
        const cKey  = `${cLat.toFixed(4)}_${cLng.toFixed(4)}`;

        if (!cells[cKey]) continue;            // outside current bounds
        cells[cKey].tot += v;
        cells[cKey].cnt += 1;
      }

      /* --- split into “real” data & “no-data placeholders” ---------- */
      const heatPts    = [];
      const maxInt     = getMaxIntensity(selectedParam);

      Object.values(cells).forEach(c => {
        if (c.cnt > 0) {
          const avg = c.tot / c.cnt;
          // Use average directly for intensity, capped by maxInt
          const intensity = Math.min(avg / maxInt, 1.0);
          heatPts.push([c.lat, c.lng, intensity]);
        }
      });

      /* --- push data into the two layers ---------------------------- */
      heatLayerRef.current.setOptions({
        // Increase radius and blur significantly for a smoother, more spread-out look
        radius: 60, 
        blur: 50, 
        maxZoom: 18, // Allow heatmap effect at higher zooms if desired
        max: 1.0, // Intensity is now normalized between 0 and 1
        // Adjusted gradient for a smoother transition and different color scheme
        gradient: {
          0.0: 'rgba(0, 119, 190, 0.2)',  // Lighter Blue, slightly transparent start
          0.2: '#00a8a8', // Teal
          0.4: '#60c060', // Green
          0.6: '#f0e040', // Yellow
          0.8: '#f08000', // Orange
          1.0: '#e00000'  // Red
        }
      });
      heatLayerRef.current.setLatLngs(heatPts);

      // Ensure noDataLayer remains empty/invisible
      if (noDataLayerRef.current) {
        noDataLayerRef.current.setLatLngs([]);
      }
    } catch (error) {
      console.error('Error updating heatmap layer:', error);
    }
  }, [zoom, points, selectedParam, map, mapReady]);

  return null;
};

export default HeatmapLayer;