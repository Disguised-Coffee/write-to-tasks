import os
import dotenv
dotenv.load_dotenv()
import logging
logging.basicConfig(level=logging.INFO)

import tasks

SYSTEM_INSTRUCTION = """
                  You are a task master assistant that helps users create tasks in Google Tasks based on their input. 
                  You will receive a prompt from the user describing a task they want to create, and you 
                  will use the provided tool to create the task in Google Tasks.
                  """

# Gemini API key setup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)
if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

from google import genai
from google.genai import types

client = genai.Client() # Initialize the Gemini API client with the API key from the environment variable
creds = None

def generate_content(prompt:str) -> dict:
    """Generate content using the Gemini API based on the provided prompt"""
    logging.info(f"Received prompt: {prompt}")
    try:
        logging.info("Generating content...")
        response = client.models.generate_content(
            model="gemma-4-31b-it", # "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                tools=[create_google_task],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False), # Not needed, as the SDK will automatically call the function when the response contains a function call
                system_instruction=[SYSTEM_INSTRUCTION]
            ),
        )

        logging.info(f"Generated content: {response.text}")

        return {"message": response.text}
    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return {"error": str(e)}


# Tools for LLM agents
# Note, since we are using Automatic Function Calling, the LLM agent will be given a schema
# of the create_google_task function, and will call it directly when it determines that a task should be created based on the user's prompt.
# 
# HENCE, having a proper doc string and type annotations for the create_google_task function is crucial for the LLM agent to understand how to use it correctly.
def create_google_task(title: str, due_date: str | None, description: str | None = None) -> dict:    
    """
    Queries the Google Tasks API to create a new task with the given title, due date, and optional description.
    Use this tool whenever the user explicitly asks to add, schedule, or remember a todo item.

    Args:
        title (str): The title of the task to be created.
        due_date (str | None): The due date of the task in RFC3339 format (e.g., "2024-12-31T23:59:00.000Z"). Optional.
        description (str | None): An optional description or notes for the task.
    """
    logging.info(f"Executing Google API call: Creating task '{title}' due on {due_date}")
    # call query function here
    return tasks.query_create_task(title, due_date, description)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Run main.py to start the server. This script is not intended to run directly.")
    tasks.test_credentials()