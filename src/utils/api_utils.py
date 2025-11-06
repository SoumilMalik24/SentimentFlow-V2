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
# BUILD NEWSAPI QUERIES 
# =========================================================
def build_sector_queries(all_startups_data, existing_startup_ids):
    """
    Builds smart queries based on the logic:
    - New Startups (not in existing_ids): Fetch 30 days of news
    - Existing Startups (in existing_ids): Fetch 1 day of news
    
    Query Format: (Startup A OR Startup B) AND ("Sector" OR "Keyword1" OR "Keyword2")
    """
    logging.info("Building API queries with 1-day/30-day logic...")
    
    # 1. Separate startups into new vs. existing
    new_startups = []
    existing_startups = []
    
    for startup in all_startups_data:
        if startup['id'] in existing_startup_ids:
            existing_startups.append(startup)
        else:
            new_startups.append(startup)

    logging.info(f"Found {len(new_startups)} new startups (30-day) and {len(existing_startups)} existing startups (1-day).")

    # 2. Define dates
    today = datetime.now()
    one_day_ago = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    thirty_days_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # 3. Create query groups (sectorId, from_date, startups_list)
    query_groups = []
    
    # Group new startups by sectorId
    if new_startups:
        sorted_new = sorted(new_startups, key=itemgetter('sectorId'))
        for sector_id, group in groupby(sorted_new, key=itemgetter('sectorId')):
            query_groups.append((sector_id, thirty_days_ago, today_str, list(group)))

    # Group existing startups by sectorId
    if existing_startups:
        sorted_existing = sorted(existing_startups, key=itemgetter('sectorId'))
        for sector_id, group in groupby(sorted_existing, key=itemgetter('sectorId')):
            query_groups.append((sector_id, one_day_ago, today_str, list(group)))

    # 4. Build the final query tuples (query_string, from_date, to_date)
    final_queries = []
    
    for sector_id, from_date, to_date, startups_in_group in query_groups:
        
        # Build the startup part of the query
        startup_names = [f'"{s["name"]}"' for s in startups_in_group]
        startup_query = " OR ".join(startup_names)
        
        # Build the keyword part of the query
        all_keywords = {s['sectorName'] for s in startups_in_group if s['sectorName']}
        for s in startups_in_group:
            # --- THIS IS THE FIX ---
            # We use (s.get('findingKeywords') or []) to handle None values
            all_keywords.update(s.get('findingKeywords') or [])
            # --- END OF FIX ---
        
        # Ensure keywords are quoted
        quoted_keywords = [f'"{k}"' for k in all_keywords if k] # Filter out None/empty
        
        if not quoted_keywords:
            logging.warning(f"No sector or keywords for sectorId {sector_id}, skipping.")
            continue
            
        keyword_query = " OR ".join(quoted_keywords)
        
        # Combine
        final_query_str = f"({startup_query}) AND ({keyword_query})"
        
        logging.info(f"Built query for sector {sector_id} ({from_date}): {final_query_str}")
        final_queries.append((final_query_str, from_date, to_date))

    return final_queries

# =========================================================
# FETCH ARTICLES (Single Sector)
# =========================================================
def fetch_sector_articles(query, from_date, to_date):
    """Fetch all articles for a given query and date range with pagination."""
    query_log_name = f'query "{query[:50]}..."'
    logging.info(f"Fetching articles for {query_log_name} (from: {from_date})")

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
            "pageSize": API_PAGE_SIZE,
            "page": page,
            "apiKey": api_key,
        }

        try:
            response = session.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=FETCH_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request failed for {query_log_name} page {page}: {e}")
            break

        data = response.json()
        if "articles" not in data or not data["articles"]:
            break

        articles = data["articles"]
        all_articles.extend(articles)
        logging.info(f"{len(articles)} articles fetched for {query_log_name} (page {page})")

        if len(articles) < API_PAGE_SIZE:
            break

        page += 1
        time.sleep(1.2)  # respect rate limits

    logging.info(f"Total fetched for {query_log_name}: {len(all_articles)} articles.")
    return all_articles

# =========================================================
# MULTI-THREADED FETCHING (Sector-Level)
# =========================================================
def fetch_articles_threaded(sector_queries):
    """
    sector_queries: list of tuples (query_string, from_date, to_date)
    Runs each query in its own thread and aggregates results.
    """
    all_articles = []

    with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        futures = {
            executor.submit(fetch_sector_articles, query, from_date, to_date): query
            for query, from_date, to_date in sector_queries
        }

        for future in as_completed(futures):
            query_str = futures[future]
            try:
                articles = future.result()
                all_articles.extend(articles)
                logging.info(f"Completed sector fetch: {query_str[:50]}... ({len(articles)} articles)")
            except Exception as e:
                logging.error(f"Failed to fetch sector query {query_str[:50]}...: {e}")

    logging.info(f"Total fetched across sectors: {len(all_articles)} articles.")
    return all_articles

# =========================================================
# DEDUPLICATION BY URL
# =========================================================
def deduplicate_articles(all_articles):
    """
    Deduplicates all articles using their 'url' as unique identifier.
    Returns a dictionary {url: article}.
    """
    unique_articles = {}
    for article in all_articles:
        url = article.get("url")
        if not url or url in unique_articles:
            continue
        unique_articles[url] = article

    logging.info(f"Deduplicated articles: {len(unique_articles)} unique URLs.")
    return unique_articles

