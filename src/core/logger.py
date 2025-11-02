import logging
import os
from logging.handlers import RotatingFileHandler
from src.core.config import settings

# Ensure log directory exists
os.makedirs(settings.LOG_DIR, exist_ok=True)

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
console_handler.setLevel(logging.INFO) # Ensure console logs INFO level

# File handler (rotating)
file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=5_000_000, backupCount=3)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO) # Ensure file logs INFO level

# Add handlers only if they haven't been added
if not logger.hasHandlers():
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

# Shorthand alias
logging = logger
logging.info("Logger initialized successfully.")