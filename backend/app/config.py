# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field # Import Field
from functools import lru_cache
import logging
class Settings(BaseSettings):
    # Pydantic-settings automatically tries to match uppercase env vars
    # but using alias makes it explicit and handles the '_DEFAULT_' part.
    model_config = SettingsConfigDict(env_file='../.env', env_file_encoding='utf-8', extra='ignore')

    # InfluxDB Configuration (Keep as is)
    # Note: Use Field with alias for environment variables if they differ from the field name
    # Although Pydantic-settings handles basic case conversion, explicit aliases are safer.
    # Let's assume direct env var mapping like INFLUXDB_URL unless .env or docker-compose specify otherwise.
    influxdb_url: str = Field("http://localhost:8086", alias="INFLUXDB_URL")
    influxdb_token: str = Field("YourAdminAuthTokenHere", alias="INFLUXDB_TOKEN")
    influxdb_org: str = Field("airquality_org", alias="INFLUXDB_ORG")
    influxdb_bucket: str = Field("airquality_data", alias="INFLUXDB_BUCKET")


    # RabbitMQ Configuration (Use alias to match .env/docker-compose setup)
    rabbitmq_host: str = Field("localhost", alias="RABBITMQ_HOST") # Default for local, overridden by env var in docker
    rabbitmq_port: int = Field(5672, alias="RABBITMQ_PORT")
    # Explicitly map the settings field to the environment variable name
    rabbitmq_user: str = Field("guest", alias="RABBITMQ_DEFAULT_USER")
    rabbitmq_pass: str = Field("guest", alias="RABBITMQ_DEFAULT_PASS")
    rabbitmq_queue_raw: str = Field("raw_air_quality", alias="RABBITMQ_QUEUE_RAW")


    # Anomaly Detection Thresholds (Keep as is)
    threshold_pm25_hazardous: float = 250.0
    threshold_pm10_hazardous: float = 420.0
    threshold_no2_hazardous: float = 200.0

@lru_cache()
def get_settings() -> Settings:
    logger = logging.getLogger(__name__) # Get logger inside function for cleaner import
    logger.info("Loading settings...")
    # Now pydantic-settings will look for RABBITMQ_DEFAULT_USER and RABBITMQ_DEFAULT_PASS
    # when populating settings.rabbitmq_user and settings.rabbitmq_pass respectively,
    # and INFLUXDB_URL etc. for influxdb_* fields.
    return Settings()

# settings = get_settings() # Avoid getting settings at module level here, use get_settings() where needed