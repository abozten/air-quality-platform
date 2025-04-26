// frontend/src/components/HeatmapLayer.jsx
import { useEffect, useRef, useState } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';

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
  const [zoom, setZoom]    = useState(map.getZoom());

  /* ----- listen for zoom changes ---------------------------------- */
  useMapEvents({
    zoomend: () => setZoom(map.getZoom())
  });

  /* ----- once: create the two layers ------------------------------ */
  useEffect(() => {
    heatLayerRef.current    = L.heatLayer([], { minOpacity: 0.4 }).addTo(map);
    noDataLayerRef.current  = L.heatLayer([], { minOpacity: 0.3 }).addTo(map);

    return () => {
      map.removeLayer(heatLayerRef.current);
      map.removeLayer(noDataLayerRef.current);
    };
  }, [map]);

  /* ----- update data every time zoom / points / parameter change -- */
  useEffect(() => {
    if (!heatLayerRef.current) return;

    const gSize     = getGridSize(zoom);
    const bounds    = map.getBounds();
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
    const noDataPts  = [];
    const maxInt     = getMaxIntensity(selectedParam);

    Object.values(cells).forEach(c => {
      if (c.cnt > 0) {
        const avg = c.tot / c.cnt;
        const intensity = Math.min(1, c.cnt / 10) * avg;
        heatPts.push([c.lat, c.lng, intensity]);
      } else {
        noDataPts.push([c.lat, c.lng, 0.5]);
      }
    });

    /* --- push data into the two layers ---------------------------- */
    heatLayerRef.current.setOptions({
      radius: 20, blur: 15, maxZoom: 11, max: maxInt,
      gradient: {
        0.3: '#2c3e50', 0.5: '#3498db', 0.7: '#2ecc71',
        0.8: '#f1c40f', 1.0: '#e74c3c'
      }
    });
    heatLayerRef.current.setLatLngs(heatPts);

    noDataLayerRef.current.setOptions({
      radius: 20, blur: 15, maxZoom: 11, max: 1,
      gradient: {
        0.0: 'rgba(30,144,255,0)',
        0.1: 'rgba(30,144,255,0.2)',
        0.5: 'rgba(30,144,255,0.4)',
        1.0: 'rgba(30,144,255,0.6)',
      }
    });
    noDataLayerRef.current.setLatLngs(noDataPts);
  }, [zoom, points, selectedParam, map]);

  return null;
};

export default HeatmapLayer;