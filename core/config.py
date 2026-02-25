import yaml
import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Ai Analyze"
    app_version: str = "1.0.0"
    debug: bool = False

    db_url: str = ""

    ai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ai_api_key: str = ""
    ai_model: str = "qwen-plus"

    max_pdf_size_mb: int = 10

    jwt_key: str = ""
    api_role_url: str = ""
    cors_origins: str = "*"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_secure: bool = True

@lru_cache()
def get_settings() -> Settings:
    config_path = os.getenv("CONFIG_PATH", "config.yml")
    
    if not os.path.exists(config_path):
        # Fallback to defaults if no config file exists
        return Settings()

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)
    
    return Settings(**(config_data or {}))
