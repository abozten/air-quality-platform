// frontend/src/components/MapComponent.jsx
import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';

// --- Icon Fix ---
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: iconRetinaUrl, iconUrl: iconUrl, shadowUrl: shadowUrl,
});
// --- End Icon Fix ---

// Helper to format popup content
const formatPopupContent = (point) => {
    return `
        <b>Location:</b> (${point.latitude.toFixed(2)}, ${point.longitude.toFixed(2)})<br/>
        <b>PM2.5:</b> ${point.pm25 ?? 'N/A'} µg/m³<br/>
        <b>PM10:</b> ${point.pm10 ?? 'N/A'} µg/m³<br/>
        <b>NO₂:</b> ${point.no2 ?? 'N/A'} µg/m³<br/>
        <b>SO₂:</b> ${point.so2 ?? 'N/A'} µg/m³<br/>
        <b>O₃:</b> ${point.o3 ?? 'N/A'} µg/m³<br/>
        <b>Time:</b> ${new Date(point.timestamp).toLocaleString()}
    `;
};

// Component to handle map clicks (optional, for future use)
const LocationMarker = ({ onMapClick }) => {
    useMapEvents({
        click(e) {
            onMapClick(e.latlng); // Pass coordinates back up
        },
    });
    return null; // Doesn't render anything visible
};


const MapComponent = ({ points = [], onMarkerClick, onMapClick }) => {
  const initialPosition = [20, 0]; // Center map more globally
  const initialZoom = 3;

  const handleMarkerClick = (point) => {
    if(onMarkerClick) {
        onMarkerClick(point); // Pass the clicked point's data
    }
  }

  return (
    <MapContainer center={initialPosition} zoom={initialZoom} style={{ height: '60vh', width: '100%' }}>
      <TileLayer
        attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
       {/* <LocationMarker onMapClick={onMapClick} /> */} {/* Enable if you want map click events */}

      {points.map((point, index) => (
        <Marker
            key={index} // Use a more stable key if available (e.g., point.id)
            position={[point.latitude, point.longitude]}
            eventHandlers={{
                click: () => handleMarkerClick(point),
            }}
        >
          <Popup>{formatPopupContent(point)}</Popup>
        </Marker>
      ))}
      {/* Heatmap layer or anomaly markers will be added here later */}
    </MapContainer>
  );
};

export default MapComponent;