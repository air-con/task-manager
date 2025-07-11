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

Your Bitable table should have at least the following columns:

- `Identifier` (Single-line text): Stores a unique hash to prevent duplicates.
- `Status` (Single-select): With options `PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`.
- ... and other columns for your task data (e.g., `Payload`, `CreatedAt`, etc.).

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
