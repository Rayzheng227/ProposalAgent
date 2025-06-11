import sqlite3
import json
import time
import os
import logging

# Define the path for the cache database in the project root
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cache.db')
# Set a default Time-To-Live for cache entries to 7 days
DEFAULT_TTL = 86400 * 7  # 7 days in seconds

def init_cache_db():
    """Initializes the SQLite database and creates the cache table if it doesn't exist."""
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()
        logging.info(f"Cache database initialized at {CACHE_DB_PATH}")
    except sqlite3.Error as e:
        logging.error(f"Database error during cache initialization: {e}")

def get_from_cache(key: str) -> any:
    """Retrieves a value from the cache if the key exists and has not expired."""
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value, timestamp FROM cache WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                value_json, timestamp = result
                if time.time() - timestamp < DEFAULT_TTL:
                    logging.info(f"CACHE HIT for key: {key[:50]}...")
                    return json.loads(value_json)
                else:
                    logging.info(f"CACHE EXPIRED for key: {key[:50]}...")
                    # Atomically delete the expired key
                    cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
    except (sqlite3.Error, json.JSONDecodeError) as e:
        logging.error(f"Error getting from cache for key {key}: {e}")
    
    logging.info(f"CACHE MISS for key: {key[:50]}...")
    return None

def set_to_cache(key: str, value: any):
    """Sets a key-value pair in the cache with the current timestamp."""
    try:
        value_json = json.dumps(value)
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            # Use REPLACE to handle both INSERT and UPDATE atomically
            cursor.execute(
                "REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                (key, value_json, time.time())
            )
            conn.commit()
        logging.info(f"CACHE SET for key: {key[:50]}...")
    except (sqlite3.Error, TypeError) as e:
        logging.error(f"Error setting cache for key {key}: {e}")

# Initialize the database when the module is first imported.
# This ensures it's ready before any function is called.
init_cache_db() 