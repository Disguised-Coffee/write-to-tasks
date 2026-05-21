import os
import dotenv
dotenv.load_dotenv()
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google Tasks API client setup
SCOPES = ["https://www.googleapis.com/auth/tasks"] # Scope for write access to Google Tasks

SYSTEM_INSTRUCTION = """
                  You are a task master assistant that helps users create tasks in Google Tasks based on their input. 
                  You will receive a prompt from the user describing a task they want to create, and you 
                  will use the provided tool to create the task in Google Tasks. Always use the provided tool to create tasks, 
                  and do not attempt to create tasks without using the tool. When creating a task, provide a title and an optional
                  due date if specified by the user. The due date should be in the RFC3339 format 'YYYY-MM-DDTHH:MM:SS.SSSZ'.
                  """

# Gemini API key setup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)
if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

TASKLIST_ID = os.getenv("TASKLIST_ID", "@default") # Use the default task list if not specified

from google import genai
from google.genai import types

client = genai.Client() # Initialize the Gemini API client with the API key from the environment variable
creds = None

def generate_content(prompt:str) -> dict:
    """Generate content using the Gemini API based on the provided prompt"""
    print(f"Received prompt: {prompt}")
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
    # create_google_task("Test Task from LLM Agent", "2024-12-31T23:59:00.000Z")
    # return {"message": "Task creation attempted. Check logs for details."}


# Tools for LLM agents
def create_google_task(title: str, due_date: str | None, description: str | None = None) -> dict:    
    """Handle the creation of a Google Task by LLM agent"""
    logging.info(f"Executing Google API call: Creating task '{title}' due on {due_date}")

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    creds = get_credentials()
    if not creds:
        logging.error("Google API credentials not found. Please authenticate with the Google API before using this tool.")
        return {"status": "error", "error": "Google API credentials not found. Please authenticate with the Google API before using this tool."}
    try:
        service = build("tasks", "v1", credentials=creds)

        service.tasks().insert(
            tasklist=TASKLIST_ID,
            body={
                "title": title,
                "notes": description if description else "", # Add description as notes if provided
                "due": due_date # need to transform the due date into RFC3339 format if provided, e.g. "2024-12-31T23:59:00.000Z"
            }
        ).execute()
        logging.info(f"Task '{title}' created successfully in Google Tasks with due date {due_date}")
        return {"status": "success", "task_title": title}

    except HttpError as err:
        logging.error(f"Error authenticating with Google API: {err}")
        print(err)
        return {"status": "error", "error": "Error creating task: Possibly an authentication issue with the Google API."}
    

def test_credentials():
    """Test Google API credentials by attempting to access the specified task list"""
    logging.debug("Testing Google API credentials...")
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    creds = None
    logging.debug("CWD: " + os.getcwd())
    if os.path.exists("token.json.env"):
        creds = Credentials.from_authorized_user_file("token.json.env", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json.env", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json.env", "w") as token:
            token.write(creds.to_json())
    try:
        service = build("tasks", "v1", credentials=creds)
        service.tasklists().get(tasklist=TASKLIST_ID).execute() # Try to access the specified task list to verify credentials and permissions
        logging.info("Google API credentials are valid. Starting server...")
    except HttpError as err:
        logging.error(f"Error authenticating with Google API: {err}")
        raise err

def get_credentials() -> Credentials | None:
    """Check if valid Google API credentials are available"""
    if os.path.exists("token.json.env"):
        creds = Credentials.from_authorized_user_file("token.json.env", SCOPES)
        return creds
    return None