"""handle user configurations lazily"""

import os
import json
import logging

USER_CONFIG = {}

def load_user_config():
    """Load user configuration from a JSON file."""
    global USER_CONFIG
    try:
        with open("user.config.json", "r") as f:
            USER_CONFIG = json.load(f)
            logging.info("User configuration loaded successfully.")
    except FileNotFoundError:
        logging.warning("user.config.json not found. Using default configuration.")
        USER_CONFIG = {}
    except json.JSONDecodeError:
        logging.error("Invalid JSON in user.config.json. Please check the file format.")
        USER_CONFIG = {}
    except Exception as e:
        logging.error(f"Error loading user configuration: {e}")
        USER_CONFIG = {}

def get(key, default=None):
    """Get a configuration variable by key, with an optional default value."""
    return USER_CONFIG.get(key, default)

def set(key, value):
    """Set a configuration variable and save it to the JSON file."""
    USER_CONFIG[key] = value
    try:
        with open("user.config.json", "w") as f:
            json.dump(USER_CONFIG, f, indent=4)
            logging.info(f"Configuration '{key}' updated successfully.")
    except Exception as e:
        logging.error(f"Error saving user configuration: {e}")