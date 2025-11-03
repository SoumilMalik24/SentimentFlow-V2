import psycopg2
import sys
import os

# This is the minimum required to import your settings
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
try:
    from src.core.config import settings
except ImportError:
    print("Error: Could not import settings. Make sure this script is in the root (same folder as src/).")
    sys.exit(1)

conn = None
try:
    print("Connecting to database...")
    conn = psycopg2.connect(settings.DB_URL)
    
    with conn.cursor() as cur:
        print('Executing: ALTER TABLE "Articles" ADD CONSTRAINT articles_url_unique UNIQUE (url);')
        cur.execute('ALTER TABLE "Articles" ADD CONSTRAINT articles_url_unique UNIQUE (url);')
    
    # Commit the change
    print("Committing transaction...")
    conn.commit()
    
    print("Successfully added UNIQUE constraint to 'Articles.url'.")

except (Exception, psycopg2.Error) as e:
    if "already exists" in str(e):
        print("Warning: Constraint 'articles_url_unique' already exists. No action taken.")
    else:
        print(f"Failed to add constraint: {e}")
    if conn:
        conn.rollback()
finally:
    if conn:
        conn.close()
        print("Database connection closed.")
