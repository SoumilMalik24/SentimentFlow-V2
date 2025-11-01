import psycopg2
from psycopg2.extras import execute_batch
import uuid
import hashlib
from datetime import datetime
from src.core.config import settings
from src.core.logger import logging

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
# DETERMINISTIC STARTUP ID GENERATOR
# =========================================================
def generate_startup_id(name: str, sector_id: str) -> str:
    """
    Generates a deterministic, readable, unique ID based on startup name and sector ID.
    Example: swiggy-51f4a2-9f2d
    """
    base_str = f"{name.lower()}|{sector_id.lower()}"
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    stable_uuid = uuid.uuid5(namespace, base_str)

    short_hash = hashlib.md5(base_str.encode()).hexdigest()[:6]
    suffix = str(stable_uuid).split('-')[-1][:4]

    readable_name = name.lower().replace(" ", "-")
    final_id = f"{readable_name}-{short_hash}-{suffix}"
    return final_id


# =========================================================
# STARTUP INSERT
# =========================================================
def insert_startup(conn, startup):
    """
    Insert or ignore a startup entry.
    startup = {
        "name": str,
        "sectorId": str,
        "description": str,
        "imageUrl": str,
        "findingKeywords": list
    }
    """
    try:
        cur = conn.cursor()
        startup_id = generate_startup_id(startup["name"], startup["sectorId"])
        cur.execute("""
            INSERT INTO "Startups"
            (id, name, "sectorId", description, "imageUrl", "findingKeywords", "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        """, (
            startup_id,
            startup["name"],
            startup["sectorId"],
            startup.get("description", ""),
            startup.get("imageUrl", ""),
            startup.get("findingKeywords", []),
            datetime.now()
        ))
        conn.commit()
        logging.info(f"Startup inserted/exists: {startup['name']} ({startup_id})")
        return startup_id
    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert startup {startup['name']}: {e}")
        raise


# =========================================================
# ARTICLE UPSERT (CREATE IF NOT EXISTS)
# =========================================================
def find_or_create_article(conn, article):
    """
    Insert article if not exists, else return existing ID.
    Returns article_id (UUID)
    """
    try:
        cur = conn.cursor()
        cur.execute('SELECT id FROM "Articles" WHERE url = %s', (article["url"],))
        result = cur.fetchone()
        if result:
            return result[0]

        article_id = str(uuid.uuid4())
        content = (article.get("content") or article.get("description") or "").strip()
        if len(content) > 300:
            content = content[:300].rsplit(" ", 1)[0] + "..."

        cur.execute("""
            INSERT INTO "Articles"
            (id, title, url, content, "publishedAt", "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            article_id,
            article.get("title", "untitled"),
            article["url"],
            content,
            article.get("publishedAt"),
            datetime.now()
        ))
        conn.commit()
        logging.info(f"Article inserted: {article.get('title')[:70]}")
        return article_id
    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert article: {e}")
        raise


# =========================================================
# SENTIMENT INSERT (NEW STRUCTURE)
# =========================================================
def insert_article_sentiment(conn, record):
    """
    Inserts one record into ArticleSentiment table.
    record = {
        "articleId": str,
        "startupId": str,
        "positiveScore": float,
        "negativeScore": float,
        "neutralScore": float,
        "sentiment": str
    }
    """
    try:
        cur = conn.cursor()
        sentiment_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO "ArticleSentiment"
            (id, "articleId", "startupId", "positiveScore", "negativeScore", "neutralScore", sentiment, "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;
        """, (
            sentiment_id,
            record["articleId"],
            record["startupId"],
            record["positiveScore"],
            record["negativeScore"],
            record["neutralScore"],
            record["sentiment"],
            datetime.now()
        ))
        conn.commit()
        logging.info(f"Sentiment inserted for startup {record['startupId']} ({record['sentiment']})")
    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert sentiment: {e}")
        raise


# =========================================================
# BATCH SENTIMENT INSERT
# =========================================================
def batch_insert_article_sentiments(conn, records):
    """
    Batch insert for multiple startup–article sentiments.
    records = [
        (uuid, articleId, startupId, positive, negative, neutral, sentiment)
    ]
    """
    try:
        cur = conn.cursor()
        execute_batch(cur, """
            INSERT INTO "ArticleSentiment"
            (id, "articleId", "startupId", "positiveScore", "negativeScore", "neutralScore", sentiment, "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;
        """, [
            (str(uuid.uuid4()), r["articleId"], r["startupId"], r["positiveScore"],
             r["negativeScore"], r["neutralScore"], r["sentiment"], datetime.now())
            for r in records
        ])
        conn.commit()
        logging.info(f"Batch inserted {len(records)} sentiment rows.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Batch insert failed: {e}")
        raise


# =========================================================
# FETCH EXISTING ARTICLE URLS
# =========================================================
def fetch_existing_urls(conn):
    """Fetch all existing article URLs."""
    try:
        cur = conn.cursor()
        cur.execute('SELECT url FROM "Articles"')
        urls = {row[0] for row in cur.fetchall() if row[0]}
        logging.info(f"Cached {len(urls)} existing article URLs.")
        return urls
    except Exception as e:
        logging.error(f"Failed to fetch URLs: {e}")
        return set()
