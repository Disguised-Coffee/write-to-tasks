import agent
import filetracker

import logging
logging.basicConfig(level=logging.INFO)

# server dependencies
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

app = FastAPI(lifespan=filetracker.lifespan)

@app.get("/")
def root():
    return "This is the Write to Tasks API. Use the /generate endpoint to generate content."

@app.post("/generate")
def generate(request: GenerateRequest):
    creds = agent.get_credentials()
    if creds is None:
        raise HTTPException(status_code=500, detail="Google API credentials not found. Please authenticate with the Google API before using this feature!")
    resp = agent.generate_content(request.prompt)
    if("error" in resp):
        raise HTTPException(status_code=500, detail=resp["error"])
    return resp

@app.get("/status")
def status():
    return {"status": "healthy"}

if __name__ == "__main__":
    # try to authenticate with the Google API to ensure credentials are set up correctly
    agent.test_credentials()
    
    # Run the server with hot reload for development
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
