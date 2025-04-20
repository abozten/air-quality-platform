// frontend/src/components/MapComponent.jsx
import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat';

import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: iconRetinaUrl, iconUrl: iconUrl, shadowUrl: shadowUrl,
});



const HeatmapLayer = ({ points, selectedParam }) => { // Added selectedParam prop
    const map = useMap();
    const heatLayerRef = useRef(null);

    useEffect(() => {
        if (!map) return;

        // 1. Filter points and extract data based on selectedParam
        const heatPoints = points
            .filter(p =>
                p.latitude != null &&
                p.longitude != null &&
                p[selectedParam] != null && // Check the selected parameter
                !isNaN(p[selectedParam])     // Ensure it's a number
            )
            .map(p => [p.latitude, p.longitude, p[selectedParam]]); // Use selectedParam value

        if (heatPoints.length === 0) {
            // Remove layer if no valid points for the selected param
            if (heatLayerRef.current) {
                map.removeLayer(heatLayerRef.current);
                heatLayerRef.current = null;
            }
            return;
        }

        // 2. Define dynamic max intensity based on parameter
        let maxIntensity;
        switch (selectedParam) {
            case 'pm10': maxIntensity = 100.0; break;
            case 'no2': maxIntensity = 80.0; break;
            case 'so2': maxIntensity = 40.0; break;
            case 'o3': maxIntensity = 150.0; break;
            case 'pm25': // fallthrough intentional
            default: maxIntensity = 50.0; break; // Default for PM2.5
        }

        // 3. Configure heatmap options dynamically
        const heatOptions = {
            radius: 20, // Slightly smaller radius might look better with more points
            blur: 15,
            maxZoom: 18,
            max: maxIntensity, // Use dynamic max intensity
            gradient: { // Keep or adjust gradient as needed
                0.4: 'blue',
                0.6: 'cyan',
                0.7: 'lime',
                0.8: 'yellow',
                1.0: 'red'
            }
        };

        // 4. Add or update the layer
        if (heatLayerRef.current) {
            heatLayerRef.current.setLatLngs(heatPoints); // Update data
            heatLayerRef.current.setOptions(heatOptions); // Update options (like max intensity)
        } else {
            heatLayerRef.current = L.heatLayer(heatPoints, heatOptions);
            heatLayerRef.current.addTo(map);
        }

        // 5. Cleanup
        return () => {
            if (heatLayerRef.current) {
                map.removeLayer(heatLayerRef.current);
                heatLayerRef.current = null;
            }
        };
        // ****************************************
        // Add selectedParam to dependency array
    }, [map, points, selectedParam]);
    // ****************************************

    return null;
};

// Accept selectedParam and pass it down
const MapComponent = ({ points = [], selectedParam }) => {
    const initialPosition = [20, 0];
    const initialZoom = 3;

    return (
        <MapContainer center={initialPosition} zoom={initialZoom} style={{ height: '70vh', width: '100%' }}>
            <TileLayer
                attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {/* Pass selectedParam to HeatmapLayer */}
            <HeatmapLayer points={points} selectedParam={selectedParam} />
        </MapContainer>
    );
};

export default MapComponent;
