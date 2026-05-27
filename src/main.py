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
logging.basicConfig(level=logging.INFO)

import config
config.load_user_config()

import agent
import filetracker
import tasks

import dotenv
dotenv.load_dotenv()
import os

# server dependencies
from pydantic import BaseModel
class GenerateRequest(BaseModel):
    prompt: str
class BindRequest(BaseModel):
    """Request body for binding a file path to track. Will be overhauled later."""
    file_path: str

from fastapi import FastAPI, HTTPException
app = FastAPI(lifespan=filetracker.lifespan)

@app.get("/")
def root():
    """Basic endpoint to verify the server is running."""
    return "This is the Write to Tasks API. Use the /generate endpoint to generate content."

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

    TODO:
        - convert HTTPException details to JSON, e.g. {"status": "error", "message": "Detailed error message here"}
    """
    try:
        resp = None
        match action:
            case "approve":
                if(not task_id or not task_id.isdigit()):
                    raise HTTPException(status_code=400, detail="Invalid task_id. Must be a numeric string.")
                resp = tasks.approve_batch(int(task_id))
            case "deny":
                if(not task_id or not task_id.isdigit()):
                    raise HTTPException(status_code=400, detail="Invalid task_id. Must be a numeric string.")
                resp =  tasks.reject_batch(int(task_id))
            case "clear":
                logging.warning("Clearing all pending batches as per 'clear' action request. This will reject all pending batches.")
                resp = tasks.clear_pending_batches()
                if resp.get("error"):
                    raise HTTPException(status_code=500, detail=resp["error"])
                return HTTPException(status_code=200, detail={"status": "success","message": "All pending batches have been cleared (rejected)."})
            case _:
                raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'.")
        if(resp.get("error")):
            raise HTTPException(status_code=500, detail=resp["error"])
        return HTTPException(status_code=200, detail={"status": "success", "message": f"Action '{action}' has been processed for task batch {task_id}."})
    except Exception as e:
        logging.error(f"Error processing action for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing action for task {task_id}: {e}")
    

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

def main():
    # try to authenticate with the Google API to ensure credentials are set up correctly
    tasks.test_credentials()
    tasks.init_db()
    tasks.cache_google_tasks()

    if (os.getenv("DEV_SERVER", "False").lower() == "true"):
        logging.debug("Starting server in development mode with hot reload...")
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    else:    
        # Run the server with hot reload for development
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()