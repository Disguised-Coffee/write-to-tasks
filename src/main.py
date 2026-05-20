import logging
import agent

logging.basicConfig(level=logging.INFO)

# server dependencies
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/generate")
def generate(request: GenerateRequest):
    resp = agent.generate_content(request.prompt)
    if("error" in resp):
        raise HTTPException(status_code=500, detail=resp["error"])
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
