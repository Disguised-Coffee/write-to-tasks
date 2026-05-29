"""
Main point of entry for this application, responsible for initializing the server 
and defining API endpoints for generating content, binding file paths, and managing tasks.

Endpoints:
- GET /: Basic endpoint to verify the server is running.
- POST /generate: Accepts a prompt and returns generated content based on that prompt.
- POST /bind: Accepts a file path to track for changes.
- GET /status: Health check endpoint to verify the server is healthy.
- POST /action/{action}: Endpoint for handling approve/deny actions on created tasks.
- GET /pending: Endpoint for retrieving a list of pending batches that require user approval.
"""

import logging

import config
if(config.IS_DEV):
    logging.basicConfig(level=logging.INFO)
    logging.debug("Running in development mode with verbose logging enabled.")

config.load_user_config()

import agent
import filetracker
import tasks

# server dependencies
from pydantic import BaseModel
class GenerateRequest(BaseModel):
    prompt: str

class BindRequest(BaseModel):
    """Request body for binding a file path to track. Will be overhauled later."""
    file_path: str

class ConfigRequest(BaseModel):
    """Request body for updating configuration settings - all fields are optional to support partial updates."""
    file_to_check: str | None = None
    tasklist_id: str | None = None
    google_api_token: str | None = None
    file_tracker_enabled: bool | None = None

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
app = FastAPI(lifespan=filetracker.lifespan)

# Mount static files
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
def root():
    """Serve the web interface"""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"), media_type="text/html")

@app.get("/config")
def get_config():
    """Get the current configuration"""
    return {
        "file_to_check": config.get("file_to_check", None),
        "tasklist_id": config.get("tasklist_id", "@default"),
        "file_tracker_set": config.get("file_tracker_set", False),
        "google_api_token": config.get("google_api_token", None) is not None,
    }

@app.post("/config")
def update_config(request: ConfigRequest):
    """Update configuration settings - only updates fields that are provided in the request"""
    try:
        # Update API token only if provided
        if request.google_api_token is not None:
            config.set("google_api_token", request.google_api_token)
        
        # Update tasklist ID only if provided
        if request.tasklist_id is not None:
            config.set("tasklist_id", request.tasklist_id)
        
        # Handle file tracker settings only if explicitly provided
        if request.file_tracker_enabled is not None:
            if request.file_tracker_enabled:
                # Only set file tracker if a file path is provided or already exists
                file_to_check = request.file_to_check if request.file_to_check is not None else config.get("file_to_check")
                if file_to_check:
                    config.set("file_to_check", file_to_check)
                    resp = filetracker.set_file_to_tracked(file_to_check)
                    if not resp:
                        return {"error": f"Failed to set file to track: {file_to_check}. Check logs for details."}
                    config.set("file_tracker_set", True)
                else:
                    return {"error": "File path is required when enabling file monitoring."}
            else:
                # Disable file tracking
                config.set("file_tracker_set", False)
        
        # Update file path if provided (independent of file tracker state)
        if request.file_to_check is not None:
            config.set("file_to_check", request.file_to_check)
            # Only attempt to track if file monitoring is enabled or being enabled
            if config.get("file_tracker_set", False) or request.file_tracker_enabled:
                resp = filetracker.set_file_to_tracked(request.file_to_check)
                if not resp:
                    return {"error": f"Failed to set file to track: {request.file_to_check}. Check logs for details."}
        
        return {
            "message": "Configuration updated successfully",
            "file_to_check": config.get("file_to_check"),
            "tasklist_id": config.get("tasklist_id", "@default"),
            "file_tracker_set": config.get("file_tracker_set", False),
            "google_api_token": "***" if config.get("google_api_token") else None
        }
    except Exception as e:
        logging.error(f"Error updating config: {e}")
        return {"error": f"Error updating config: {e}"}

@app.post("/generate")
def generate(request: GenerateRequest):
    """Endpoint for generating content based on a user prompt. This is currently used for generating Google Tasks API calls based on user modifications to their file, but it can be used for other things in the future as well."""
    creds = tasks.get_credentials()
    if creds is None:
        raise HTTPException(status_code=500, detail="Google API credentials not found. Please authenticate with the Google API before using this feature!")
    resp = agent.generate_content({"prompt" : request.prompt})
    if("error" in resp):
        raise HTTPException(status_code=500, detail=resp["error"])
    return resp

