#!/usr/bin/env python3
"""
Air Quality Platform API Test Script
-----------------------------------
Tests the backend API endpoints for functionality.
"""

import requests
import json
import time
import websocket
import threading
import random
from datetime import datetime, timedelta
import sys

# API Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
WS_URL = "ws://localhost:8000/api/v1/ws/anomalies"

# Colors for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

def print_header(message):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {message}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.END}\n")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_error(message):
    """Print an error message"""
    print(f"{Colors.RED}✗ {message}{Colors.END}")

def print_info(message):
    """Print an info message"""
    print(f"{Colors.YELLOW}• {message}{Colors.END}")

def test_root_endpoint():
    """Test the root endpoint"""
    print_header("Testing Root Endpoint")
    
    try:
        response = requests.get(f"http://localhost:8000/")
        if response.status_code == 200:
            data = response.json()
            print_success(f"Root endpoint is working. Message: {data['message']}")
            return True
        else:
            print_error(f"Root endpoint failed with status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_heatmap_data():
    """Test the heatmap data endpoint"""
    print_header("Testing Heatmap Data Endpoint")
    
    # Sample coordinates of a large area (roughly Turkey)
    params = {
        "min_lat": 36.0,
        "max_lat": 42.0,
        "min_lon": 26.0,
        "max_lon": 45.0,
        "zoom": 5,
        "window": "24h"
    }
    
    try:
        print_info(f"Fetching heatmap data for area: lat [{params['min_lat']}-{params['max_lat']}], lon [{params['min_lon']}-{params['max_lon']}]")
        response = requests.get(f"{API_BASE_URL}/air_quality/heatmap_data", params=params)
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Heatmap data endpoint returned {len(data)} data points")
            
            if len(data) > 0:
                sample_point = data[0]
                print_info("Sample data point:")
                print(json.dumps(sample_point, indent=2))
            else:
                print_info("No data points found in the specified area and time window")
            
            return True
        else:
            print_error(f"Heatmap data endpoint failed with status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_anomalies():
    """Test the anomalies endpoint"""
    print_header("Testing Anomalies Endpoint")
    
    try:
        # Get anomalies from the last 24 hours (default behavior)
        print_info("Fetching anomalies from the last 24 hours")
        response = requests.get(f"{API_BASE_URL}/anomalies")
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Anomalies endpoint returned {len(data)} anomalies")
            
            if len(data) > 0:
                sample_anomaly = data[0]
                print_info("Sample anomaly:")
                print(json.dumps(sample_anomaly, indent=2))
            else:
                print_info("No anomalies found in the last 24 hours")
            
            # Test with custom time range
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.isoformat()
            
            print_info(f"Fetching anomalies since {yesterday_str}")
            response = requests.get(f"{API_BASE_URL}/anomalies", params={"start_time": yesterday_str})
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Anomalies with time range returned {len(data)} anomalies")
            else:
                print_error(f"Anomalies endpoint with time range failed: {response.status_code}")
            
            return True
        else:
            print_error(f"Anomalies endpoint failed with status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_location_api():
    """Test the location API endpoint"""
    print_header("Testing Location API Endpoint")
    
    # Istanbul coordinates
    params = {
        "lat": 41.01,
        "lon": 28.98,
        "geohash_precision": 5,
        "window": "24h"
    }
    
    try:
        print_info(f"Fetching data for location: lat={params['lat']}, lon={params['lon']}")
        response = requests.get(f"{API_BASE_URL}/air_quality/location", params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print_success("Location API returned data")
                print_info("Data:")
                print(json.dumps(data, indent=2))
                
                # Store geohash for history test if available
                geohash = data.get("geohash")
                if geohash:
                    test_location_history(geohash)
            else:
                print_info("No data found for the specified location")
            
            return True
        else:
            print_error(f"Location API failed with status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_location_history(geohash=None):
    """Test the location history endpoint"""
    print_header("Testing Location History Endpoint")
    
    # Use provided geohash or a default one
    if not geohash:
        # Turkey/Istanbul area
        geohash = "u4phf"  
    
    # Parameters to test
    parameters = ["pm25", "pm10", "no2", "o3", "so2"]
    
    success_count = 0
    for param in parameters:
        try:
            print_info(f"Fetching history for parameter: {param}, geohash: {geohash}")
            response = requests.get(f"{API_BASE_URL}/air_quality/location_history/{geohash}?parameter={param}&window=24h&aggregate=10m")
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"History API for {param} returned {len(data)} data points")
                
                if len(data) > 0:
                    print_info(f"First point: {data[0]}")
                    print_info(f"Last point: {data[-1]}")
                else:
                    print_info(f"No history data for {param}")
                
                success_count += 1
            else:
                print_error(f"History API for {param} failed with status code: {response.status_code}")
                print_error(f"Response: {response.text}")
        except requests.exceptions.RequestException as e:
            print_error(f"Connection error: {e}")
    
    return success_count > 0

def test_pollution_density():
    """Test the pollution density endpoint"""
    print_header("Testing Pollution Density Endpoint")
    
    # Sample coordinates for a smaller area (roughly Istanbul)
    params = {
        "min_lat": 40.9,
        "max_lat": 41.1,
        "min_lon": 28.9,
        "max_lon": 29.1,
        "window": "24h"
    }
    
    try:
        print_info(f"Fetching pollution density for area: lat [{params['min_lat']}-{params['max_lat']}], lon [{params['min_lon']}-{params['max_lon']}]")
        response = requests.get(f"{API_BASE_URL}/pollution_density", params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print_success("Pollution density endpoint returned data")
                print_info("Data:")
                print(json.dumps(data, indent=2))
            else:
                print_info("No density data found for the specified area")
            
            return True
        else:
            print_error(f"Pollution density endpoint failed with status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_ingest_data():
    """Test the data ingestion endpoint"""
    print_header("Testing Data Ingestion Endpoint")
    
    # Create a random data point
    current_time = datetime.utcnow().isoformat() + "Z"
    test_data = {
        "timestamp": current_time,
        "latitude": 41.01 + random.uniform(-0.01, 0.01),  # Istanbul with small random variation
        "longitude": 28.98 + random.uniform(-0.01, 0.01),
        "pm25": 25.0 + random.uniform(-5, 5),
        "pm10": 40.0 + random.uniform(-10, 10),
        "no2": 15.0 + random.uniform(-5, 5),
        "so2": 5.0 + random.uniform(-2, 2),
        "o3": 30.0 + random.uniform(-10, 10),
        "co": 0.5 + random.uniform(-0.1, 0.1),
        "device_id": "api_test_device",
        "source": "api_test_script"
    }
    
    try:
        print_info("Sending test data point for ingestion")
        print(json.dumps(test_data, indent=2))
        
        response = requests.post(f"{API_BASE_URL}/air_quality/ingest", json=test_data)
        
        if response.status_code == 202:
            print_success("Data ingestion succeeded - 202 Accepted")
            print_info(f"Response: {response.json()}")
            return True
        else:
            print_error(f"Data ingestion failed with status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_websocket():
    """Test the WebSocket connection for live anomalies"""
    print_header("Testing WebSocket Connection")
    
    # Event to signal receipt of messages
    message_received = threading.Event()
    
    def on_message(ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            if data.get("type") == "connection_status":
                print_success(f"WebSocket connected: {data.get('message')}")
            elif data.get("type") == "recent_anomaly":
                print_success(f"Received recent anomaly: {data.get('payload', {}).get('id')}")
            elif data.get("type") == "new_anomaly":
                print_success(f"Received new anomaly: {data.get('payload', {}).get('id')}")
            else:
                print_info(f"Received message: {message[:100]}...")
            
            message_received.set()
        except json.JSONDecodeError:
            print_error(f"Could not parse message as JSON: {message[:100]}...")
    
    def on_error(ws, error):
        print_error(f"WebSocket error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print_info(f"WebSocket connection closed (status: {close_status_code}, msg: {close_msg})")
    
    def on_open(ws):
        print_info("WebSocket connection established")
        # Send a ping after connection
        def ping():
            time.sleep(1)
            ws.send("ping")
        
        threading.Thread(target=ping).start()
    
    # Create and start WebSocket connection
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    ws_thread = threading.Thread(target=ws.run_forever)
    ws_thread.daemon = True
    
    try:
        print_info(f"Connecting to WebSocket at {WS_URL}")
        ws_thread.start()
        
        # Wait for message for 10 seconds
        if message_received.wait(timeout=10):
            print_success("Successfully received message(s) from WebSocket")
        else:
            print_error("Timed out waiting for WebSocket messages")
        
        # Test broadcast by triggering the test endpoint
        print_info("Testing anomaly broadcast via test endpoint")
        response = requests.post(f"{API_BASE_URL}/test/broadcast-anomaly")
        
        if response.status_code == 200:
            print_success(f"Test broadcast triggered: {response.json().get('message')}")
            # Reset event and wait for broadcast message
            message_received.clear()
            if message_received.wait(timeout=10):
                print_success("Successfully received broadcast anomaly")
            else:
                print_info("No broadcast anomaly received (this is normal if running only one API instance)")
        else:
            print_error(f"Test broadcast failed: {response.status_code}")
        
        return True
    except Exception as e:
        print_error(f"WebSocket test error: {e}")
        return False
    finally:
        print_info("Closing WebSocket connection")
        ws.close()

def run_all_tests():
    """Run all API tests"""
    print_header("RUNNING ALL API TESTS")
    
    tests = [
        ("Root Endpoint", test_root_endpoint),
        ("Heatmap Data", test_heatmap_data),
        ("Anomalies", test_anomalies),
        ("Location API", test_location_api),
        ("Pollution Density", test_pollution_density), 
        ("Data Ingestion", test_ingest_data),
        ("WebSocket", test_websocket)
    ]
    
    results = []
    
    for name, test_func in tests:
        print_header(f"RUNNING: {name}")
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print_error(f"Uncaught exception in {name} test: {e}")
            results.append((name, False))
    
    # Print summary
    print_header("TEST SUMMARY")
    
    success_count = 0
    for name, success in results:
        if success:
            print_success(f"{name}: PASSED")
            success_count += 1
        else:
            print_error(f"{name}: FAILED")
    
    success_rate = (success_count / len(results)) * 100 if results else 0
    print(f"\n{Colors.BOLD}Tests passed: {success_count}/{len(results)} ({success_rate:.1f}%){Colors.END}")
    
    return success_count == len(results)

if __name__ == "__main__":
    # Check if a specific test is requested
    if len(sys.argv) > 1:
        test_name = sys.argv[1].lower()
        
        if test_name == "root":
            test_root_endpoint()
        elif test_name == "heatmap":
            test_heatmap_data()
        elif test_name == "anomalies":
            test_anomalies()
        elif test_name == "location":
            test_location_api()
        elif test_name == "history":
            test_location_history()
        elif test_name == "density":
            test_pollution_density()
        elif test_name == "ingest":
            test_ingest_data()
        elif test_name == "websocket":
            test_websocket()
        else:
            print_error(f"Unknown test: {test_name}")
            print_info("Available tests: root, heatmap, anomalies, location, history, density, ingest, websocket")
    else:
        # Run all tests
        run_all_tests()