"""
Handles interactions with Google Tasks API, including authentication and task creation/modification.

Because we want the user to approve suggested tasks from Gemini, we'll have to store them as a "Job"
where each job is a suggested task creation/modification that the user can approve or reject. Once 
the user approves a job, we can then call the add_task function to create/modify the task in Google Tasks.
"""
import datetime
import os
import logging

from pydantic import BaseModel

import notif
import config

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# Google Tasks API client setup
SCOPES = ["https://www.googleapis.com/auth/tasks"] # Scope for write access to Google Tasks
TASKLIST_ID = os.getenv("TASKLIST_ID", "@default") # Use the default task list if not specified

# Pydantic version of our tasks for agent tool schema
class TaskItem(BaseModel):
    title: str | None # We'll have to make the title optional for the modify action, since Gemini might only suggest a modification to the due date or description without changing the title, and we don't want the agent to be forced to provide a title in that case
    due_date: str | None
    description: str | None
    google_task_id: str | None = None # This will store the ID of the task in Google Tasks once it's created, which can be useful for modifying existing tasks

from typing import Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select, Relationship, delete

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str | None
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

class CachedGoogleTask(SQLModel, table=True):
    """Utility table for storing the current list of tasks from Google Tasks for quick retrieval without needing to query the Google API every time"""
    google_id: str = Field(primary_key=True) # Use Google's actual task ID
    title: str
    due_date: Optional[str] = None
    notes: Optional[str] = None
    
SQLITE_URL = "sqlite:///tasks.db"
engine = create_engine(SQLITE_URL)

def init_db():
    # This automatically generates the tables based on your classes above
    SQLModel.metadata.create_all(engine)

    # and then try updating the cache with the most recent tasks from Google Tasks
    # cache_google_tasks(get_tasks())

def check_db():
    """Check if the database is set up correctly by trying to query the Task table."""
    try:
        with Session(engine) as session:
            session.exec(select(Task)).first()
        logging.debug("Database connection successful and Task table is accessible.")
    except Exception as e:
        logging.error(f"Database connection failed or Task table is not accessible: {e}")

def cache_google_tasks(force : bool = False) -> None:
    """
    Utility function to cache the most recent list of tasks from Google Tasks in our database for quick retrieval
    
    TODO:
        - account for pagination if there are more than 100 tasks in the task list, since the Google Tasks API returns a maximum of 100 tasks per request. We can use the "nextPageToken" in the API response to retrieve additional pages of tasks until we've cached all tasks.

    """
    # we'll get the date of the most recent update stored from our config file,
    # and retrieve tasks from Google Tasks from that date onward.
    most_recent_check = config.get("most_recent_check", None)
    
    if not most_recent_check or force:
        logging.info("Caching all tasks from Google Tasks to DB...")
    else:
        logging.info(f"Caching tasks from Google Tasks updated since {most_recent_check} to DB...")
    creds = get_credentials()
    if not creds:
        logging.error("Google API credentials not found. Please authenticate with the Google API before using this tool.")
        return
    try:
        service = build("tasks", "v1", credentials=creds)
        
        if most_recent_check and not force:
            results = service.tasks().list(tasklist=TASKLIST_ID, updatedMin=most_recent_check).execute()
        else:
            results = service.tasks().list(tasklist=TASKLIST_ID).execute()
        items = results.get("items", [])
        if not items:
            logging.info("No tasks found in Google Tasks to cache.")
            return
        
        if force:
            # deletes all cached tasks before re-caching to ensure that our cache is an exact mirror of the current state of Google Tasks
            logging.warning("Force caching enabled. All existing cached tasks will be deleted and replaced with the current tasks from Google Tasks.")
            with Session(engine) as session:
                session.exec(delete(CachedGoogleTask))
                session.commit()

        with Session(engine) as session:
            # from here, there are two scenarios, if not force (otherwise do #1):
            # 1) we are updating (google_task_id is found in our cache)
            # 2) we are creating (google_task_id not found in our cache) and need to add new tasks to our cache.
            for item in items:
                if(not force):
                    cached_task = session.exec(select(CachedGoogleTask).where(CachedGoogleTask.google_id == item["id"])).first()
                    if cached_task:
                        # update the existing cached task with the new info from Google Tasks
                        cached_task.title = item["title"]
                        cached_task.due_date = item.get("due")
                        cached_task.notes = item.get("notes")
                        session.add(cached_task)
                        continue
                cached_task = CachedGoogleTask(
                    google_id=item["id"],
                    title=item["title"],
                    due_date=item.get("due"),
                    notes=item.get("notes")
                )
                session.add(cached_task)
            session.commit()
            logging.debug("Google Tasks have been cached successfully.")
    except HttpError as err:
        logging.error(f"Error authenticating with Google API: {err}")
    except Exception as e:
        logging.error(f"Error caching tasks from Google Tasks: {e}")
    # and then update the most recent check date in our config file
    # as RFC 3339 format, e.g. "2024-12-31T23:59:00.000Z"
    most_recent_check = datetime.datetime.now(datetime.timezone.utc).isoformat()
    config.set("most_recent_check", most_recent_check)
    logging.info(f"Google Tasks caching complete. Most recent check date updated to {most_recent_check}!")


