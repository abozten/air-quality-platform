// frontend/src/components/AnomalyPanel.jsx
import React, { useEffect, useState, useRef } from 'react';
import { API_BASE_URL } from '../services/api'; // Import API_BASE_URL

const AnomalyPanel = ({ anomalies = [], isLoading, error }) => {
  // State to store all anomalies including live updates
  const [allAnomalies, setAllAnomalies] = useState(anomalies);
  // State to track if we received any new anomalies in real-time
  const [hasNewAnomalies, setHasNewAnomalies] = useState(false);
  // Reference to the WebSocket connection
  const wsRef = useRef(null);
  // Reference to the animation timeout
  const animationTimeoutRef = useRef(null);
  // State to track connection status
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  // State to count WebSocket messages for debugging
  const [messageCount, setMessageCount] = useState(0);
  
  // Update allAnomalies when the prop changes (initial load)
  useEffect(() => {
    // Sort anomalies by timestamp (descending) before setting state
    const sortedAnomalies = [...anomalies].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    setAllAnomalies(sortedAnomalies);
  }, [anomalies]);
  
  // Set up WebSocket connection for real-time anomalies
  useEffect(() => {
    // Use API_BASE_URL but convert http to ws or https to wss
    const getWebSocketUrl = () => {
      let wsBaseUrl = API_BASE_URL;
      if (wsBaseUrl.startsWith('http:')) {
        wsBaseUrl = wsBaseUrl.replace('http:', 'ws:');
      } else if (wsBaseUrl.startsWith('https:')) {
        wsBaseUrl = wsBaseUrl.replace('https:', 'wss:');
      }
      return `${wsBaseUrl}/ws/anomalies`;
    };
    
    const connectWebSocket = () => {
      try {
        // Create WebSocket connection with explicit URL
        const wsUrl = getWebSocketUrl();
        console.log('DEBUG: Connecting to WebSocket:', wsUrl);
        
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
          console.log('DEBUG: WebSocket connection established for anomaly notifications');
          setConnectionStatus('connected');
          
          // Send initial message to test the connection
          try {
            ws.send("ping");
            console.log('DEBUG: Sent ping message to server');
          } catch (error) {
            console.error('DEBUG: Error sending ping message:', error);
          }
        };
        
        ws.onmessage = (event) => {
          // Log raw data first
          console.log('DEBUG: Raw WebSocket message received:', event.data); 
          setMessageCount(prev => prev + 1);
          
          try {
            // Check if data is a string before parsing
            if (typeof event.data !== 'string') {
              console.warn('DEBUG: Received non-string WebSocket message:', event.data);
              return; // Skip processing if not a string
            }

            // Parse the incoming message
            const data = JSON.parse(event.data);
            console.log('DEBUG: Parsed WebSocket data:', data);
            
            // Handle connection status messages or pings/pongs
            if (data.type === 'connection_status' || data.type === 'pong' || event.data === 'pong') { // Also check raw data for simple 'pong'
              console.log('DEBUG: Received status/pong message:', data.type || event.data);
              return;
            }
            
            // Process anomaly data - log all properties to help debugging
            console.log('DEBUG: Anomaly properties:', Object.keys(data));

            // Ensure the anomaly has an ID before proceeding
            if (!data.id) {
              console.warn('DEBUG: Received anomaly without an ID, skipping:', data);
              return;
            }
            
            // Add the anomaly to our state and re-sort
            setAllAnomalies(prev => {
              // Skip if this anomaly already exists
              if (prev.some(a => a.id === data.id)) {
                console.log(`DEBUG: Duplicate anomaly detected (ID: ${data.id}), skipping`);
                return prev;
              }
              
              console.log(`DEBUG: Adding new anomaly (ID: ${data.id}) and re-sorting`);
              // Add new anomaly and sort the entire list by timestamp (descending)
              const updatedAnomalies = [data, ...prev];
              updatedAnomalies.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
              return updatedAnomalies;
            });
            
            // Set flag to highlight the new anomaly
            setHasNewAnomalies(true);
            
            // Reset the highlight after a few seconds
            if (animationTimeoutRef.current) {
              clearTimeout(animationTimeoutRef.current);
            }
            animationTimeoutRef.current = setTimeout(() => {
              setHasNewAnomalies(false);
            }, 5000);
          } catch (e) {
            // Log the error and the raw data that caused it
            console.error('DEBUG: Error processing WebSocket message:', e);
            console.error('DEBUG: Raw data causing error:', event.data); 
          }
        };
        
        ws.onerror = (error) => {
          console.error('DEBUG: WebSocket error:', error);
          setConnectionStatus('error');
        };
        
        ws.onclose = (event) => {
          console.log('DEBUG: WebSocket connection closed:', event.code, event.reason);
          setConnectionStatus('disconnected');
          
          // Try to reconnect after a short delay
          setTimeout(() => {
            if (wsRef.current === ws) {
              console.log('DEBUG: Attempting to reconnect WebSocket...');
              connectWebSocket();
            }
          }, 3000);
        };
        
        // Store the WebSocket reference
        wsRef.current = ws;
      } catch (error) {
        console.error('DEBUG: Failed to create WebSocket connection:', error);
        setConnectionStatus('error');
      }
    };
    
    // Initialize the connection
    connectWebSocket();
    
    // Clean up WebSocket on unmount
    return () => {
      if (wsRef.current) {
        console.log('DEBUG: Closing WebSocket connection on component unmount');
        wsRef.current.close();
        wsRef.current = null;
      }
      if (animationTimeoutRef.current) {
        clearTimeout(animationTimeoutRef.current);
      }
    };
  }, []);
  
  return (
    <div className={`anomaly-panel ${hasNewAnomalies ? 'has-new-anomaly' : ''}`}>
      <div className="panel-header">
        <h3>
          Anomaly Alerts 
          {hasNewAnomalies && <span className="new-alert-badge">New!</span>}
        </h3>
        {connectionStatus === 'connected' && 
          <small className="ws-status connected">Live{messageCount > 0 ? ` (${messageCount})` : ''}</small>
        }
        {connectionStatus === 'connecting' && 
          <small className="ws-status connecting">Connecting...</small>
        }
        {(connectionStatus === 'disconnected' || connectionStatus === 'error') && 
          <small className="ws-status disconnected">Offline</small>
        }
      </div>
      
      {isLoading && <p>Loading anomalies...</p>}
      {error && <p style={{ color: '#ff6b6b' }}>Error loading anomalies: {error}</p>}
      
      {!isLoading && !error && allAnomalies.length === 0 && (
        <p>No anomalies detected recently.</p>
      )}
      
      {!isLoading && !error && allAnomalies.length > 0 && (
        <ul className="anomaly-list">
          {allAnomalies.map((anomaly) => (
            <li 
              key={anomaly.id} // Use anomaly.id as key
              className={`anomaly-item ${hasNewAnomalies && (Date.now() - new Date(anomaly.timestamp).getTime()) < 5000 ? 'new-anomaly' : ''}`} 
            >
              <div className="anomaly-time">
                {new Date(anomaly.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
              <div className="anomaly-description">
                {anomaly.description || (
                  anomaly.parameter === 'pm25' 
                    ? `High PM₂.₅ level detected` 
                    : anomaly.parameter === 'pm10'
                      ? `High PM₁₀ value detected`
                      : `Elevated ${anomaly.parameter.toUpperCase()} level detected`
                )}
              </div>
              <div className="anomaly-location">
                {getLocationName(anomaly.latitude, anomaly.longitude)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// Helper function to get a city name based on coordinates
// In a real app, you would use reverse geocoding or a location database
const getLocationName = (lat, lon) => {
  // This is a simplified example - in reality you would use a geocoding service
  // or a database lookup to find the city name based on coordinates
  
  // Some hardcoded examples for demo purposes
  if (Math.abs(lat - 40.71) < 1 && Math.abs(lon - (-74.01)) < 1) return "New York, USA";
  if (Math.abs(lat - 34.05) < 1 && Math.abs(lon - (-118.24)) < 1) return "Los Angeles, USA";
  if (Math.abs(lat - 19.43) < 1 && Math.abs(lon - (-99.13)) < 1) return "Mexico City, Mexico";
  if (Math.abs(lat - 28.61) < 1 && Math.abs(lon - 77.21) < 1) return "New Delhi, India";
  if (Math.abs(lat - 39.91) < 1 && Math.abs(lon - 116.40) < 1) return "Beijing, China";
  if (Math.abs(lat - 35.68) < 1 && Math.abs(lon - 139.69) < 1) return "Tokyo, Japan";
  if (Math.abs(lat - (-33.87)) < 1 && Math.abs(lon - 151.21) < 1) return "Sydney, Australia";
  
  // Add Turkey locations since we have Turkish data in the test scripts
  if (Math.abs(lat - 41.01) < 1 && Math.abs(lon - 28.98) < 1) return "Istanbul, Turkey";
  if (Math.abs(lat - 39.91) < 1 && Math.abs(lon - 32.85) < 1) return "Ankara, Turkey";
  if (Math.abs(lat - 38.41) < 1 && Math.abs(lon - 27.14) < 1) return "Izmir, Turkey";
  if (Math.abs(lat - 36.88) < 1 && Math.abs(lon - 30.70) < 1) return "Antalya, Turkey";
  
  // Default fallback - just show coordinates
  return `${lat.toFixed(2)}°, ${lon.toFixed(2)}°`;
};

export default AnomalyPanel;