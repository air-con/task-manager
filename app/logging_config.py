import sys
from loguru import logger

def setup_logging():
    """
    Configures the logger for the application, including file rotation.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        "logs/app_{time}.log",
        rotation="3 days",
        retention="10 days", # Keep logs for 10 days
        compression="zip",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True, # Make it process-safe
        backtrace=True,
        diagnose=True
    )
    logger.info("Logger configured successfully.")
