import agent
import filetracker
import dotenv
dotenv.load_dotenv()
import os

import logging

import tasks
logging.basicConfig(level=logging.INFO)

# server dependencies
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

class BindRequest(BaseModel):
    file_path: str

class ActionRequest(BaseModel):
    task_id: str # keep this as is, we may want to move to this later
    action: str  # "approve" or "deny"

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

# we'll also make a general-purpose approve/deny endpoint for allowing/disallowing created tasks into Google Tasks
@app.post("/action")
def action(request: ActionRequest):
    """Endpoint for handling approve/deny actions on created tasks"""
    try:
        if request.action == "approve":
            tasks.approve_task(int(request.task_id))
            return {"message": f"Task {request.task_id} approved and added to Google Tasks."}
        elif request.action == "deny":
            tasks.reject_task(int(request.task_id))
            return {"message": f"Task {request.task_id} denied and will not be added to Google Tasks."}
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'.")
    except Exception as e:
        logging.error(f"Error processing action for task {request.task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing action for task {request.task_id}: {e}")
    
# we should also be able to get a list of pending tasks for approval
@app.get("/pending")
def pending():
    """Endpoint for retrieving a list of pending tasks that require user approval"""
    try:
        pending = tasks.get_pending_tasks()
        return {"pending_tasks": pending}
    except Exception as e:
        logging.error(f"Error retrieving pending tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving pending tasks: {e}")

if __name__ == "__main__":
    # try to authenticate with the Google API to ensure credentials are set up correctly
    tasks.test_credentials()
    tasks.init_db()

    if (os.getenv("DEV_SERVER", "False").lower() == "true"):
        logging.debug("Starting server in development mode with hot reload...")
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    else:    
        # Run the server with hot reload for development
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
