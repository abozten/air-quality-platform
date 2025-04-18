# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # Load .env file if it exists (useful for local development without Docker)
    # Docker Compose will set these via its own env var mechanism
    model_config = SettingsConfigDict(env_file='../.env', env_file_encoding='utf-8', extra='ignore')

    # InfluxDB Configuration
    influxdb_url: str = "http://localhost:8086" # Default for local running outside docker
    influxdb_token: str = "YourAdminAuthTokenHere" # Default/placeholder
    influxdb_org: str = "airquality_org"
    influxdb_bucket: str = "airquality_data"


    # RabbitMQ Configuration
    rabbitmq_host: str = "localhost" # Default for local running outside docker
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest" # Default RabbitMQ user
    rabbitmq_pass: str = "guest" # Default RabbitMQ pass
    rabbitmq_queue_raw: str = "raw_air_quality" # Queue for raw data

    # Anomaly Detection Thresholds (Example WHO PM2.5 24h Guideline - Hazardous)
    # Define thresholds for other pollutants as needed
    threshold_pm25_hazardous: float = 250.0 # Example value (adjust based on WHO guidelines or specific needs)
    threshold_pm10_hazardous: float = 420.0 # Example
    threshold_no2_hazardous: float = 200.0 # Example (often 1h limit)
    # ... add others

    # Add other settings as needed (e.g., API keys, Kafka details)
    # backend_api_port: int = 8000


@lru_cache() # Cache the settings object for performance
def get_settings() -> Settings:
    print("Loading settings...") # Debug print
    # When running inside Docker Compose, env vars set by compose will override .env defaults
    return Settings()

# Example usage:
# from .config import get_settings
# settings = get_settings()
# db_url = settings.influxdb_url