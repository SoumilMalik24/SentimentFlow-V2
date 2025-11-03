import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import uuid
from datetime import datetime
from src.core.config import settings
from src.core.logger import logging
from src.constants import MAX_CONTENT_PREVIEW

# =========================================================
# DB CONNECTION
# =========================================================
def get_connection():
    """Safely create a PostgreSQL connection."""
    try:
        conn = psycopg2.connect(settings.DB_URL)
        logging.info("Connected to PostgreSQL successfully.")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        raise

# =========================================================
# FETCH STARTUPS
# =========================================================
def fetch_all_startups(conn):
    """Fetch all startups (id, name, sectorId) from the DB."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, "sectorId"
                FROM "Startups"
            """)
            rows = cur.fetchall()
            logging.info(f"Fetched {len(rows)} startups from DB.")
            return rows
    except Exception as e:
        logging.error(f"Failed to fetch startups: {e}")
        raise

# =========================================================
# FETCH STARTUP IDS WITH EXISTING SENTIMENT (NEW FUNCTION)
# =========================================================
def fetch_startup_ids_with_sentiment(conn):
    """
    Fetches a set of all startup IDs that have at least one entry
    in the ArticlesSentiment table.
    """
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT "startupId" FROM "ArticlesSentiment"')
            # Use a set for efficient O(1) lookups
            startup_ids = {row[0] for row in cur.fetchall()}
            logging.info(f"Found {len(startup_ids)} startups with existing sentiment.")
            return startup_ids
    except Exception as e:
        logging.error(f"Failed to fetch existing startup IDs: {e}")
        raise

# =========================================================
# FETCH SECTORS
# =========================================================
def fetch_sector_map(conn):
    """Fetch a map of {sector_id: sector_name}."""
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name FROM "Sector"')
            rows = cur.fetchall()
            sector_map = {row[0]: row[1] for row in rows}
            logging.info(f"Fetched {len(sector_map)} sectors from DB.")
            return sector_map
    except Exception as e:
        logging.error(f"Failed to fetch sector map: {e}")
        raise

# =========================================================
# FETCH EXISTING ARTICLE URLS
# =========================================================
def fetch_existing_urls(conn):
    """Fetch all existing article URLs for deduplication."""
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT url FROM "Articles"')
            urls = {row[0] for row in cur.fetchall() if row[0]}
            logging.info(f"Cached {len(urls)} existing article URLs.")
            return urls
    except Exception as e:
        logging.error(f"Failed to fetch URLs: {e}")
        return set()

# =========================================================
# BATCH INSERT ARTICLES
# =========================================================
def batch_insert_articles(conn, articles: list):
    """
    Batch-inserts new articles.
    Does NOT commit; the pipeline must handle the transaction.
    """
    if not articles:
        logging.info("No new articles to insert.")
        return

    insert_data = []
    for article in articles:
        # Prepare content: truncate if necessary
        content = (article.get("content") or article.get("description") or "").strip()
        if len(content) > MAX_CONTENT_PREVIEW:
            content = content[:MAX_CONTENT_PREVIEW].rsplit(" ", 1)[0] + "..."
            
        insert_data.append((
            str(uuid.uuid4()),
            article.get("title", "untitled"),
            article["url"],
            content,
            article.get("publishedAt"),
            datetime.now()
        ))

    try:
        with conn.cursor() as cur:
            execute_batch(cur, """
                INSERT INTO "Articles"
                (id, title, url, content, "publishedAt", "createdAt")
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING;
            """, insert_data)
            logging.info(f"Batch inserted/ignored {len(insert_data)} articles.")
    except Exception as e:
        logging.error(f"Failed to batch insert articles: {e}")
        raise

# =========================================================
# GET ARTICLES BY URLS
# =========================================================
def get_articles_by_urls(conn, urls: list):
    """
    Fetches newly inserted articles (with their DB IDs) by their URLs.
    Returns a dict {url: article_row}
    """
    if not urls:
        return {}
        
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, title, content, url FROM "Articles" WHERE url = ANY(%s)
            """, (urls,))
            rows = cur.fetchall()
            logging.info(f"Fetched {len(rows)} articles by URL to get their IDs.")
            return {row['url']: row for row in rows}
    except Exception as e:
        logging.error(f"Failed to get articles by URLs: {e}")
        raise

# =========================================================
# BATCH INSERT SENTIMENTS
# =========================================================
def batch_insert_article_sentiments(conn, sentiment_records):
    """
    Batch-inserts multiple sentiment analysis results.
    Does NOT commit; the pipeline must handle the transaction.
    """
    if not sentiment_records:
        logging.info("No sentiment records to insert.")
        return

    insert_data = [
        (
            str(uuid.uuid4()),
            record["articleId"],
            record["startupId"],
            record["positiveScore"],
            record["negativeScore"],
            record["neutralScore"],
            record["sentiment"],
            datetime.now()
        )
        for record in sentiment_records
    ]

    try:
        with conn.cursor() as cur:
            execute_batch(cur, """
                INSERT INTO "ArticlesSentiment"
                (id, "articleId", "startupId", "positiveScore", "negativeScore", "neutralScore", sentiment, "createdAt")
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("articleId", "startupId") DO NOTHING;
            """, insert_data)
        logging.info(f"Batch inserted {len(insert_data)} sentiment rows.")
    except Exception as e:
        logging.error(f"Failed to batch insert sentiments: {e}")
        raise
