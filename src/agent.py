import os
import dotenv
dotenv.load_dotenv()
import typing

import logging

# Google Tasks API client setup

# Gemini API key setup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)
if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

from google import genai
from google.genai import types

client = genai.Client()

def generate_content(prompt:str) -> dict:
    print(f"Received prompt: {prompt}")
    try:
        logging.info("Generating content...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                tools=[create_google_task],
                # automatic_function_calling=types.AutomaticFunctionCallingConfig(disabled=False) # Not needed, as the SDK will automatically call the function when the response contains a function call
            )
        )

        logging.info(f"Generated content: {response.text}")

        return {"message": response.text}
    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return {"error": str(e)}
    


# Tools for LLM agents
def create_google_task(title: str, due_date: str | None):    
    """Handle the creation of a Google Task by LLM agent"""
    print(f"Executing Google API call: Creating task '{title}' due on {due_date}")
    # (Google API client code goes here)
    return {"status": "success", "task_title": title}