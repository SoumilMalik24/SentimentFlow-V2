from src.core.config import settings

# General constants
MAX_CONTENT_PREVIEW = 300
FETCH_TIMEOUT = 15
API_PAGE_SIZE = 100
THREAD_COUNT = 5
RETRY_LIMIT = 3

# Model settings
MODEL_MAX_LENGTH = 256
SENTIMENT_LABELS = ["negative", "neutral", "positive"]

# Summary file path template
SUMMARY_FILE_PATTERN = "logs/pipeline_summary_{timestamp}.json"


#api keys
NEWS_API_KEYS = settings.NEWS_API_KEYS

# Model settings
MODEL_MAX_LENGTH = 256
MODEL_BATCH_SIZE = 32