def get_tasks() -> dict:
    """
        Utility function to get all tasks from Google Tasks

        Ideally, we should be caching the most recent list of tasks from Google Tasks in our database, 
        and only query Google Tasks for updates when necessary (e.g. when the user explicitly asks to 
        list their tasks, or after we create/modify a task to refresh the cache). This way, we can 
        minimize the number of API calls to Google Tasks and improve performance.

        We'll be converting the cached tasks in our database into TaskItem objects to return to the 
        agent when it calls the list_google_tasks tool, so it's important that the CachedGoogleTask 
        table has the same structure as the TaskItem class for easy conversion.
    """
    try:
        with Session(engine) as session:
            cached_tasks = session.exec(select(CachedGoogleTask)).all()
            return {"status": "success", "cached": [{"task_id": task.google_id, "title": task.title, "due_date": task.due_date, "description": task.notes} for task in cached_tasks]}
    except Exception as e:
        logging.error(f"Error retrieving cached tasks from database: {e}")
        return {"status": "error", "cached": []}

async def create_batch(task_items: list[TaskItem], action: str) -> None:    
    """Interface to query a task to create into a database for user to approve before storing in Google Tasks"""

    # Looks like a mess
    # we want to create a task wwith the title, due date, and description that Gemini suggested,
    # and store that in a job 
    try:
        with Session(engine) as session:
            # create a new batch for this set of tasks
            batch = Batch()
            session.add(batch)
            session.flush() # flush to get the batch ID for the job relationship

            for item in task_items:
                logging.debug(f"Staging new task for approval: '{item.title}' due on {item.due_date}. Waiting for user approval...")

                # create the tasks in the DB
                match action:
                    case "create":
                        task = Task(
                            title=item.title,
                            due_date=item.due_date,
                            description=item.description
                        )
                    case "update":
                        # for modify actions, we need the Google Task ID to know which task to modify,
                        # we need to get the info that is missing from our taskitem from our cache

                        cached_task = session.exec(select(CachedGoogleTask).where(CachedGoogleTask.google_id == item.google_task_id)).first()
                        if not cached_task:
                            logging.error(f"Cached task with Google ID {item.google_task_id} not found for modification. Skipping this task.")
                            continue

                        task = Task(
                            title=(item.title if item.title is not None else cached_task.title),
                            due_date=(item.due_date if item.due_date is not None else cached_task.due_date),
                            description=(item.description if item.description is not None else cached_task.notes),
                            google_task_id=item.google_task_id
                        )
                    case _:
                        logging.error(f"Unsupported job action: {action}. Skipping this task.")
                        continue
                logging.info(task)
                session.add(task)
                session.flush() # flush to get the task ID for the job relationship
                # create a job for this task with action "create"
                if not task.id:
                    logging.error("Failed to create task in database, task ID not generated.")
                    continue
                job = Job(
                    task_id=task.id,
                    action=action,
                    batch_id=batch.id
                )
                session.add(job)

            session.commit()
            logging.info(f"Task batch with ID {batch.id} has been staged for approval successfully.")

            # get the batch id....
            # necessary to define as this way for Pylancer type errors
            id = batch.id
            if id is None:
                logging.error("Batch ID is None after commit, cannot send notification for approval.")
                return
            
            notif.send_choice_notif(
                title="New Tasks Suggested",
                message=f"{len(task_items)} new tasks have been suggested based on your recent file changes. Do you want to add them to Google Tasks?",
                choices=[
                    ("Approve", lambda: approve_batch(id)),
                    ("Deny", lambda: reject_batch(id))
                ]
            )
    except Exception as e:
        logging.error(f"Error staging task for approval: {e}")

