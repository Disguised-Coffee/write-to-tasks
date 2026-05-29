"""handle configurations, both user and appliation"""

import os
import json
import logging

import keyring

import dotenv
dotenv.load_dotenv()

USER_CONFIG = {}

DEFAULT_CONFIG = {
    "file_to_check": "todo.txt",  # the file path that the file tracker will watch for changes
    "most_recent_check": None,  # timestamp of the most recent file check, used to prevent duplicate checks in quick succession
    "google_api_token": None,  # the API token for the agent to use when making calls to the Google Tasks API
    "tasklist_id": "@default",  # the ID of the Google Tasks tasklist to add tasks to
    "file_tracker_set": False,  # whether the file tracker has been set with a file to track yet. This is used to prevent the file tracker from trying to track changes before we have a file path to track
}

IS_DEV = os.getenv("ENV", "production") == "development"

def load_user_config():
    """Load user configuration from a JSON file."""
    global USER_CONFIG
    try:
        with open("user.config.json", "r") as f:
            temp = json.load(f)
            # validate config keys
            for key in DEFAULT_CONFIG.keys():
                # skip google api token...
                if key == "google_api_token":
                    continue
                if key not in temp:
                    logging.info(f"Configuration key '{key}' not found in user.config.json. Using default value: {DEFAULT_CONFIG[key]}")
                    temp[key] = DEFAULT_CONFIG[key]
            USER_CONFIG = temp
            logging.info("User configuration loaded successfully.")
    except FileNotFoundError:
        logging.warning("user.config.json not found. Using default configuration.")
        USER_CONFIG = DEFAULT_CONFIG.copy()

        # write file
        try:
            with open("user.config.json", "w") as f:
                json.dump(USER_CONFIG, f, indent=4)
                logging.info("Default configuration file created as user.config.json.")
        except Exception as e:
            logging.error(f"Error creating default configuration file: {e}")
    except json.JSONDecodeError:
        logging.error("Invalid JSON in user.config.json. Please check the file format.")
        USER_CONFIG = DEFAULT_CONFIG.copy()
    except Exception as e:
        logging.error(f"Error loading user configuration: {e}")
        USER_CONFIG = DEFAULT_CONFIG.copy()
    
     # because we want to use os encryption for the API key, we need a separate case
    USER_CONFIG["google_api_token"] = keyring.get_password("write-to-tasks", "google_api_token")
    if USER_CONFIG["google_api_token"] is None:
        # try the .ENV variable as a fallback
        logging.info("Google API token not found in keyring! Trying .ENV variable...")
        USER_CONFIG["google_api_token"] = os.getenv("GOOGLE_API_KEY", None)
        if USER_CONFIG["google_api_token"] is None:
            logging.error("Google API token not found! Set it using the Web Interface or use a .ENV variable. Google API calls will not work until this is set.")

def get(key, default=None):
    """Get a configuration variable by key, with an optional default value."""
    return USER_CONFIG.get(key, default)

def set(key, value):
    """Set a configuration variable and save it to the JSON file."""
    USER_CONFIG[key] = value
    # if it was the google api token, we want to save it in the keyring instead of the JSON file for security reasons
    if key == "google_api_token":
        try:
            keyring.set_password("write-to-tasks", "google_api_token", value)
            logging.info("Google API token updated successfully in keyring.")
        except Exception as e:
            logging.error(f"Error saving Google API token to keyring: {e}")
    else:
        try:
            with open("user.config.json", "w") as f:
                to_dump = USER_CONFIG.copy()
                # we don't want to save the google API token in the JSON file, so we'll remove it before dumping
                to_dump.pop("google_api_token", None)
                json.dump(to_dump, f, indent=4)
                logging.info(f"Configuration '{key}' updated successfully.")
        except Exception as e:
            logging.error(f"Error saving user configuration: {e}")