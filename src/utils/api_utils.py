import requests
from requests.adapters import HTTPAdapter, Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from itertools import cycle, groupby
from operator import itemgetter
from datetime import datetime, timedelta
from src.core.config import settings
from src.core.logger import logging
from src.constants import FETCH_TIMEOUT, API_PAGE_SIZE, THREAD_COUNT

# =========================================================
# SETUP: Session with Retry Adapter
# =========================================================
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

# =========================================================
# KEY ROTATION (Cycle through multiple API keys)
# =========================================================
api_keys = settings.NEWS_API_KEYS
if not api_keys or len(api_keys) == 0:
    raise ValueError("No NEWS_API_KEYS provided in .env")

key_cycle = cycle(api_keys)

def get_api_key():
    """Return the next NewsAPI key (round-robin)."""
    return next(key_cycle)

# =========================================================
# BUILD NEWSAPI QUERIES (Moved from pipeline)
# =========================================================
def build_sector_queries(startups, sector_map):
    """
    Groups startups by sector and builds the NewsAPI query strings.
    """
    logging.info("Building sector queries...")
    sector_queries = []
    
    sorted_startups = sorted(startups, key=itemgetter('sectorId'))
    
    for sector_id, group in groupby(sorted_startups, key=itemgetter('sectorId')):
        sector_name = sector_map.get(sector_id)
        if not sector_name:
            logging.warning(f"Skipping sectorId {sector_id}: No matching name found.")
            continue
            
        startup_names = [f'"{s["name"]}"' for s in group]
        startup_query = " OR ".join(startup_names)
        final_query = f'({startup_query}) AND "{sector_name}"'
        
        sector_queries.append((sector_name, final_query))
        
    logging.info(f"Built {len(sector_queries)} queries for News API.")
    return sector_queries

# =========================================================
# FETCH ARTICLES (Single Sector)
# =========================================================
def fetch_sector_articles(sector_name, query):
    """Fetch all articles for a given sector query with pagination."""
    logging.info(f"Fetching articles for sector: {sector_name}")

    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")

    all_articles = []
    page = 1

    while True:
        api_key = get_api_key()
        params = {
            "q": query,
            "language": "en",
            "from": from_date,
            "to": to_date,
            "sortBy": "publishedAt",
            "searchIn": "title,description",
            "pageSize": API_PAGE_SIZE, # From constants
            "page": page,
            "apiKey": api_key,
        }

        try:
            response = session.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=FETCH_TIMEOUT, # From constants
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request failed for {sector_name} page {page}: {e}")
            break

        data = response.json()
        if "articles" not in data or not data["articles"]:
            break

        articles = data["articles"]
        all_articles.extend(articles)
        logging.info(f"{len(articles)} articles fetched for {sector_name} (page {page})")

        if len(articles) < API_PAGE_SIZE:
            break

        page += 1
        time.sleep(1.2)  # respect rate limits

    logging.info(f"Total fetched for {sector_name}: {len(all_articles)} articles.")
    return all_articles

# =========================================================
# MULTI-THREADED FETCHING (Sector-Level)
# =========================================================
def fetch_articles_threaded(sector_queries):
    """
    Runs each query in its own thread and aggregates results.
    """
    all_articles = []

    with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor: # From constants
        futures = {
            executor.submit(fetch_sector_articles, sector, query): sector
            for sector, query in sector_queries
        }

        for future in as_completed(futures):
            sector = futures[future]
            try:
                articles = future.result()
                all_articles.extend(articles)
                logging.info(f"Completed sector fetch: {sector} ({len(articles)} articles)")
            except Exception as e:
                logging.error(f"Failed to fetch sector {sector}: {e}")

    logging.info(f"Total fetched across sectors: {len(all_articles)} articles.")
    return all_articles

# =========================================================
# DEDUPLICATION BY URL
# =========================================================
def deduplicate_articles(all_articles):
    """
    Deduplicates all articles using their 'url' as unique identifier.
    """
    unique_articles = {}
    for article in all_articles:
        url = article.get("url")
        if not url or url in unique_articles:
            continue
        unique_articles[url] = article

    logging.info(f"Deduplicated articles: {len(unique_articles)} unique URLs.")
    return unique_articles