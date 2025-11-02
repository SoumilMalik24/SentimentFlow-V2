from src.pipeline import main_pipeline
from src.core.logger import logging
import sys

if __name__ == "__main__":
    try:
        logging.info("====================================")
        logging.info("STARTING PIPELINE RUN FROM main.py")
        logging.info("====================================")
        
        # Call the main pipeline function
        main_pipeline()
        
        logging.info("====================================")
        logging.info("PIPELINE RUN COMPLETED SUCCESSFULLY")
        logging.info("====================================")
        
    except Exception as e:
        logging.critical(f"Pipeline failed with an unhandled exception: {e}", exc_info=True)
        sys.exit(1)