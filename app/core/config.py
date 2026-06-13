from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Splunk HEC Settings
    SPLUNK_HEC_URI: str = "http://localhost:8088/services/collector/event"
    SPLUNK_HEC_TOKEN: str = "default-dev-token"
    
    # App Settings
    APP_NAME: str = "Real-Time Event Ticketing Engine"
    DEBUG: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
