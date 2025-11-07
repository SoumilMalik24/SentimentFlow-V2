import sys
from os.path import dirname, abspath

# Add the project root to the Python path
project_root = dirname(dirname(abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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

        all_startups_data = db_utils.fetch_startups_for_api(conn)
        existing_startup_ids = db_utils.fetch_startup_ids_with_sentiment(conn)
        
        if not all_startups_data:
            logging.error("No startups found in 'Startups' table. Exiting.")
            return

        # =========================================================
        # STEP 2: Build API Queries
        # =========================================================
        sector_queries = api_utils.build_sector_queries(
            all_startups_data, 
            existing_startup_ids
        )
        
        if not sector_queries:
            logging.error("No API queries could be built. Exiting.")
            return
            
        # =========================================================
        # STEP 3: Fetch and Deduplicate Articles
        # =========================================================
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
        search_engine.build_engine(all_startups_data) 

        # =========================================================
        # STEP 6: Process Articles and Analyze Sentiment (REVISED)
        # =========================================================
        
        # 1. First, find all startups mentioned in all articles (in-memory)
        logging.info("Finding all startup mentions in new articles...")
        articles_to_process = []
        for url, article_row in articles_from_db.items():
            try:
                text_to_search = f"{article_row['title']}. {article_row['content']}"
                found_startup_ids = search_engine.find_startups_in_text(text_to_search)
                
                if not found_startup_ids:
                    logging.info(f"No registered startups found in article: {article_row.get('title', 'No Title')[:30]}...")
                    continue
                    
                startups_to_analyze = [
                    info for sid in found_startup_ids 
                    if (info := search_engine.get_startup_info(sid))
                ]
                
                if startups_to_analyze:
                    # --- THIS IS THE FIX ---
                    # We append a dictionary, not a tuple
                    articles_to_process.append({
                        "article": article_row, 
                        "startups_to_analyze": startups_to_analyze
                    })
                    # --- END OF FIX ---
                    logging.info(f"Found {len(startups_to_analyze)} startups in article: {article_row.get('title', 'No Title')[:30]}...")

            except Exception as e:
                logging.error(f"Failed to find startups in article {article_row.get('url')}: {e}")

        # 2. Now, run the model ONCE for all articles in a single bulk call
        if not articles_to_process:
            logging.info("No startups found in any new articles. Pipeline complete.")
            return

        all_sentiment_records = sentiment_utils.analyze_all_articles_in_bulk(articles_to_process)

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


if __name__ == "__main__":
    # To run: python -m src.pipeline
    main_pipeline()