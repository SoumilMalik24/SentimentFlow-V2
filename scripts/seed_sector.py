import sys
import os
import psycopg2

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.core.config import settings
    from src.core.logger import logging
except ImportError:
    print("Failed to import 'src' modules. Make sure you are running from the project root.")
    sys.exit(1)

SECTORS_TO_SEED = [
    (1, "Fintech"),
    (2, "EdTech"),
    (3, "HealthTech"),
    (4, "E-commerce"),
    (5, "SaaS"),
    (6, "AI"),
    (7, "AgriTech"),
    (8, "Logistics"),
    (9, "EV"),
    (10, "Gaming"),
    (11, "Biotech"),
    (12, "CleanTech"),
    (13, "Media"),
    (14, "D2C"),
    (15, "RetailTech"),
    (16, "HRTech"),
    (17, "MarTech"),
    (18, "Web3"),
    (19, "Blockchain"),
    (20, "Data Analytics"),
    (21, "Enterprise Software"),
    (22, "Mobility"),
    (23, "SpaceTech"),
    (24, "Hardware"),
    (25, "DroneTech"),
    (26, "Social Media"),
    (27, "Cybersecurity"),
    (28, "FoodTech"),
    (29, "Quick Commerce"),
    (30, "PropTech")
]

def seed_sectors():
    logging.info(f"Starting sector seeding for {len(SECTORS_TO_SEED)} sectors...")
    conn = None
    try:
        conn = psycopg2.connect(settings.DB_URL)
        with conn.cursor() as cur:
            
            logging.warning('Truncating "Sector" table... This will CASCADE and delete all startups!')
            cur.execute('TRUNCATE TABLE "Sector" CASCADE;')
            logging.info('Table "Sector" truncated.')

            for sector_id, sector_name in SECTORS_TO_SEED:
                logging.info(f"Seeding sector: {sector_name} (ID: {sector_id})")
                cur.execute(
                    """
                    INSERT INTO "Sector" (id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    (sector_id, sector_name)
                )
        conn.commit()
        logging.info("Sector seeding completed successfully.")
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Failed to seed sectors: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    seed_sectors()

