# Write-To-Tasks
A Python application that integrates Google Gemini with the Google Tasks API to create tasks based on user input. The aim of this project is to allow users to easily convert their thoughts, ideas, or reminders into actionable tasks in their Google Tasks using natural language processing with Google Gemini as a parser.

---

## 🛠️ Setup guide
1. Clone the repository:
   ```bash
   git clone https://github.com/googleapis/google-tasks-api.git
    cd google-tasks-api
    ```
2. Get the necessary credentials for Google Tasks API and Google Gemini set up your environment, found in these quickstart guides. Store the credentials in a `.env` file in the root directory of the project.
   - [Google Tasks API Quickstart](https://developers.google.com/tasks/quickstart/python)
   - [Google Gemini API Quickstart](https://ai.google.dev/gemini-api/docs/quickstart)

   Note: Be sure to enables yourself as a tester in the Google Cloud Console for the Gemini API!

3. Install the required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
    python src/agent.py
    ```
5. Continue into your browser to allow the application to access your Google Tasks account when prompted. This will enable the application to create tasks on your behalf.

6. Send a `POST` request to `http://localhost:8000/create_task` with a JSON body containing a prompt field to create a new task in your Google Tasks account. For example:
   ```json
   {
      "prompt": "Buy groceries: Milk, Bread, Eggs by Friday 5/20/2023 at 5 PM"
   }
   ```