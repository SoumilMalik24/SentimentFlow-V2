import ahocorasick
from src.utils.db_utils import get_connection
from src.core.logger import logging

# =========================================================
# GLOBAL AUTOMATON INSTANCE
# =========================================================
_startup_automaton = None
_startup_map = {}

# =========================================================
# BUILD STARTUP SEARCH ENGINE
# =========================================================
def build_startup_search_engine():
    """
    Build the Aho–Corasick automaton for startup name detection.
    Loads all startup names + IDs from the DB and builds an efficient matcher.
    """
    global _startup_automaton, _startup_map

    logging.info("Building startup search engine...")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name FROM "Startups"')
            startups = cur.fetchall()
    finally:
        conn.close()

    if not startups:
        logging.warning("No startups found in DB to build search engine.")
        return None

    automaton = ahocorasick.Automaton()
    for startup_id, startup_name in startups:
        if not startup_name:
            continue
        normalized_name = startup_name.strip().lower()
        automaton.add_word(normalized_name, startup_id)
        _startup_map[startup_id] = normalized_name

    automaton.make_automaton()
    _startup_automaton = automaton

    logging.info(f"Startup search engine built with {len(startups)} entries.")
    return automaton


# =========================================================
# DETECT STARTUPS IN TEXT
# =========================================================
def find_startups_in_text(text):
    """
    Detect all startup IDs mentioned in a given text.
    Returns a list of unique startup IDs.
    """
    global _startup_automaton
    if _startup_automaton is None:
        logging.warning("Startup search engine not built yet. Building now...")
        build_startup_search_engine()

    text_lower = text.lower()
    found_ids = set()

    for _, startup_id in _startup_automaton.iter(text_lower):
        found_ids.add(startup_id)

    return list(found_ids)


# =========================================================
# FETCH STARTUP NAME (UTILITY)
# =========================================================
def get_startup_name_by_id(startup_id):
    """
    Returns the startup name corresponding to a given ID.
    """
    return _startup_map.get(startup_id, "Unknown Startup")


# =========================================================
# REFRESH AUTOMATON (FOR NEW ENTRIES)
# =========================================================
def refresh_startup_search_engine():
    """
    Rebuilds the search engine in case new startups are added.
    """
    logging.info("Refreshing startup search engine...")
    build_startup_search_engine()
