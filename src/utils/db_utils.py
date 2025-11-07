import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import uuid
import json
import re  
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
# == HELPER FOR TRUNCATION 
# =========================================================
def _clean_and_truncate_content(content_str: str) -> str:
    """
    Cleans and truncates article content for database storage.
    """
    if not content_str:
        return ""
    
    # 1. Remove trailing "[+123 chars]" patterns
    cleaned_content = re.sub(r'\s*\[\+\d+\s+chars\]$', '', content_str)
    
    # 2. Check length and truncate if necessary
    if len(cleaned_content) > MAX_CONTENT_PREVIEW:
        truncated = cleaned_content[:MAX_CONTENT_PREVIEW].rsplit(' ', 1)[0]
        return truncated + "..."
    
    return cleaned_content

# =========================================================
# == MAIN PIPELINE FUNCTIONS 
# =========================================================

def fetch_startups_for_api(conn):
    """
    Fetches all startup details needed for API query building.
    Joins with Sector to get sectorName and fetches findingKeywords.
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    s.id, 
                    s.name, 
                    s."sectorId", 
                    s."findingKeywords", 
                    sec.name AS "sectorName"
                FROM "Startups" s
                LEFT JOIN "Sector" sec ON s."sectorId" = sec.id
            """)
            rows = cur.fetchall()
            
            for row in rows:
                if row['findingKeywords'] and isinstance(row['findingKeywords'], str):
                    try:
                        row['findingKeywords'] = json.loads(row['findingKeywords'])
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse findingKeywords for {row['name']}: {row['findingKeywords']}")
                        row['findingKeywords'] = []
                elif not row['findingKeywords']:
                    row['findingKeywords'] = []

            logging.info(f"Fetched {len(rows)} startups with sector/keyword data.")
            return rows
    except Exception as e:
        logging.error(f"Failed to fetch startups with details: {e}")
        raise

def fetch_startup_ids_with_sentiment(conn):
    """Fetch a set of all startup IDs that have at least one sentiment entry."""
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT "startupId" FROM "ArticlesSentiment"')
            ids = {row[0] for row in cur.fetchall()}
            logging.info(f"Found {len(ids)} startups with existing sentiment data.")
            return ids
    except Exception as e:
        logging.error(f"Failed to fetch startup IDs with sentiment: {e}")
        raise

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
        raise

# =========================================================
# BATCH INSERT ARTICLES (REVISED)
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
        raw_content = (article.get("content") or article.get("description") or "").strip()
        
        cleaned_content = _clean_and_truncate_content(raw_content)
            
        insert_data.append((
            str(uuid.uuid4()),
            article.get("title", "untitled"),
            article["url"],
            cleaned_content, 
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

# =========================================================
# == ADMIN SCRIPT FUNCTIONS
# =========================================================

def fetch_all_sectors(conn):
    """Fetches all sectors for the Streamlit dropdown."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, name FROM "Sector" ORDER BY name')
            return cur.fetchall()
    except Exception as e:
        logging.error(f"Failed to fetch all sectors: {e}")
        raise

def get_sector_id_by_name(conn, sector_name: str):
    """
    Fetches the ID of a sector given its name.
    """
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM "Sector" WHERE LOWER(name) = LOWER(%s)', (sector_name.strip(),))
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                logging.warning(f"No sector found with name: {sector_name}")
                return None
    except Exception as e:
        logging.error(f"Failed to fetch sector by name: {e}")
        raise

def upsert_startup(conn, startup_data: dict):
    """
    Inserts or updates a startup.
    Converts findingKeywords list into a JSON string for storage.
    """
    try:
        keywords_list = startup_data.get("findingKeywords", [])
        keywords_json_string = json.dumps(keywords_list)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO "Startups"
                (id, name, "sectorId", description, "imageUrl", "findingKeywords", "createdAt")
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    "sectorId" = EXCLUDED."sectorId",
                    description = EXCLUDED.description,
                    "imageUrl" = EXCLUDED."imageUrl",
                    "findingKeywords" = EXCLUDED."findingKeywords";
            """, (
                startup_data["id"],
                startup_data["name"],
                startup_data["sectorId"],
                startup_data.get("description", ""),
                startup_data.get("imageUrl", ""),
                keywords_json_string,  
                datetime.now()
            ))
            logging.info(f"Upserted startup: {startup_data['name']} (ID: {startup_data['id']})")
    except Exception as e:
        logging.error(f"Failed to upsert startup {startup_data['name']}: {e}")
        raise