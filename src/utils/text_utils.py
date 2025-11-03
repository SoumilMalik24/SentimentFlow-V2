import ahocorasick
from src.core.logger import logging
import uuid
import hashlib

class StartupSearch:
    """
    Manages the Aho-Corasick automaton for efficient startup detection.
    """
    def __init__(self):
        self.automaton = None
        self.startup_map = {} # {startup_id: {"id": str, "name": str}}
        logging.info("StartupSearch engine initialized.")

    def build_engine(self, startups: list):
        """
        Build the Aho–Corasick automaton from a provided list of startups.
        
        Args:
            startups (list): A list of startup dicts, e.g.,
                             [{"id": "...", "name": "..."}, ...]
        """
        logging.info("Building startup search engine...")
        if not startups:
            logging.warning("No startups provided to build search engine.")
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

# =========================================================
# DETERMINISTIC STARTUP ID GENERATOR
# =========================================================
def generate_startup_id(name: str, sector_id: str) -> str:
    """
    Generates a deterministic, readable, unique ID based on startup name and sector ID.
    Example: swiggy-51f4a2-9f2d
    """
    base_str = f"{name.lower()}|{str(sector_id).lower()}"
    
    # You can use any fixed UUID as a namespace
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    stable_uuid = uuid.uuid5(namespace, base_str)

    short_hash = hashlib.md5(base_str.encode()).hexdigest()[:6]
    suffix = str(stable_uuid).split('-')[-1][:4]

    readable_name = name.lower().replace(" ", "-").replace(".", "")
    final_id = f"{readable_name}-{short_hash}-{suffix}"
    return final_id
