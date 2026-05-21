from contextlib import asynccontextmanager
import logging
from threading import Timer
from fastapi import FastAPI
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Allow us to get difference from a file's previous content to its new content, so we can be smarter about what to update in Google Tasks instead of just wiping and re-adding everything every time.
import difflib

# file to track for changes
WATCHED_FILE = "./todo.txt"

# 1. Define your file save logic just like before
class FileSaveHandler(FileSystemEventHandler):
    def __init__(self, file_path):
        self.debounce_timer = None
        self.file_path = file_path
        # Keep a cached list of the file lines in memory
        self.file_cache = self.load_file_lines()

    def load_file_lines(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return f.readlines()
        except FileNotFoundError:
            return []
        
    def check_for_changes(self):
    # 1. Read the fresh state of the file after the save event
        fresh_lines = self.load_file_lines()
        
        # 2. Use Python's built-in difflib to find exactly what lines were added
        diff = difflib.ndiff(self.file_cache, fresh_lines)
        # print([a for a in diff]) # For debugging: See the diff output in the console
        added_lines = [line[2:].strip() for line in diff if line.startswith('+ ')]
        
        # 3. Update the memory cache so it's ready for the next save
        self.file_cache = fresh_lines
        
        # 4. Format a nice "modification note" for Gemini
        if added_lines:
            modification_note = f"User added the following lines:\n" + "\n".join([f"- {l}" for l in added_lines])
            full_file_content = "".join(fresh_lines)
            
            # Send BOTH variables to your FastAPI /generate endpoint
            self.send_to_fastapi(full_file_content, modification_note) 
    
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("todo.txt"):
            logging.info("💾 Save detected inside FastAPI handler!")
            # (Your debounced Gemini/Google Tasks logic goes here)
            self.trigger_debounced_sync()
    
    def trigger_debounced_sync(self):
        # 3. If a save event happens while we are already waiting, cancel the old timer
        if self.debounce_timer is not None:
            self.debounce_timer.cancel()

        # 4. Start a fresh 1.5-second countdown. 
        # If no more changes happen in 1.5 seconds, execute 'send_to_fastapi'
        self.debounce_timer = Timer(1.5, self.check_for_changes)
        self.debounce_timer.start()
    
    def send_to_fastapi(self, string_content, modification_note):
        logging.info("🚀 Settle period ended. Reading file and updating Google Tasks...")
        try:

            # Prepare payload for the FastAPI endpoint we designed earlier
            payload = {
                "file_content": string_content,
                "modification_note": modification_note,
                "existing_tasks": [] # Ideally fetch current tasks from Google first!
            }

            logging.info(f"📡 Sending content to FastAPI: {payload}")
            # we'll have to have to reformat the payload to match generate_content()'s expected input
            # this also a note to investigate context caching
            # []

        except Exception as e:
            logging.error(f"❌ Failed to sync: {e}")

# 2. Define the Lifespan Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
        Lifespan manager to handle startup and shutdown of the file watcher thread.
        
        # Be sure to pass this lifespan function to your FastAPI app like so:
        app = FastAPI(lifespan=lifespan)
    """
    # --- BEFORE SERVER STARTS ---
    logging.info("🎬 Starting up file watcher thread...")
    
    event_handler = FileSaveHandler(file_path=WATCHED_FILE)
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=False)
    
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
