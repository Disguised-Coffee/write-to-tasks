"""
Handles interactions with Google Tasks API, including authentication and task creation/modification.

Because we want the user to approve suggested tasks from Gemini, we'll have to store them as a "Job"
where each job is a suggested task creation/modification that the user can approve or reject. Once 
the user approves a job, we can then call the add_task function to create/modify the task in Google Tasks.
"""
import os
import logging

import notif
logging.basicConfig(level=logging.INFO)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# Google Tasks API client setup
SCOPES = ["https://www.googleapis.com/auth/tasks"] # Scope for write access to Google Tasks
TASKLIST_ID = os.getenv("TASKLIST_ID", "@default") # Use the default task list if not specified

from typing import Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select, Relationship

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    due_date: Optional[str] = None
    description: Optional[str] = None
    google_task_id: Optional[str] = None # This will store the ID of the task in Google Tasks once it's created

class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id")  # ← Add this
    task: Task = Relationship()
    action: str
    batch_id: Optional[int] = Field(default=None, foreign_key="batch.id")
    batch: Optional["Batch"] = Relationship(back_populates="tasks")


class Batch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tasks: list[Job] = Relationship(back_populates="batch")
    status: str = "pending" # pending, approved, rejected. We likely won't need the rejected status, since when the user acts on a job, we can just delete it from the database

SQLITE_URL = "sqlite:///tasks.db"
engine = create_engine(SQLITE_URL)

def init_db():
    # This automatically generates the tables based on your classes above
    SQLModel.metadata.create_all(engine)

def check_db():
    """Check if the database is set up correctly by trying to query the Task table."""
    try:
        with Session(engine) as session:
            session.exec(select(Task)).first()
        logging.debug("Database connection successful and Task table is accessible.")
    except Exception as e:
        logging.error(f"Database connection failed or Task table is not accessible: {e}")


async def query_create_task(title: str, due_date: str | None, description: str | None = None) -> None:    
    """Interface to query a task to create into a database for user to approve before storing in Google Tasks"""
    # some db logic here

    # Looks like a mess
    # we want to create a task wwith the title, due date, and description that Gemini suggested,
    # and store that in a job 
    logging.debug(f"Staging new task for approval: '{title}' due on {due_date}. Waiting for user approval...")

    try:

        with Session(engine) as session:
            staged_task = Task(title=title, due_date=due_date, description=description)
            session.add(staged_task)
            session.flush()
            if staged_task.id is None:
                raise ValueError("Failed to create staged task in the database.")
            new_batch = Batch(tasks=[Job(task_id=staged_task.id, action="create")])
            
            session.add(new_batch)
            session.commit()
            session.refresh(new_batch)  # Ensures the ID is populated
            batch_id = new_batch.id
            if batch_id is None:
                logging.error("Failed to create task batch in the database.")
            else:
                # send a desktop notification to the user to approve the task creation, with a callback that
                logging.debug(f"New task batch created with ID {batch_id} for task '{title}' due on {due_date}. Waiting for user approval...")
                notif.send_choice_notif(title="Creating Task...", message=f"Gemini is creating task '{title}' due on {due_date}.", choices=[("Approve", lambda: approve_task(batch_id=batch_id)), ("Reject", lambda: reject_task(batch_id=batch_id))])
    except Exception as e:
        logging.error(f"Error creating task batch in the database: {e}")

def approve_task(batch_id: int) -> dict:
    """Once the user approves a staged task, this function is called to actually create the task in Google Tasks"""
    try:
        with Session(engine) as session:
            batch = session.exec(select(Batch).where(Batch.id == batch_id)).first()
            if not batch:
                logging.error(f"Batch with ID {batch_id} not found.")
                return {"status": "error", "error": f"Batch with ID {batch_id} not found."}
            
            # pass batch.tasks to a function that will loop through them and create/modify/delete tasks in Google Tasks based on the action specified in each job
            # Make a copy of task IDs and actions before session closes to avoid detached instance errors
            jobs_data = [(job.id, job.task_id, job.action) for job in batch.tasks]
            resp = google_tasks_handler(batch_id, jobs_data)
            # print(resp)
            if(resp.get("status") == "success"):
                # remove the batch from the database after approval
                for job in batch.tasks:
                    task = session.exec(select(Task).where(Task.id == job.task_id)).first()
                    if task:
                        session.delete(task)
                    session.delete(job)
                session.delete(batch)
                session.commit()
                logging.debug(f"Task batch with ID {batch_id} has been approved and processed successfully.")
                return {"status": "approved"}
            else:
                logging.error(f"Error processing task batch: {resp.get('error', 'Unknown error')}")
                return {"status": "error", "error": f"Error processing task batch: {resp.get('error', 'Unknown error')}"}
    except Exception as e:
        logging.error(f"Error approving task batch: {e}")
        return {"status": "error", "error": f"Error approving task batch: {e}"}
    
def reject_task(batch_id: int) -> dict:
    """If the user rejects a staged task, this function is called to remove the staged task from the database"""
    try:
        with Session(engine) as session:
            batch = session.exec(select(Batch).where(Batch.id == batch_id)).first()
            if not batch:
                logging.error(f"Batch with ID {batch_id} not found.")
                return {"status": "error", "error": f"Batch with ID {batch_id} not found."}
            
            # delete the batch and its associated jobs and tasks from the database
            for job in batch.tasks:
                task = session.exec(select(Task).where(Task.id == job.task_id)).first()
                if task:
                    session.delete(task)
                session.delete(job)
            session.delete(batch)
            session.commit()
            logging.debug(f"Task batch with ID {batch_id} has been rejected and removed from the database.")
            return {"status": "rejected"}
    except Exception as e:
        logging.error(f"Error rejecting task batch: {e}")
        return {"status": "error", "error": f"Error rejecting task batch: {e}"}

def google_tasks_handler(batch_id: int, jobs_data: list[tuple]) -> dict:    
    """Creates multiple Google Tasks using the API with the given title, due date, and description"""
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

        # we want to execute once all the tasks in the batch have been processed, so we can minimize the number of API calls!
        tasks = service.tasks()

        batch = service.new_batch_http_request()

        # Fetch fresh task data within this function's session
        with Session(engine) as session:
            for job_id, task_id, action in jobs_data:
                task = session.exec(select(Task).where(Task.id == task_id)).first()
                if not task:
                    logging.error(f"Task with ID {task_id} not found.")
                    continue
                
                match action:
                    case "create":
                        batch.add(
                            tasks.insert(
                                tasklist=TASKLIST_ID,
                                body={
                                    "title": task.title,
                                "notes": task.description if task.description else "", # Add description as notes if provided
                                "due": task.due_date # need to transform the due date into RFC3339 format if provided, e.g. "2024-12-31T23:59:00.000Z"
                                }
                            )
                        )
                        logging.debug(f"Task '{task.title}' created successfully in Google Tasks with due date {task.due_date}")
                    case _:
                        logging.error(f"Unsupported job action: {action}")
        
        batch.execute()
        return {"status": "success"}
    except HttpError as err:
        logging.error(f"Error authenticating with Google API: {err}")
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
        logging.debug("Google API credentials are valid. Starting server...")
    except HttpError as err:
        logging.error(f"Error authenticating with Google API: {err}")
        raise err

def get_credentials() -> Credentials | None:
    """Check if valid Google API credentials are available"""
    if os.path.exists("token.json.env"):
        creds = Credentials.from_authorized_user_file("token.json.env", SCOPES)
        return creds
    return None