@app.post("/bind")
def bind(request: BindRequest):
    """Sets file path to track. Maybe be replaced with a more general "config" endpoint in the future if we want to allow users to set other configuration variables through the API as well."""
    try:
        resp = filetracker.set_file_to_tracked(request.file_path)
        if resp:
            return {"message": f"File tracker is now watching {request.file_path} for changes."}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to set file to track: {request.file_path}. Check logs for details.")
    except Exception as e:
        logging.error(f"Error setting file to track: {e}")
        raise HTTPException(status_code=500, detail=f"Error setting file to track: {e}")

@app.get("/status")
def status():
    """Health check endpoint to verify the server is healthy."""
    return {"status": "healthy"}

# we'll also make a general-purpose approve/deny endpoint for allowing/disallowing created "batch jobs" into Google Tasks
@app.post("/action/{action}")
def action(action: str, task_id: str | None = None):
    """
    Endpoint for handling approve/deny actions on created tasks
    
    Parameters:
        - action: The action to perform, either "approve", "deny", or "clear"
        - task_id: The ID of the task batch to approve or deny. Not required for "clear" action.
    """
    try:
        resp = None
        match action:
            case "approve":
                if not task_id or not task_id.isdigit():
                    raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid task_id. Must be a numeric string."})
                resp = tasks.approve_batch(int(task_id))
                if resp.get("error"):
                    raise HTTPException(status_code=500, detail={"status": "error", "message": resp["error"]})
                return {"status": "success", "message": f"Task batch {task_id} approved and added to Google Tasks."}
            case "deny":
                if not task_id or not task_id.isdigit():
                    raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid task_id. Must be a numeric string."})
                resp = tasks.reject_batch(int(task_id))
                if resp.get("error"):
                    raise HTTPException(status_code=500, detail={"status": "error", "message": resp["error"]})
                return {"status": "success", "message": f"Task batch {task_id} denied and discarded."}
            case "clear":
                logging.warning("Clearing all pending batches as per 'clear' action request. This will reject all pending batches.")
                resp = tasks.clear_pending_batches()
                if resp.get("error"):
                    raise HTTPException(status_code=500, detail={"status": "error", "message": resp["error"]})
                return {"status": "success", "message": "All pending batches have been cleared (rejected)."}
            case _:
                raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid action. Must be 'approve', 'deny', or 'clear'."})
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error processing action '{action}' for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail={"status": "error", "message": f"Error processing action: {e}"})
    

@app.get("/pending")
def pending():
    """Endpoint for retrieving a list of pending batches that require user approval"""
    try:
        pending = tasks.get_pending_batches()
        return {"pending_batches": pending}
    except Exception as e:
        logging.error(f"Error retrieving pending batches: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving pending batches: {e}")

@app.get("/tasks")
def get_tasks():
    """Endpoint for retrieving the current list of tasks from our cache (which is updated whenever a batch is approved)"""
    try:
        tasks_data = tasks.get_tasks()
        if tasks_data.get("status") == "error":
            raise HTTPException(status_code=500, detail=tasks_data.get("error"))
        return {"last_update": config.get("most_recent_check", None), "tasks": tasks_data.get("cached", [])}
    except Exception as e:
        logging.error(f"Error retrieving tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving tasks: {e}")

@app.get("/refresh")
def refresh_tasks(force: bool = False):
    """Endpoint for manually refreshing our cache of Google Tasks without needing to wait for the next scheduled refresh"""
    try:
        tasks.cache_google_tasks(force=force)
        return {"message": "Tasks cache refresh has been queried!"}
    except Exception as e:
        logging.error(f"Error refreshing tasks cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error refreshing tasks cache: {e}")

@app.get("/get_tasklists")
def get_tasklists():
    """Endpoint for retrieving the list of task lists from Google Tasks"""
    try:
        task_lists = tasks.get_task_lists()
        return {"task_lists": task_lists}
    except Exception as e:
        logging.error(f"Error retrieving task lists: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving task lists: {e}")

def main():
    # try to authenticate with the Google API to ensure credentials are set up correctly
    tasks.test_credentials()
    tasks.init_db()
    tasks.cache_google_tasks()

    if(config.IS_DEV):
        logging.debug("Starting server in development mode with hot reload...")
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    else:    
        # Run the server with hot reload for development
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()