import os
import dotenv
dotenv.load_dotenv()

# Google dependencies and API key setup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)
if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

from google import genai
from google.genai import types

client = genai.Client()

import logging

def generate_content(prompt:str) -> dict:
    print(f"Received prompt: {prompt}")
    try:
        logging.info("Generating content...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                tools=[],
            )
        )

        logging.info(f"Generated content: {response.text}")

        return {"message": response.text}
    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return {"error": str(e)}
    


# Tools for LLM agents
def create_google_task(task_name: str, description: str, input_schema: dict) -> dict:
    """Handle the creation of a Google Task by LLM agent"""
    return {}