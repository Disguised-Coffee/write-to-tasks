# Write-To-Tasks
An agent that converts natural language todo lists into actionable tasks in Google Tasks using Google Gemini for parsing and the Google Tasks API for task creation to streamline task management and organization.

---
## Overview
Write-To-Tasks is an intelligent agent designed to simplify task management by converting natural language todo lists into actionable tasks in Google Tasks. By leveraging the capabilities of Google Gemini for natural language processing and the Google Tasks API for task creation, Write-To-Tasks allows users to effortlessly create and edit their tasks and stay on top of their responsibilities. 

Once set up, users can simply write their tasks in natural language, and the agent will parse the input and create corresponding tasks in Google Tasks, complete with due dates and other relevant details, and notify the user of the agent's edits for confirmation.

This tool is ideal for anyone looking to streamline their task management process and stay organized without the hassle of manually entering Google Tasks.

## ‼️ Requirements
- Python 3.8 or higher installed on your machine. If you don't have Python installed, you can download it from the [official Python website](https://www.python.org/downloads/).
- `git` installed to clone the repository. If you don't have `git` installed, you can download it from the [official Git website](https://git-scm.com/downloads).
- Access to the Google Gemini API, and have the necessary credentials to authenticate with these services.
- You have a Google account to access the Google Tasks API with, along with a Tasklist created.

## 🛠️ Setup guide

**Note: This guide assumes developer experience**

1. Clone the repository:
   ```bash
   git clone https://github.com/googleapis/google-tasks-api.git
    cd google-tasks-api
    ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
3. Retrieve a Google Gemini API key and put in a `.env` file as `GOOGLE_API_KEY`. 
   - [Google Gemini API Quickstart](https://ai.google.dev/gemini-api/docs/quickstart)

4. Retrieve the necessary credentials for Google Tasks API found in these quickstart guides. Store the credentials in as `credentials.json.env` file in the root directory of the project. ***When the application runs, you will need to authenticate with Google Tasks API and the credentials will be stored in `token.json.env` for future use.***
      
   **(If you are a tester, you will be given this file by the project owner)**
   - [Google Tasks Python API Quickstart Reference](https://developers.google.com/tasks/quickstart/python)

3. Install the required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
    python src/agent.py
    ```
5. Continue into your browser to allow the application to access your Google Tasks account when prompted. This will enable the application to create tasks on your behalf.

6. Configure the Tasklist ID to bind tasks queries and creations to a specific tasklist. You can find your Tasklist ID by running `tests/list_tasklists.py`, which will display all your tasklists along with their IDs. Once you have the Tasklist ID of the list you want to edit, set it as an environment variable named `TASKLIST_ID` in your `.env` file.

6. Trigger task creation by either:
   - sending a `POST` request to the `/generate` endpoint with a natural language prompt describing the task you want to create. You can use tools like `curl`, Postman, or any HTTP client to send the request.

      For example:
      ```json
      {
         "prompt": "Buy groceries: Milk, Bread, Eggs by Friday 5/20/2023 at 5 PM"
      }
      ```
   
   - Or editting and saving `todo.txt` with a natural language prompt describing the task you want to create. The application will monitor the file for changes and automatically process new tasks when they are added.

      For example, add the following line to `todo.txt`:
      ```
      - Buy groceries: Milk, Bread, Eggs by Friday at 5 PM
      ```
   
