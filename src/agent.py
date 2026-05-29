import os

import logging
import asyncio

import config

import notif
from tasks import TaskItem, create_batch, get_tasks

SYSTEM_INSTRUCTION = """You are an expert Task Synchronization Agent. Your role is to analyze a user's local todo text file changes and reconcile them against their live Google Tasks data. 

CRITICAL PROTOCOLS:
1. THE STAGING ARCHITECTURE: Your tools do not modify Google Tasks directly. They insert items into a local review queue for human approval. Tell the user you are "staging" or "queuing" their requests.
2. DUPLICATE PREVENTION: Before staging a creation, scan the provided live task list thoroughly. If a task with the same core semantic intent already exists, DO NOT create a new one.
3. ID MAPPING FOR UPDATES: If an item in the text file matches an existing live task but has a modified title, due date, or description, you must extract the alphanumeric string inside the `[ID: ...]` block and pass it as the `google_task_id` to the update tool.
4. PARTIAL UPDATES ONLY: When invoking the update tool, pass ONLY the arguments that have explicitly changed. Leave arguments as None if they were not modified."""

INSERT_TASK_INSTRUCTION = """### LIVE GOOGLE TASKS CONTEXT
The following list represents the active items currently present on the user's Google Account. The value inside `[ID: ...]` is the unique identifier you must use for updates.

{current_tasks}

----------------------------------------------------------------------
{next}
"""

TASK_FILE_INSTRUCTION = """### RECENT FILE CHANGE HIGHLIGHTS
The file watcher detected the following explicit changes on the last file-save event:
{modification_note}

----------------------------------------------------------------------

### FULL FILE SOURCE OF TRUTH
Below is the entire, up-to-date state of the user's local todo file:
{full_file_content}

----------------------------------------------------------------------
### EVALUATION ASSIGNMENT
Cross-reference the modifications and full file content against the live Google Tasks context. 
- If a modification describes a brand-new task, use the `create_google_task` tool.
- If a modification alters a task that already exists in the live context, extract its ID and use the `update_google_task` tool with only the altered fields.
- If no actionable changes are required, explain that everything is up to date."""

TEXT_PROMPT_INSTRUCTION = """### USER PROMPT REQUEST
The user provided the following prompt:
{prompt}----------------------------------------------------------------------
### EVALUATION ASSIGNMENT
Cross-reference the prompt against the live Google Tasks context. 
- If a modification describes a brand-new task, use the `create_google_task` tool.
- If a modification alters a task that already exists in the live context, extract its ID and use the `update_google_task` tool with only the altered fields.
- If no actionable changes are required, explain that everything is up to date."""

# Gemini API key setup
GOOGLE_API_KEY = config.get("google_api_token", None)
if GOOGLE_API_KEY is None:
    notif.send_error_notif(
        title="Configuration Error: Missing API Key",
        message="Google API token not found in configuration. Please set your Google Gemini API token before generating content.",
        # on click, we should open our web interface where the user can input their API key into the configuration page
        #  []
        on_click_callback=lambda: ()
    )
    logging.error("GOOGLE_API_KEY environment variable is not set. Please set it to your Google API key to enable task synchronization!")

    # raise ValueError("GOOGLE_API_KEY environment variable is not set!")

from google import genai
from google.genai import types

client = genai.Client() # Initialize the Gemini API client with the API key from the environment variable
creds = None

TASK_IDS = [] # for ensuring response from Gemini contains correct task IDs after creation when using update_google_tasks

