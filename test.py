import sys
from src.utils import db_utils
from src.core.logger import logging

def fix_database_column():
    """
    Changes the "findingKeywords" column in the "Startups" table
    from TEXT[] (or any other type) to TEXT.
    This is necessary to store keywords as a JSON string,
    bypassing the Prisma proxy array issue.
    """
    conn = None
    try:
        conn = db_utils.get_connection()
        with conn.cursor() as cur:
            logging.info('Attempting to change "findingKeywords" column type to TEXT...')
            cur.execute('ALTER TABLE "Startups" ALTER COLUMN "findingKeywords" TYPE TEXT;')
            conn.commit()
            logging.info('SUCCESS: "findingKeywords" column is now TEXT.')

    except Exception as e:
        logging.error(f"Failed to alter table: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if "--run" in sys.argv:
        fix_database_column()
    else:
        logging.warning("This is a safety check.")
        logging.warning('Run this script with "python test.py --run" to execute the database migration.')

