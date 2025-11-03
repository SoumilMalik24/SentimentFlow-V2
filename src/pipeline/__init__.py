import sys
from os.path import dirname, abspath

# Add the project root to the Python path
project_root = dirname(dirname(abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Imports now use your new logger
from src.core.logger import logging 
from src.utils import api_utils, db_utils, sentiment_utils
from src.utils.text_utils import StartupSearch

def main_pipeline():
    """
    Runs the full E-T-L pipeline for sentiment flow.
    """
    logging.info("===== STARTING SENTIMENT FLOW PIPELINE =====")
    conn = None
    try:
        # =========================================================
        # STEP 1: Connect and Fetch Initial Data
        # =========================================================
        conn = db_utils.get_connection()
        if conn is None:
            raise Exception("Failed to get database connection.")

        all_startups = db_utils.fetch_all_startups(conn)
        sector_map = db_utils.fetch_sector_map(conn)
        
        # --- NEW ---
        # Get set of startups that already have sentiment data
        existing_startup_ids = db_utils.fetch_startup_ids_with_sentiment(conn)
        # --- END NEW ---
        
        if not all_startups or not sector_map:
            logging.error("No startups or sectors found. Exiting.")
            return

        # =========================================================
        # STEP 2: Build API Queries
        # =========================================================
        # Pass all data to the revised builder
        sector_queries = api_utils.build_sector_queries(
            all_startups, 
            sector_map, 
            existing_startup_ids
        )
        if not sector_queries:
            logging.error("No API queries could be built. Exiting.")
            return
            
        # =========================================================
        # STEP 3: Fetch and Deduplicate Articles
        # =========================================================
        # fetch_articles_threaded is already updated to handle the new
        # (name, query, date) format of sector_queries
        fetched_articles_list = api_utils.fetch_articles_threaded(sector_queries)
        unique_fetched_articles = api_utils.deduplicate_articles(fetched_articles_list)
        
        existing_urls = db_utils.fetch_existing_urls(conn)
        
        new_article_data = []
        for url, article in unique_fetched_articles.items():
            if url not in existing_urls:
                new_article_data.append(article)
                
        if not new_article_data:
            logging.info("No new articles found. Pipeline complete.")
            return
            
        logging.info(f"Found {len(new_article_data)} new articles to process.")

        # =========================================================
        # STEP 4: Insert New Articles
        # =========================================================
        db_utils.batch_insert_articles(conn, new_article_data)
        
        new_urls = [a['url'] for a in new_article_data]
        articles_from_db = db_utils.get_articles_by_urls(conn, new_urls)

        # =========================================================
        # STEP 5: Build Startup Search Engine
        # =========================================================
        search_engine = StartupSearch()
        search_engine.build_engine(all_startups) # Build with ALL startups

        # =========================================================
        # STEP 6: Process Articles and Analyze Sentiment
        # =========================================================
        all_sentiment_records = []
        
        for url, article_row in articles_from_db.items():
            try:
                logging.info(f"Processing article: {article_row.get('title', 'No Title')[:70]}...")
                
                text_to_search = f"{article_row['title']}. {article_row['content']}"
                found_startup_ids = search_engine.find_startups_in_text(text_to_search)
                
                if not found_startup_ids:
                    logging.info("No registered startups found in this article.")
                    continue
                    
                startups_to_analyze = [
                    info for sid in found_startup_ids 
                    if (info := search_engine.get_startup_info(sid))
                ]

                logging.info(f"Found {len(startups_to_analyze)} startups to analyze: {[s['name'] for s in startups_to_analyze]}")
                
                sentiment_records = sentiment_utils.analyze_article_sentiments(
                    article_row,
                    startups_to_analyze
                )
                
                all_sentiment_records.extend(sentiment_records)

            except Exception as e:
                logging.error(f"Failed to process article {article_row.get('url')}: {e}")

        # =========================================================
        # STEP 7: Batch Insert All Sentiments and Commit
        # =========================================================
        if not all_sentiment_records:
            logging.info("No new sentiment records to insert.")
        else:
            logging.info(f"Batch inserting {len(all_sentiment_records)} sentiment records...")
            db_utils.batch_insert_article_sentiments(conn, all_sentiment_records)
            
        logging.info("Committing transaction...")
        conn.commit()
        logging.info("===== SENTIMENT FLOW PIPELINE FINISHED SUCCESSFULLY =====")
            
    except Exception as e:
        logging.critical(f"Pipeline failed critically: {e}", exc_info=True)
        if conn:
            logging.warning("Rolling back transaction...")
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")
