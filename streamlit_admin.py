import streamlit as st
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from src.core.logger import logging
    from src.utils import db_utils
    from src.utils import text_utils
except ImportError as e:
    st.error(f"Failed to import project modules: {e}")
    st.error("Please make sure you are running streamlit from the project's root directory.")
    st.stop()

# Page config
st.set_page_config(layout="wide", page_title="Startup Admin")

# --- (Caching) ---
@st.cache_data(ttl=600)
def get_sectors():
    """
    Fetches all sectors from the DB for the dropdown.
    """
    logging.info("Caching sector list...")
    conn = None
    try:
        conn = db_utils.get_connection()
        sectors = db_utils.fetch_all_sectors(conn)
        return sectors
    except Exception as e:
        st.error(f"Failed to fetch sectors: {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- (Helper Functions) ---
def process_startup(startup, sector_name_to_id, conn):
    """
    Processes a single startup dict (from JSON) and upserts it.
    Returns True on success, False on failure.
    """
    name = startup.get("name")
    sector_name = startup.get("sector")
    description = startup.get("description")

    if not name or not sector_name or not description:
        st.warning(f"Skipping startup: `{name or 'Unknown'}` - Missing name, sector, or description.")
        return False

    sector_id = sector_name_to_id.get(sector_name)
    if not sector_id:
        st.warning(f"Skipping startup: `{name}` - Sector '{sector_name}' not found in DB.")
        return False

    startup_id = text_utils.generate_startup_id(name, str(sector_id))
    
    startup_data = {
        "id": startup_id,
        "name": name,
        "sectorId": sector_id,
        "description": description,
        "imageUrl": startup.get("imageUrl", ""),
        "findingKeywords": startup.get("keywords", []) # Key in JSON is 'keywords'
    }

    db_utils.upsert_startup(conn, startup_data)
    return True

# --- (Main App) ---
st.title("Startup Admin Dashboard")
st.caption("Add or update startups in the SentimentFlow database.")

# Load sector data once
sectors = get_sectors()
if not sectors:
    st.error("No sectors found in database. Please run `scripts/seed_sectors.py` first.")
    st.stop()

sector_names = [s['name'] for s in sectors]
sector_name_to_id = {s['name']: s['id'] for s in sectors}


# --- (Layout) ---
tab1, tab2 = st.tabs(["Add Single Startup", "Bulk Upload JSON"])

# === TAB 1: Add Single Startup ===
with tab1:
    st.header("Add a Single Startup")
    st.markdown("Use this form to add or update one startup. The `Name` and `Sector` are used to create a unique ID, so updating will overwrite existing entries with the same ID.")
    
    with st.form("single_startup_form"):
        st.subheader("Required Information")
        name = st.text_input("Startup Name*")
        sector_name = st.selectbox("Sector*", options=sector_names)
        description = st.text_area("Description*")

        # Optional fields
        st.subheader("Optional Information")
        keywords_str = st.text_input("Finding Keywords (comma-separated)", help="e.g., food delivery, quick commerce, instamart")
        image_url = st.text_input("Image URL")

        submitted = st.form_submit_button("Add / Update Startup")

    if submitted:
        if not name or not sector_name or not description:
            st.error("Please fill in all required fields: Name, Sector, and Description.")
        else:
            with st.spinner("Processing..."):
                conn = None
                try:
                    conn = db_utils.get_connection()
                    
                    sector_id = sector_name_to_id.get(sector_name)
                    
                    keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
                    
                    startup_id = text_utils.generate_startup_id(name, str(sector_id))

                    startup_data = {
                        "id": startup_id,
                        "name": name,
                        "sectorId": sector_id,
                        "description": description,
                        "imageUrl": image_url,
                        "findingKeywords": keywords_list
                    }

                    db_utils.upsert_startup(conn, startup_data)
                    conn.commit()
                    
                    st.success(f"Successfully upserted startup: **{name}**")
                    st.balloons()
                    
                    st.cache_data.clear()

                except Exception as e:
                    if conn: conn.rollback()
                    st.error(f"An error occurred: {e}")
                finally:
                    if conn: conn.close()

# === TAB 2: Bulk Upload JSON ===
with tab2:
    st.header("Bulk Upload Startups")
    st.markdown("Upload a JSON file containing an array of startup objects. This is useful for migrating or adding many startups at once.")

    with st.expander("Click to see example JSON format"):
        st.code("""
[
  {
    "name": "Swiggy",
    "sector": "E-commerce",
    "description": "An Indian online food ordering and delivery platform.",
    "keywords": ["food delivery", "quick commerce"],
    "imageUrl": "https://example.com/swiggy_logo.png"
  },
  {
    "name": "Zomato",
    "sector": "E-commerce",
    "description": "Another food delivery platform.",
    "keywords": ["food", "dining out", "zomato gold"],
    "imageUrl": ""
  }
]
        """, language="json")

    uploaded_file = st.file_uploader("Upload JSON file", type=["json"])

    if uploaded_file is not None:
        if st.button("Process JSON File"):
            conn = None
            try:
                try:
                    startups_list = json.load(uploaded_file)
                    if not isinstance(startups_list, list):
                        st.error("Invalid JSON format: File does not contain a JSON list (array).")
                        st.stop()
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON file: {e}")
                    st.stop()

                with st.spinner(f"Processing {len(startups_list)} startups..."):
                    conn = db_utils.get_connection()
                    success_count = 0
                    
                    progress_bar = st.progress(0.0, "Starting batch...")
                    
                    for i, startup in enumerate(startups_list):
                        if process_startup(startup, sector_name_to_id, conn):
                            success_count += 1
                        
                        progress_bar.progress((i + 1) / len(startups_list), f"Processing '{startup.get('name', '...')}'")

                    conn.commit()
                    
                    st.success(f"Batch processing complete! Successfully upserted {success_count} out of {len(startups_list)} startups.")
                    st.cache_data.clear()

            except Exception as e:
                if conn: conn.rollback()
                st.error(f"An error occurred: {e}")
            finally:
                if conn: conn.close()
