import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    # Feishu Credentials
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET")
    
    # Feishu Bitable
    FEISHU_BITABLE_APP_TOKEN: str = os.getenv("FEISHU_BITABLE_APP_TOKEN")
    FEISHU_BITABLE_TABLE_ID: str = os.getenv("FEISHU_BITABLE_TABLE_ID")

    # Feishu Robot for notifications
    FEISHU_ROBOT_WEBHOOK_URL: str = os.getenv("FEISHU_ROBOT_WEBHOOK_URL")
    
    # Celery Configuration
    CELERY_APP_NAME: str = os.getenv("CELERY_APP_NAME")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL")
    CELERY_TASK_NAME: str = os.getenv("CELERY_TASK_NAME")
    CELERY_QUEUE: str = os.getenv("CELERY_QUEUE")

    import hashlib

class Settings:
    # ... (other settings)

    # Security
    API_KEY_HASH: str = os.getenv("API_KEY_HASH")
    

settings = Settings()
