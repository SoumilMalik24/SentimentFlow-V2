import ahocorasick
from src.core.logger import logging
from psycopg2.extras import RealDictCursor

class StartupSearch:
    """
    Manages the Aho-Corasick automaton for efficient startup detection.
    """
    def __init__(self):
        self.automaton = None
        self.startup_map = {} # {startup_id: {"id": str, "name": str}}
        logging.info("StartupSearch engine initialized.")

    def build_engine(self, conn):
        """
        Build the Aho–Corasick automaton from startups in the DB.
        """
        logging.info("Building startup search engine...")
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT id, name FROM "Startups"')
                startups = cur.fetchall()
        except Exception as e:
            logging.error(f"Failed to fetch startups for search engine: {e}")
            raise

        if not startups:
            logging.warning("No startups found in DB to build search engine.")
            self.automaton = ahocorasick.Automaton() # Empty automaton
            return

        automaton = ahocorasick.Automaton()
        for startup in startups:
            startup_id = startup['id']
            startup_name = startup['name']
            
            if not startup_name:
                continue
                
            normalized_name = startup_name.strip().lower()
            automaton.add_word(normalized_name, startup_id)
            self.startup_map[startup_id] = {
                "id": startup_id,
                "name": startup_name # Store original name for the model
            }

        automaton.make_automaton()
        self.automaton = automaton
        logging.info(f"Startup search engine built with {len(startups)} entries.")

    def find_startups_in_text(self, text: str):
        """
        Detect all startup IDs mentioned in a given text.
        Returns a set of unique startup IDs.
        """
        if self.automaton is None:
            logging.error("Search engine is not built. Call build_engine() first.")
            return set()

        text_lower = text.lower()
        found_ids = set()

        for end_index, startup_id in self.automaton.iter(text_lower):
            found_ids.add(startup_id)

        return found_ids

    def get_startup_info(self, startup_id: str):
        """
        Returns the startup info dict ({"id": str, "name": str})
        """
        return self.startup_map.get(startup_id)