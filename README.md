# Task Manager for MQ

This project is a Python-based task management service designed to supplement and manage tasks for a Message Queue (MQ) system. It uses Feishu (Lark) Bitable as its database and provides a set of APIs to control task ingestion, prioritization, and status updates.

## Features

- **Automatic Task Replenishment**: A scheduled job runs every 4 hours to check the task pool and automatically adds new tasks if the count falls below a specified threshold.
- **Data Ingestion API**: An endpoint to submit new tasks. It includes a mechanism to prevent duplicate entries.
- **Priority Queue API**: An endpoint to inject high-priority tasks directly into the processing queue.
- **Status Update API**: An endpoint to bulk-update the status of tasks (e.g., to `SUCCESS`, `FAILED`, or `PENDING`).
- **Feishu Integration**: Uses Feishu Bitable as a database and sends notifications via Feishu bots.
- **Docker Support**: Comes with a `Dockerfile` for easy containerization and deployment.

## How It Works

1.  **Task Ingestion**: New tasks are submitted via the `/api/tasks/ingest` endpoint. They are stored in a Feishu Bitable with a `PENDING` status.
2.  **Scheduled Replenishment**: Every 4 hours, the system checks for tasks. If the number of `PENDING` tasks is below 3,000, it fetches up to 500 tasks from the Bitable, publishes them to the MQ (via a configurable API call), and updates their status to `PROCESSING`.
3.  **Priority Tasks**: Tasks submitted to `/api/tasks/priority-queue` are immediately published to the MQ and saved in the Bitable with a `PROCESSING` status.
4.  **Status Updates**: External systems can call `/api/tasks/update-status` to change the status of tasks in the Bitable once they are completed or have failed.

## Setup and Configuration

### 1. Prerequisites

- Python 3.8+
- Docker (optional, for containerized deployment)
- A Feishu account with permissions to create Apps and Bitables.

### 2. Installation

Clone the repository and install the required Python packages:

```bash
git clone <your-repo-url>
cd task-manager
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory of the project by copying the example file:

```bash
cp .env.example .env
```

Now, edit the `.env` file and fill in the following values:

- `API_KEY_HASH`: **(Required for security)** The SHA-256 hash of your secret API key. The server stores only this hash.
- `FEISHU_APP_ID`: Your Feishu App ID.
- `FEISHU_APP_SECRET`: Your Feishu App Secret.
- `FEISHU_BITABLE_APP_TOKEN`: The App Token for your Bitable.
- `FEISHU_BITABLE_TABLE_ID`: The Table ID for your Bitable table.
- `FEISHU_ROBOT_WEBHOOK_URL`: The webhook URL for your Feishu bot.
- `CELERY_APP_NAME`: The name of your Celery application (e.g., `wqb`).
- `CELERY_BROKER_URL`: The URL for your Celery message broker (e.g., `pyamqp://guest:guest@localhost:5672//`).
- `CELERY_TASK_NAME`: The full name of the target task to be executed (e.g., `wqb.tasks.simulate_task`).
- `CELERY_QUEUE`: The target Celery queue.
- `CELERY_DEFAULT_PRIORITY`: The priority for regular, scheduled tasks (e.g., `5`).
- `CELERY_HIGH_PRIORITY`: The priority for urgent, manually queued tasks (e.g., `1`).

### 4. Prepare Your Feishu Bitable

For this application to work correctly, you must set up a Feishu Bitable table with specific columns. The application will read from and write to these columns.

#### Mandatory Columns

These two columns are **required** for the core logic of the task manager.

| Column Name  | Column Type      | Description                                                                                                                              |
| :----------- | :--------------- | :--------------------------------------------------------------------------------------------------------------------------------------- |
| `Identifier` | `Single-line text` | **Crucial for preventing duplicates.** This field stores a unique MD5 hash of the task content. The application manages this automatically. |
| `Status`     | `Single-select`  | **Tracks the task lifecycle.** You **must** create this column with the following four options (case-sensitive): `PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`. |

#### Custom Data Columns

You need to add columns that correspond to the keys in the JSON data you plan to send to the application. The application will automatically map the JSON keys to the column names.

**Example:**

If you plan to send tasks with the following JSON structure:

```json
{
  "url": "https://example.com/data/1",
  "customer_id": "CUST-007",
  "retry_count": 3
}
```

Then, in addition to the mandatory columns, you would need to create the following columns in your Bitable:

| Column Name     | Column Type | Description                               |
| :-------------- | :---------- | :---------------------------------------- |
| `url`           | `URL` or `Text` | To store the URL from the task.           |
| `customer_id`   | `Text`      | To store the customer's unique ID.        |
| `retry_count`   | `Number`    | To store the number of retries.           |