def approve_batch(batch_id: int) -> dict:
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
            resp = google_tasks_handler(jobs_data)
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

                # we must also update our own cache of tasks from Google Tasks after creating/modifying/deleting tasks, 
                # to ensure that the agent has the most up-to-date information when it queries the list of tasks
                cache_google_tasks()

                logging.info(f"Task batch with ID {batch_id} has been approved and processed successfully.")
                return {"status": "approved"}
            else:
                logging.error(f"Error processing task batch: {resp.get('error', 'Unknown error')}")
                return {"status": "error", "error": f"Error processing task batch: {resp.get('error', 'Unknown error')}"}
    except Exception as e:
        logging.error(f"Error approving task batch: {e}")
        return {"status": "error", "error": f"Error approving task batch: {e}"}
    
def reject_batch(batch_id: int) -> dict:
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
    
def get_pending_batches() -> list[dict]:
    """
    Returns a list of pending batches that require user approval
    
    {
    "pending_batches": [
        {
            "batch_id": 1,
            "tasks": [
                {
                    "task_id": 1,
                    "title": "Task 1",
                    "due_date": "2024-12-31T23:59:00.000Z",
                    "description": "This is a test task.",
                    "action": "create"
                },
                {
                    "task_id": 2,
                    "title": "Task 2",
                    "due_date": null,
                    "description": null,
                    "action": "modify"
                }
            ]
        },
        ...
    }
    """
    try:
        with Session(engine) as session:
            pending_batches = session.exec(select(Batch).where(Batch.status == "pending")).all()
            pending_jobs = []
            for batch in pending_batches:
                to_append = []
                for job in batch.tasks:
                    task = session.exec(select(Task).where(Task.id == job.task_id)).first()
                    if task:
                        to_append.append({
                            "task_id": task.id,
                            "title": task.title,
                            "due_date": task.due_date,
                            "description": task.description,
                            "action": job.action
                        })
                pending_jobs.append({
                    "batch_id": batch.id,
                    "tasks": to_append
                })
            return pending_jobs
    except Exception as e:
        logging.error(f"Error retrieving pending batches: {e}")
        return []               

def clear_pending_batches() -> dict:
    """Utility function to clear all pending batches from the database. This can be used for testing purposes."""
    try:
        with Session(engine) as session:
            pending_batches = session.exec(select(Batch).where(Batch.status == "pending")).all()
            for batch in pending_batches:
                for job in batch.tasks:
                    task = session.exec(select(Task).where(Task.id == job.task_id)).first()
                    if task:
                        session.delete(task)
                    session.delete(job)
                session.delete(batch)
            session.commit()
            logging.debug("All pending batches have been cleared from the database.")
            return {"status": "success", "message": "All pending batches have been cleared from the database."}
    except Exception as e:
        logging.error(f"Error clearing pending batches: {e}")
        return {"status": "error", "error": f"Error clearing pending batches: {e}"}

def google_tasks_handler(jobs_data: list[tuple]) -> dict:    
    """Handles multiple Google Tasks edit jobs using the API with the given task info and actions (create/modify)"""
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

        batch_req = service.new_batch_http_request()

        # Fetch fresh task data within this function's session
        with Session(engine) as session:
            print(jobs_data)
            for _, task_id, action in jobs_data:
                task = session.exec(select(Task).where(Task.id == task_id)).first()
                if not task:
                    logging.error(f"Task with ID {task_id} not found.")
                    continue
                
                match action:
                    case "create":
                        batch_req.add(
                            tasks.insert(
                                tasklist=TASKLIST_ID,
                                body={
                                    "title": task.title if task.title else "", # Google Tasks API requires a title, so we'll use "' if the title is None
                                "notes": task.description if task.description else "", # Add description as notes if provided
                                "due": task.due_date # need to transform the due date into RFC3339 format if provided, e.g. "2024-12-31T23:59:00.000Z"
                                }
                            )
                        )
                        logging.info(f"Task '{task.title}' created successfully in Google Tasks with due date {task.due_date}")
                    case "update":
                        logging.info(f"Modifying task with Google Task ID {task.google_task_id}, task: {task}...")
                        batch_req.add(
                            tasks.update(
                                tasklist=TASKLIST_ID,
                                task=task.google_task_id,
                                body={
                                    "title": task.title,
                                    "notes": task.description if task.description else "",
                                    "due": task.due_date,
                                    "id": task.google_task_id
                                }
                            )
                        )
                        logging.info(f"Task '{task.title}' updated successfully in Google Tasks with due date {task.due_date}")
                    # for now, we do not want to delete
                    case _:
                        logging.error(f"Unsupported job action: {action}")
        
        batch_req.execute()
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
