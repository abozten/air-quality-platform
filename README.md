# Air Quality Platform

A full-stack application for collecting, processing, storing, and visualizing real-time air quality data.

## Features

*   **Real-time Data Ingestion:** Accepts air quality readings (PM2.5, PM10, NO2, SO2, O3) via an API endpoint.
*   **Asynchronous Processing:** Uses RabbitMQ and a Python worker to process and store data in InfluxDB asynchronously.
*   **Data Visualization:**
    *   Interactive map (Leaflet) displaying data points.
    *   Heatmap layer showing pollution intensity based on selected parameters.
    *   Anomaly markers highlighting unusual readings.
    *   Area selection tool to calculate and display average pollution density within a chosen bounding box.
*   **Real-time Updates:** WebSocket connection for pushing live updates (e.g., new anomalies) to the frontend.
*   **Anomaly Detection:** Backend logic (potentially in `anomaly_detection.py` and `worker.py`) to identify and store anomalies.
*   **Containerized:** Fully containerized using Docker and Docker Compose for easy setup and deployment.

## Tech Stack

*   **Backend:** Python, FastAPI, Pydantic, InfluxDB-Client, aio-pika (RabbitMQ client)
*   **Frontend:** React, Vite, JavaScript, Leaflet, react-leaflet, Chart.js, Axios
*   **Database:** InfluxDB (Time-series database)
*   **Message Queue:** RabbitMQ
*   **Containerization:** Docker, Docker Compose

## Project Structure

```
.
├── backend/             # FastAPI application, worker, DB/queue clients
│   ├── app/             # Main application code
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/            # React frontend application
│   ├── public/
│   ├── src/             # Source files (components, services, etc.)
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yaml  # Defines all services (backend, frontend, db, queue)
├── .env.example         # Example environment variables (You need to create a .env file)
└── README.md
```

## Setup and Running

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/abozten/air-quality-platform-kartaca/
    cd air-quality-platform
    ```

2.  **Create Environment File:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   **Important:** Edit the `.env` file and fill in your actual credentials and desired settings for InfluxDB, RabbitMQ, and API/Frontend ports. Pay special attention to:
        *   `INFLUXDB_USERNAME`, `INFLUXDB_PASSWORD`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `INFLUXDB_TOKEN`
        *   `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`
        *   `VITE_API_BASE_URL` (should point to your backend API, e.g., `http://localhost:8000/api/v1`)

3.  **Build and Run with Docker Compose:**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forces Docker to rebuild the images if the Dockerfiles or context have changed.
    *   `-d`: Runs the containers in detached mode (in the background).

4.  **Access the Application:**
    *   **Frontend:** Open your browser and navigate to `http://localhost:5173` (or the `FRONTEND_DEV_PORT` you set in `.env`).
    *   **Backend API Docs:** Navigate to `http://localhost:8000/docs` (or the `BACKEND_API_PORT` you set in `.env`) to see the FastAPI Swagger UI.
    *   **RabbitMQ Management:** Navigate to `http://localhost:15672` (or the `RABBITMQ_MANAGEMENT_PORT` you set in `.env`) and log in with the RabbitMQ credentials from your `.env` file.

## Development

*   **Backend:** The backend service uses `uvicorn --reload`, so changes made to the Python code inside `backend/app` should automatically reload the server within the container.
*   **Frontend:** The frontend service uses Vite's development server with Hot Module Replacement (HMR), so changes made to the React code inside `frontend/src` should update in the browser automatically.

## Stopping the Application

```bash
docker-compose down
```
*   To remove volumes (database data, queue data, node_modules cache) as well:
    ```bash
    docker-compose down -v
    ```

## Key API Endpoints (Prefix: `/api/v1`)

*   `POST /air_quality/ingest`: Submit new air quality readings.
*   `GET /air_quality/heatmap_data`: Get aggregated data points for the heatmap based on map bounds and zoom.
*   `GET /anomalies`: Retrieve detected anomalies.
*   `GET /pollution_density`: Get average pollution density for a selected bounding box.
*   `GET /air_quality/location`: Get the latest reading for a specific geohash cell near a lat/lon.
*   `WS /ws/anomalies`: WebSocket endpoint for live anomaly updates.

*(Note: This is based on the `backend/app/main.py` file. Refer to `/docs` on the running backend for full details.)*
