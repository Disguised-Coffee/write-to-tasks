from contextlib import asynccontextmanager
import logging
from threading import Timer
from fastapi import FastAPI
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import agent

import notif

FILE_PROMPT = """Create or update Google Tasks based on the following user modifications to their file. Only respond with the Google Tasks API calls needed to reflect the following changes the user made in the file:"""

logging.basicConfig(level=logging.INFO)

# Allow us to get difference from a file's previous content to its new content, so we can be smarter about what to update in Google Tasks instead of just wiping and re-adding everything every time.
import difflib

# 1. Define your file save logic just like before
class FileSaveHandler(FileSystemEventHandler):
    def __init__(self, file_path):
        self.debounce_timer = None
        self.file_path = file_path
        # Keep a cached list of the file lines in memory
        self.file_cache = self.load_file_lines()

    def load_file_lines(self):
        if not self.file_path:
            logging.warning("No file path set for FileSaveHandler. Please set the file to track before starting the server.")
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return f.readlines()
        except FileNotFoundError:
            # If the file doesn't exist yet, we'll raise a warning to our server
            # hopefully the user sees this.
            return []
        
    def check_for_changes(self):
        # Read the fresh state of the file after the save event
        fresh_lines = self.load_file_lines()
        
        # Use Python's built-in difflib to find exactly what lines were added
        diff = difflib.ndiff(self.file_cache, fresh_lines)
        added_lines = [line[2:].strip() for line in diff if line.startswith('+ ')]
        
        # 3. Update the memory cache so it's ready for the next save
        self.file_cache = fresh_lines
        
        # Format a nice "modification note" for Gemini
        # I may need figure out about this formatting, but for now let's just send a simple list of added lines.
        if added_lines:
            modification_note = f"User added the following lines:\n" + "\n".join([f"- {l}" for l in added_lines])
            full_file_content = "".join(fresh_lines)
            
            # Send BOTH variables to your FastAPI /generate endpoint
            self.send_to_agent(full_file_content, modification_note) 
    
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(self.file_path):
            logging.info("Save detected inside FastAPI handler!")
            # (Your debounced Gemini/Google Tasks logic goes here)
            self.trigger_debounced_sync()
    
    def trigger_debounced_sync(self):
        # If a save event happens while we are already waiting, cancel the old timer
        if self.debounce_timer is not None:
            self.debounce_timer.cancel()

        # If no more changes happen in 5 seconds, execute 'send_to_fastapi'
        self.debounce_timer = Timer(5, self.check_for_changes)
        self.debounce_timer.start()
    
    def send_to_agent(self, string_content, modification_note):
        logging.info("Settle period ended. Reading file and updating Google Tasks...")
        try:
            # we'll call generate_content here to parse the conten
            notif.send_notif(title="File change detected!", message="Your changes have been detected and are being processed. Check logs for details.")
            agent.generate_content({"modification_note": modification_note, "full_file_content": string_content})

        except Exception as e:
            logging.error(f"❌ Failed to sync: {e}")
    
    def set_file_to_tracked(self, file_path) -> bool:
        self.file_path = file_path
        self.file_cache = self.load_file_lines()
        # check if file exists and is readable
        config.set("file_to_check", file_path)
        
        notif.send_notif(title="File Tracker Updated", message=f"File tracker is now watching {file_path} for changes.")
        return True


# open the json figuration file and read the name of the file to track, then initialize the FileSaveHandler with that file path
# import json
import config
CONFIG_FILE = config.get("file_to_check", None)
if not CONFIG_FILE:
    logging.warning("No file to track specified in configuration. Please set 'file_to_check' to the file you want to track for changes.")

handler = FileSaveHandler(file_path=CONFIG_FILE)

# expose set_file_to_tracked so that main.py can call it to set the file path before the server starts
def set_file_to_tracked(file_path):
    return handler.set_file_to_tracked(file_path)

# 2. Define the Lifespan Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
        Lifespan manager to handle startup and shutdown of the file watcher thread.
        
        # Be sure to pass this lifespan function to your FastAPI app like so:
        app = FastAPI(lifespan=lifespan)
    """
    # --- BEFORE SERVER STARTS ---
    if(config.get("file_tracker_set", False)):
        logging.info("🎬 Starting up file watcher thread...")
        
        observer = Observer()
        observer.schedule(handler, path=".", recursive=False)
        
        # Spin up the background thread. Because FastAPI keeps running,
        # we DO NOT call observer.join() here, otherwise the server would freeze up!
        observer.start() 
        
        # The yield splits startup from shutdown
        yield 
        
        # --- BEFORE SERVER SHUTS DOWN ---
        logging.info("🛑 Shutting down file watcher thread safely...")
        observer.stop()
        
        # NOW we call join() because we want to block FastAPI from fully closing 
        # until our background thread has finished cleaning up its OS hooks.
        observer.join() 
        logging.info("✨ File watcher stopped. Goodbye!")
    else:
        logging.warning("!! File tracker is not set to track any file. File watcher thread will not start.")
        yield
