# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field # Import Field
from functools import lru_cache

class Settings(BaseSettings):
    # Pydantic-settings automatically tries to match uppercase env vars
    # but using alias makes it explicit and handles the '_DEFAULT_' part.
    model_config = SettingsConfigDict(env_file='../.env', env_file_encoding='utf-8', extra='ignore')

    # InfluxDB Configuration (Keep as is)
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "YourAdminAuthTokenHere"
    influxdb_org: str = "airquality_org"
    influxdb_bucket: str = "airquality_data"

    # RabbitMQ Configuration (Use alias to match .env/docker-compose setup)
    rabbitmq_host: str = "localhost" # Default for local, overridden by env var in docker
    rabbitmq_port: int = 5672
    # Explicitly map the settings field to the environment variable name
    rabbitmq_user: str = Field("guest", alias="RABBITMQ_DEFAULT_USER")
    rabbitmq_pass: str = Field("guest", alias="RABBITMQ_DEFAULT_PASS")
    rabbitmq_queue_raw: str = "raw_air_quality"
    
    geohash_precision_storage: int = 7 # Example precision

    # Anomaly Detection Thresholds (Keep as is)
    threshold_pm25_hazardous: float = 250.0
    threshold_pm10_hazardous: float = 420.0
    threshold_no2_hazardous: float = 200.0

@lru_cache()
def get_settings() -> Settings:
    print("Loading settings...") # Debug print
    # Now pydantic-settings will look for RABBITMQ_DEFAULT_USER and RABBITMQ_DEFAULT_PASS
    # when populating settings.rabbitmq_user and settings.rabbitmq_pass respectively.
    return Settings()