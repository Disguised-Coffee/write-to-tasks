import agent
import filetracker
import dotenv
dotenv.load_dotenv()
import os

import logging

import tasks
logging.basicConfig(level=logging.DEBUG)

# server dependencies
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

class BindRequest(BaseModel):
    file_path: str

app = FastAPI(lifespan=filetracker.lifespan)

@app.get("/")
def root():
    return "This is the Write to Tasks API. Use the /generate endpoint to generate content."

@app.post("/generate")
def generate(request: GenerateRequest):
    creds = tasks.get_credentials()
    if creds is None:
        raise HTTPException(status_code=500, detail="Google API credentials not found. Please authenticate with the Google API before using this feature!")
    resp = agent.generate_content(request.prompt)
    if("error" in resp):
        raise HTTPException(status_code=500, detail=resp["error"])
    return resp

@app.post("/bind")
def bind(request: BindRequest):
    """Sets file path to track"""
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
                return {"message": "All pending batches have been cleared (rejected)."}
            case _:
                raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'.")
        if(resp.get("error")):
            raise HTTPException(status_code=500, detail=resp["error"])
        return {"message": f"Action '{action}' has been processed for task batch {task_id}."}
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

if __name__ == "__main__":
    # try to authenticate with the Google API to ensure credentials are set up correctly
    tasks.test_credentials()
    tasks.init_db()
    tasks.cache_google_tasks()

    print(tasks.get_tasks())

    if (os.getenv("DEV_SERVER", "False").lower() == "true"):
        logging.debug("Starting server in development mode with hot reload...")
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    else:    
        # Run the server with hot reload for development
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