def generate_content(stimulus:dict) -> dict:
    """Generate content using the Gemini API based on the provided prompt

    Args:
        - stimulus (dict): A dictionary containing the following keys under 2 scenarios:
            1): When generating content based on a user's prompt from the frontend:
                - prompt (str): The user's prompt or the modification note from the file watcher to generate. 
            2): When generating content based on a file change detected by the file watcher:
                - full_file_content (str): The entire content of the user's local todo file, which can be used as context for generating tasks
                - modification_note (str): A note describing the specific changes detected in the user's local todo
        
    """
    # check api key before generating content
    if config.get("google_api_token", None) is None:
        logging.error("Google API token not found in configuration. Cannot generate content without API token.")
        return {"error": "Google API token not found in configuration. Please set your Google Gemini API token before generating content."}
    
    # get current Google tasks, and record IDs for checking later
    get_tasks_response = get_tasks()
    current_tasks_str = ""
    if get_tasks_response["status"] == "error":
        logging.error(f"Error retrieving tasks before generating content from local cache")
        return {"error": f"Error retrieving tasks before generating content from local cache"}
    else:
        # we can populate current_tasks
        global TASK_IDS
        TASK_IDS = [task["task_id"] for task in get_tasks_response["cached"]]
        tasks = get_tasks_response["cached"]
        # logging.info(f"Current tasks in Google Tasks: {tasks}")
        current_tasks_str += "\n".join(
                                [f"- [ID:{task['task_id']}] {task['title']} (due_date: {task['due_date'] if task['due_date'] else 'Not set'}, description: {task['description'] if task['description'] else 'Not set'})" for task in tasks]
            )
    
    # there are 2 prompt scenarios for generating content:
    # 1) The user is asking the agent to generate tasks based on a text prompt
    # 2) File watcher detected a change in the user's local todo file
    prompt = ""
    if("prompt" not in stimulus):
        prompt = INSERT_TASK_INSTRUCTION.format(current_tasks=current_tasks_str, 
                                                next=TASK_FILE_INSTRUCTION.format(
                                                    modification_note=stimulus.get("modification_note", "No modifications detected."), 
                                                    full_file_content=stimulus.get("full_file_content", "No file content provided.")
                                                    )
                                                )
    else:
        logging.info(f"Received prompt: {stimulus['prompt']}")
        prompt = INSERT_TASK_INSTRUCTION.format(current_tasks=current_tasks_str, 
                                                next=TEXT_PROMPT_INSTRUCTION.format(prompt=stimulus["prompt"])
                                                )
    try:
        logging.info("Generating content...")
        response = client.models.generate_content(
            model="gemma-4-31b-it", # "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                tools=[create_google_tasks, update_google_tasks],
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
    #         "title": "Buy more infinite groceries",
    #         "due_date": "2024-12-01T17:00:00Z",
    #         "description": "peace and love",
    #         "google_task_id": "Z0J5dU9mbUxGZXQ1R3ZBaw"
    #     },
    # ]
    #
    # create_google_tasks([TaskItem(**item) for item in tasks_data]) # Create a new task in Google Tasks based on the generated content from Gemini
    # update_google_tasks([TaskItem(**item) for item in tasks_data]) # Update the task in Google Tasks based on the generated content from Gemini (make sure to include the correct google_task_id for updates!)
    #
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

    Each TaskItem has the following structure for this function:
        - title (str): The title of the task to be created in Google Tasks. Required.
        - due_date (str | None): The due date for the task in RFC 3339 format (e.g., "2024-07-01T17:00:00Z").
        - description (str | None): A description for the task.

    Args:
        task_items (list[tasks.TaskItem]): A list of TaskItem objects containing the task details.
    """
    # we don't want to a database query to interfere with the responsiveness of the agent, so we'll run the query in a separate thread using asyncio
    asyncio.run(create_batch(task_items, action="create"))

    return {"status": "queued", "message": f"Tasks '{[item.title for item in task_items]}' are now being processed (pending user approval)."}

def update_google_tasks(task_items: list[TaskItem]) -> dict:
    """
    Queries the Google Tasks API to update existing tasks with the given titles, due dates, and optional descriptions.
    Use this tool whenever the user explicitly asks to update or modify existing tasks in Google Tasks.
    If a argument is not provided (e.g. no title, or no due date), it will not be updated and will keep its value in Google Tasks!

    Each TaskItem has the following structure for this function:
        - title (str | None): The title of the task to be updated in Google Tasks.
        - due_date (str | None): The new due date for the task in RFC 3339 format (e.g., "2024-07-01T17:00:00Z").
        - description (str | None): A new description for the task.
        - google_task_id (str): The ID of the existing task in Google Tasks that you want to update. This is necessary to identify which task to update.
    Args:
        task_items (list[TaskItem]): A list of TaskItem objects containing the updated task details.
    """
    # check that google_task_id is provided AND are accurate for all task items, otherwise we won't know which tasks to update in Google Tasks
    for item in task_items:
        if not item.google_task_id:
            logging.error(f"Task '{item.title}' is missing 'google_task_id', which is required for updating tasks.")
            return {"status": "error", "message": f"Task '{item.title}' is missing 'google_task_id', which is required for updating tasks."}
        if item.google_task_id not in TASK_IDS:
            logging.error(f"Task '{item.title}' has 'google_task_id' {item.google_task_id} which does not match any existing task IDs!")
            return {"status": "error", "message": f"Task '{item.title}' has 'google_task_id' {item.google_task_id} which does not match any existing task IDs!"}
        
    asyncio.run(create_batch(task_items, action="update"))
    return {"status": "queued", "message": f"Tasks '{[item.title for item in task_items]}' are now being processed (pending user approval)."}

if __name__ == "__main__":
    from tasks import test_credentials
    logging.basicConfig(level=logging.INFO)
    logging.info("Run main.py to start the server. This script is not intended to run directly.")
    test_credentials()