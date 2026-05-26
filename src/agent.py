import os
import dotenv
from pydantic import BaseModel
dotenv.load_dotenv()
import logging
import asyncio

from tasks import TaskItem, create_batch

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
                tools=[create_google_tasks],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False), # Not needed, as the SDK will automatically call the function when the response contains a function call
                system_instruction=[SYSTEM_INSTRUCTION]
            ),
        )

        logging.info(f"Generated content: {response.text}")

        return {"message": response.text}
    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return {"error": str(e)}
    # 
    # ---------------------------------------------------------------------------------------------------
    # Comment above and uncomment this segment below to test with mock response without calling the Gemini API
    # ---------------------------------------------------------------------------------------------------
    # 
    # tasks_data = [
    #     {
    #         "title": "Buy no groceries",
    #         "due_date": "2024-07-01T17:00:00Z",
    #         "description": "Milk, eggs, bread"
    #     },
    #     {
    #         "title": "Finish project report",
    #         "due_date": "2099-07-05T17:00:00Z",
    #         "description": "Complete the final report for the project and submit it to the manager."
    #     }
    # ]
    # create_google_tasks([tasks.TaskItem(**item) for item in tasks_data])
    # return {"message": "Content generated successfully (mock response)"}


# Tools for LLM agents
# Note, since we are using Automatic Function Calling, the LLM agent will be given a schema
# of the create_google_task function, and will call it directly when it determines that a task should be created based on the user's prompt.
# 
# HENCE, having a proper doc string and type annotations for the create_google_task function is crucial for the LLM agent to understand how to use it correctly.
def create_google_tasks(task_items: list[TaskItem]) -> dict:    
    """
    Queries the Google Tasks API to create new tasks with the given titles, due dates, and optional descriptions.
    Use this tool whenever the user explicitly asks to add, schedule, or remember todo items.

    Each TaskItem has the following structure:
        - title (str): The title of the task to be created in Google Tasks.
        - due_date (str): The due date for the task in RFC 3339 format (e.g., "2024-07-01T17:00:00Z").
        - description (str, optional): A description for the task.

    Args:
        task_items (list[tasks.TaskItem]): A list of TaskItem objects containing the task details.
    """
    # we don't want to a database query to interfere with the responsiveness of the agent, so we'll run the query in a separate thread using asyncio
    asyncio.run(create_batch(task_items))

    return {"status": "success", "message": f"Tasks '{[item.title for item in task_items]}' have been querried (pending user approval)."}

def update_google_tasks(task_items: list[TaskItem]) -> dict:
    """
    Queries the Google Tasks API to update existing tasks with the given titles, due dates, and optional descriptions.
    Use this tool whenever the user explicitly asks to update existing tasks in Google Tasks.

    Each TaskItem has the following structure:
        - title (str): The title of the task to be updated in Google Tasks.
        - due_date (str): The new due date for the task in RFC 3339 format (e.g., "2024-07-01T17:00:00Z").
        - description (str, optional): A new description for the task.
    Args:
        task_items (list[TaskItem]): A list of TaskItem objects containing the updated task details.
    """
    pass

def list_google_tasks() -> dict:
    """
    Queries the Google Tasks API to retrieve a list of existing tasks.
    Use this tool whenever the user explicitly asks to list, show, or view their existing tasks in Google Tasks.

    Returns:
        list[TaskItem]: A list of TaskItem objects containing the existing tasks with their titles, due dates, and descriptions.
    """
    # This function can be implemented similarly to create_google_tasks, but instead of creating tasks, it will query the Google Tasks API to retrieve existing tasks and return them in a structured format for the LLM agent to use in its response to the user.
    # pass
    tasks_data = [
        {
            "title": "Buy no groceries",
            "due_date": "2024-07-01T17:00:00Z",
            "description": "Milk, eggs, bread"
        },
        {
            "title": "Finish project report",
            "due_date": "2099-07-05T17:00:00Z",
            "description": "Complete the final report for the project and submit it to the manager."
        }
    ]
    return {"status": "success", "tasks": [TaskItem(**item) for item in tasks_data]}

if __name__ == "__main__":
    from tasks import test_credentials
    logging.basicConfig(level=logging.INFO)
    logging.info("Run main.py to start the server. This script is not intended to run directly.")
    test_credentials()