import logging
import os
from logging.handlers import RotatingFileHandler
from src.core.config import settings

LOG_FILE_PATH = os.path.join(settings.LOG_DIR, "pipeline.log")

# Create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# File handler (rotating)
file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=5_000_000, backupCount=3)
file_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Shorthand alias
logging = logger
logging.info("Logger initialized successfully.")
