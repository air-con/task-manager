import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

    # Momento Cache
    MOMENTO_API_KEY: str = os.getenv("MOMENTO_API_KEY")

    # Celery Configuration
    CELERY_APP_NAME: str = os.getenv("CELERY_APP_NAME")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL")
    CELERY_TASK_NAME: str = os.getenv("CELERY_TASK_NAME")
    CELERY_QUEUE: str = os.getenv("CELERY_QUEUE")

    # Scheduler Settings
    SCHEDULER_TASK_REPLENISH_COUNT: int = int(os.getenv("SCHEDULER_TASK_REPLENISH_COUNT", 5000))
    SCHEDULER_BATCH_SIZE: int = int(os.getenv("SCHEDULER_BATCH_SIZE", 10))

    
    

settings = Settings()