Your final table structure would look something like this:

| Identifier (Text) | Status (Select) | url (URL) | customer_id (Text) | retry_count (Number) |
| :---------------- | :-------------- | :-------- | :----------------- | :------------------- |
| (auto-generated)  | PENDING         | ...       | ...                | ...                  |


## How to Run

### Local Development

To run the application locally, use `uvicorn`:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### Docker Deployment

To build and run the application using Docker:

```bash
# Build the Docker image
docker build -t task-manager .

# Run the container
docker run -d -p 8080:80 --env-file .env --name task-manager-app task-manager
```

The API will be available at `http://localhost:8080`.

## Testing

Once the application is running, you can use `curl` or any API client to test the endpoints. The following examples assume the application is running locally on port 8000 and you have set your `API_KEY` in the `.env` file.

**All requests must include the `X-API-Key` header.**

### 1. Toggle Notifications

By default, notifications are off. You can enable them for testing.

**Enable Notifications:**
```bash
curl -X POST http://127.0.0.1:8000/notifications/toggle -H "Content-Type: application/json" -H "X-API-Key: your_secret_api_key" -d '{"enabled": true}'
```

**Check Status:**
```bash
curl http://127.0.0.1:8000/notifications/status -H "X-API-Key: your_secret_api_key"
```

### 2. Ingest New Tasks

This endpoint adds new tasks to the Bitable with `PENDING` status. It prevents duplicates based on the task content.

```bash
curl -X POST http://127.0.0.1:8000/tasks/ingest -H "Content-Type: application/json" -H "X-API-Key: your_secret_api_key" -d '[
  {"customer_id": "CUST-001", "data": "some_payload_1"},
  {"customer_id": "CUST-002", "data": "some_payload_2"}
]'
```

If you run the same command again, the response will indicate that 0 tasks were added and 2 were duplicates.

### 3. Add High-Priority Tasks

This endpoint sends tasks directly to the message queue and saves them to the Bitable with `PROCESSING` status.

**Default (Medium) Priority:**
```bash
curl -X POST http://127.0.0.1:8000/tasks/priority-queue -H "Content-Type: application/json" -H "X-API-Key: your_secret_api_key" -d '[
  {"customer_id": "CUST-003", "data": "urgent_payload_3"}
]'
```

**Custom (High) Priority:**
```bash
curl -X POST "http://127.0.0.1:8000/tasks/priority-queue?priority=9" -H "Content-Type: application/json" -H "X-API-Key: your_secret_api_key" -d '[
  {"customer_id": "CUST-004", "data": "critical_payload_4"}
]'
```

### 4. Update Task Status

This endpoint updates the status of existing tasks. You need to get the `record_id` from your Feishu Bitable first.

```bash
curl -X POST http://127.0.0.1:8000/tasks/update-status -H "Content-Type: application/json" -H "X-API-Key: your_secret_api_key" -d '[
  {"record_id": "rec_xxxxxxxx", "status": "SUCCESS"},
  {"record_id": "rec_yyyyyyyy", "status": "FAILED"}
]'
```

### Generating a Secure Key and Hash

For production environments, you should use a long, randomly generated secret key. The client will use this key in the `X-API-Key` header. The server, however, only needs to know the SHA-256 hash of this key.

**1. Generate a Secret Key:**

Use this command to generate a cryptographically secure key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Example Output: 1a2b3c4d...
```
Keep this key safe and provide it to your API clients.

**2. Generate the Hash for the Server:**

Take the key you just generated and use this command to create its SHA-256 hash:
```bash
python -c "import hashlib; print(hashlib.sha256('your_secret_key_here'.encode()).hexdigest())"
# Example Output: 8c6976e5...
```

**3. Configure the Server:**

Copy the resulting hash and set it as the value for `API_KEY_HASH` in your `.env` file.

## API Endpoints

All endpoints are prefixed with `/api`.

- **POST /tasks/ingest**
  - Ingests a list of tasks. Checks for duplicates before adding.
  - **Body**: `[{"field1": "value1"}, {"field2": "value2"}]`

- **POST /tasks/priority-queue**
  - Injects high-priority tasks directly into the MQ.
  - **Body**: `[{"field1": "value1"}, {"field2": "value2"}]`

- **POST /tasks/update-status**
  - Updates the status of one or more tasks.
  - **Body**: `{"SUCCESS": ["rec_id1"], "FAILED": ["rec_id2"]}`
