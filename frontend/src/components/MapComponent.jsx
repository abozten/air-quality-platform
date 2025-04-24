// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Tooltip, ZoomControl } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat';

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

// Component to display anomaly markers
const AnomalyMarkers = ({ anomalies }) => {
  if (!anomalies || anomalies.length === 0) return null;
  
  return (
    <>
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
    </>
  );
};

// Heatmap Layer Component
const HeatmapLayer = ({ points, selectedParam }) => {
  const map = useMap();
  const heatLayerRef = useRef(null);

  useEffect(() => {
    if (!map) return;

    // Filter points and extract data based on selectedParam
    const heatPoints = points
      .filter(p => 
        p.latitude != null && 
        p.longitude != null && 
        p[`avg_${selectedParam}`] != null && 
        !isNaN(p[`avg_${selectedParam}`])
      )
      .map(p => [p.latitude, p.longitude, p[`avg_${selectedParam}`]]);

    if (heatPoints.length === 0) {
      // Remove layer if no valid points
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
        heatLayerRef.current = null;
      }
      return;
    }

    // Define dynamic max intensity based on parameter
    let maxIntensity;
    switch (selectedParam) {
      case 'pm10': maxIntensity = 100.0; break;
      case 'no2': maxIntensity = 80.0; break;
      case 'so2': maxIntensity = 40.0; break;
      case 'o3': maxIntensity = 150.0; break;
      case 'pm25': 
      default: maxIntensity = 50.0; break;
    }

    // Configure heatmap options - adjusted for dark mode
    const heatOptions = {
      radius: 20,
      blur: 15,
      maxZoom: 11,
      max: maxIntensity,
      gradient: {
        0.3: '#2c3e50',
        0.5: '#3498db',
        0.7: '#2ecc71',
        0.8: '#f1c40f',
        1.0: '#e74c3c'
      }
    };

    // Add or update the layer
    if (heatLayerRef.current) {
      heatLayerRef.current.setLatLngs(heatPoints);
      heatLayerRef.current.setOptions(heatOptions);
    } else {
      heatLayerRef.current = L.heatLayer(heatPoints, heatOptions);
      heatLayerRef.current.addTo(map);
    }

    // Cleanup
    return () => {
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
        heatLayerRef.current = null;
      }
    };
  }, [map, points, selectedParam]);

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

// Main MapComponent
const MapComponent = ({ points = [], anomalies = [], selectedParam = 'pm25' }) => {
  const initialPosition = [20, 0];
  const initialZoom = 2;

  return (
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
      <HeatmapLayer points={points} selectedParam={selectedParam} />
      <AnomalyMarkers anomalies={anomalies} />
      <MapStyleCustomization />
      <ZoomControl position="bottomright" />
    </MapContainer>
  );
};

export default MapComponent;
