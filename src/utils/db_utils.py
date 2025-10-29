import psycopg2
from psycopg2.extras import execute_batch
import uuid
import hashlib
from datetime import datetime
from src.core.config import settings
from src.core.logger import logging

#=====================================================
# DB CONNECTION
#=====================================================

def get_connection():
    """ Safely create a PostgreSQL connection"""
    try:
        conn = psycopg2.connect(settings.DB_URL)
        logging.info("Connected to  DB successfully")
        return conn
    except Exception as e:
        logging.error(f"database connection FAILED: {e}")
        raise

#====================================================
# UUID GENERATOR
#====================================================

def generate_startup_id(name: str,sector:str) -> str:
    """
    Generates a deterministic, readable, unique ID based on startup name and sector.
    Ensures same name+sector always yields same ID.
    """
    base_str = f"{name.lower()}|{sector.lower()}"
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    stable_uuid = uuid.uuid5(namespace,base_str)

    short_hash = hashlib.md5(base_str.encode().hexdigest()[:6])
    suffix = str(stable_uuid).split[-1][:4]

    readable_name = name.lower().replace(" ","-")
    readable_sector = sector.lower.replace(" ","-")

    final_id = f"{readable_sector}-{readable_name}-{short_hash}-{suffix}"

    return final_id

#====================================================
# STARTUP INSERTION
#====================================================

def insert_startup(conn,startup):
    """
    Inserts a startup into DB safely.
    startup: dict with keys -> name, sector, description, imageUrl, findingKeywords
    """
    try:
        cur = conn.cursor()
        startup_id = generate_startup_id(startup["name"], startup["sector"])
        cur.execute("""
            INSERT INTO "Startups" 
            (id, name, sector, description, "imageUrl", "findingKeywords", "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        """, (
            startup_id,
            startup["name"],
            startup["sector"],
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

#====================================================
# ARTICLE INSERT/FIND
#====================================================

def find_or_create_article(conn, article):
    """Insert an article if not exists; return its ID."""
    try:
        cur = conn.cursor()
        cur.execute('SELECT id FROM "Articles" WHERE url = %s', (article["url"],))
        result = cur.fetchone()
        if result:
            return result[0]

        article_id = str(uuid.uuid4())
        content = article.get("content") or article.get("description") or ""
        content = content.strip()
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
        logging.info(f"Article inserted: {article.get('title')[:60]}")
        return article_id
    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert article: {e}")
        raise

#====================================================
# BATCH INSERT SENTIMENTS
#====================================================

def batch_insert_article_sentiments(conn, sentiments):
    """
    Batch insert for article-startup sentiment mapping.
    sentiments: list of tuples (id, articleId, startupId, sentiment, sentimentScore)
    """
    try:
        cur = conn.cursor()
        execute_batch(cur, """
            INSERT INTO "ArticleSentiment" 
            (id, "articleId", "startupId", sentiment, "sentimentScore", "createdAt")
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;
        """, [(s[0], s[1], s[2], s[3], s[4], datetime.now()) for s in sentiments])
        conn.commit()
        logging.info(f"Inserted {len(sentiments)} sentiment entries in batch.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Failed batch insert sentiment: {e}")
        raise

#=====================================================
# FETCH HELPERS
#=====================================================
def fetch_existing_urls(conn):
    """Fetch all existing article URLs to build dedup cache."""
    try:
        cur = conn.cursor()
        cur.execute('SELECT url FROM "Articles"')
        urls = {row[0] for row in cur.fetchall() if row[0]}
        logging.info(f"Cached {len(urls)} existing article URLs.")
        return urls
    except Exception as e:
        logging.error(f"Failed to fetch URLs: {e}")
        return set()



