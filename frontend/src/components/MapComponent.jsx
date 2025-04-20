// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
// Import the heatmap plugin AFTER Leaflet
import 'leaflet.heat'; // This imports the JS and expects L to be global

// --- Icon Fix (Still needed if you add markers back later) ---
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: iconRetinaUrl, iconUrl: iconUrl, shadowUrl: shadowUrl,
});
// --- End Icon Fix ---


// Internal component to handle the heatmap layer logic
const HeatmapLayer = ({ points }) => {
    const map = useMap(); // Get the map instance from the parent MapContainer
    const heatLayerRef = useRef(null); // Ref to store the heatmap layer

    useEffect(() => {
        // Ensure map instance exists
        if (!map) return;

        // 1. Format data for leaflet.heat: array of [lat, lng, intensity]
        // We'll use pm10 as intensity. Filter out points without valid pm10 data.
        const heatPoints = points
            .filter(p => p.latitude != null && p.longitude != null && p.pm10 != null && !isNaN(p.pm10))
            .map(p => [p.latitude, p.longitude, p.pm10]);

        // If no valid points, potentially remove existing layer or do nothing
        if (heatPoints.length === 0) {
             if (heatLayerRef.current) {
                map.removeLayer(heatLayerRef.current);
                heatLayerRef.current = null;
             }
             return;
        }

        // 2. Configure heatmap options
        const heatOptions = {
            radius: 25,         // Radius of each point's influence
            blur: 15,           // Amount of blur
            maxZoom: 18,        // Zoom level where heatmap disappears
            max: 50.0,          // Max intensity value (adjust based on expected PM2.5 range)
            gradient: {         // Color gradient (0.0 = transparent, 1.0 = max color)
                0.4: 'blue',    // ~20 µg/m³
                0.6: 'cyan',    // ~30 µg/m³
                0.7: 'lime',    // ~35 µg/m³
                0.8: 'yellow',  // ~40 µg/m³
                1.0: 'red'      // >=50 µg/m³ (or your defined max)
            }
        };

        // 3. Add or update the heatmap layer
        if (heatLayerRef.current) {
            // If layer exists, update its data and options
            heatLayerRef.current.setLatLngs(heatPoints);
            heatLayerRef.current.setOptions(heatOptions);
        } else {
            // If layer doesn't exist, create it and add to map
            heatLayerRef.current = L.heatLayer(heatPoints, heatOptions);
            heatLayerRef.current.addTo(map);
        }

        // 4. Cleanup function: Remove layer when component unmounts or points change drastically
        // This cleanup function runs before the next useEffect runs or when the component unmounts
        return () => {
            if (heatLayerRef.current) {
                map.removeLayer(heatLayerRef.current);
                heatLayerRef.current = null; // Clear the ref
            }
        };

    }, [map, points]); // Re-run effect if map instance or points data changes

    return null; // This component doesn't render anything itself
};


// Main Map Component
const MapComponent = ({ points = [] }) => { // Removed onMarkerClick/onMapClick for now
    const initialPosition = [20, 0];
    const initialZoom = 3;

    return (
        <MapContainer center={initialPosition} zoom={initialZoom} style={{ height: '70vh', width: '100%' }}>
            <TileLayer
                attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* Render the HeatmapLayer component, passing the points data */}
            <HeatmapLayer points={points} />

            {/* Markers removed for now to show heatmap clearly */}
            {/* {points.map((point, index) => (
                <Marker key={index} position={[point.latitude, point.longitude]}>
                    <Popup>{`PM2.5: ${point.pm10 ?? 'N/A'}`}</Popup>
                </Marker>
            ))} */}

        </MapContainer>
    );
};

export default MapComponent;