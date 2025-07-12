# Task Manager for MQ

This project is a Python-based task management service designed to supplement and manage tasks for a Message Queue (MQ) system. It uses Feishu (Lark) Bitable as its database and provides a set of APIs to control task ingestion, prioritization, and status updates.

## Features

- **Visual Monitoring Dashboard**: A simple, auto-refreshing web page to monitor the number of pending tasks in the queue.
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
- A Supabase account (free tier is sufficient to start).

### 2. Installation

Clone the repository and install the required Python packages:

```bash
git clone <your-repo-url>
cd task-manager
pip install -r requirements.txt
```

### 3. Configure Supabase

1.  **Create a Supabase Project**: Go to [Supabase](https://supabase.com/) and create a new project.
2.  **Create the `tasks` Table**: In your Supabase project, go to the **SQL Editor** and run the following script to create the `tasks` table with the correct columns and policies.

    ```sql
    CREATE TABLE public.tasks (
      id TEXT PRIMARY KEY,
      status TEXT NOT NULL DEFAULT 'PENDING',
      payload JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    ```

3.  **Get API Credentials**: In your Supabase project, go to **Project Settings > API**. You will find your **Project URL** and your **`service_role` key**. You will need these for the next step.

### 4. Configure Environment Variables

Create a `.env` file in the root directory of the project by copying the example file:

```bash
cp .env.example .env
```

Now, edit the `.env` file and fill in the following values:

- `SUPABASE_URL`: Your Supabase project URL.
- `SUPABASE_KEY`: Your Supabase `service_role` key.
- `API_KEY_HASH`: The SHA-256 hash of your secret API key for client authentication.
- `CELERY_BROKER_URL`: The URL for your Celery message broker.
- ... (and other Celery/Scheduler settings)


## How to Run

### Local Development

To run the application locally, use `uvicorn`:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

**Monitoring Dashboard**

The visual dashboard is available at `http://127.0.0.1:8000/status`. Note that this page does not require an API key.

### Docker Deployment (Step-by-Step)

Deploying the application with Docker provides a consistent and isolated environment. Here’s how to do it:

**Step 1: Prepare Your Environment**

Make sure you have Docker installed and running on your system.

**Step 2: Configure Environment Variables**

The Docker container needs access to all the necessary environment variables to run correctly. The most secure way to provide them is through an environment file.

- Ensure you have a `.env` file in the root of the project, as described in the "Configure Environment Variables" section.
- **Crucially**, make sure this file is complete and all values are correctly set for your production environment.

**Step 3: Build the Docker Image**

Navigate to the root directory of the project in your terminal and run the `docker build` command. This command reads the `Dockerfile`, installs all dependencies, and packages the application into a reusable image.

```bash
# The -t flag tags the image with a name (e.g., task-manager-app)
docker build -t task-manager-app .
```

**Step 4: Run the Docker Container**

Once the image is built, you can create and run a container from it. 

```bash
docker run \
  -d \
  -p 8080:80 \
  --env-file ./.env \
  --name my-task-manager \
  --restart unless-stopped \
  task-manager-app
```

Let's break down this command:
- `-d`: Runs the container in detached mode (in the background).
- `-p 8080:80`: Maps port 8080 on your host machine to port 80 inside the container. You will access the API via `http://localhost:8080`.
- `--env-file ./.env`: This is the most important part. It securely passes all the variables from your `.env` file into the container.
- `--name my-task-manager`: Assigns a memorable name to your container for easier management.
- `--restart unless-stopped`: A crucial policy for production. It ensures the container automatically restarts if it crashes, unless you manually stop it.
- `task-manager-app`: The name of the image you want to run.

**Step 5: Verify the Deployment**

Check if the container is running and view its logs to ensure there were no startup errors.

```bash
# List running containers
docker ps

# View the container's logs
docker logs my-task-manager
```

You should see the log output from `loguru`, indicating that the application and the scheduler have started successfully.

**Step 6: Test the API**

Finally, use `curl` or your preferred API client to send a test request to the containerized application. Remember to use the correct port (8080 in this example) and include your API key.

```bash
curl http://127.0.0.1:8080/notifications/status -H "X-API-Key: your_secret_api_key"
```

If you get a successful response, your deployment is complete!

**Managing the Container**

- **To stop the container:** `docker stop my-task-manager`
- **To start it again:** `docker start my-task-manager`
- **To remove the container:** `docker rm my-task-manager` (must be stopped first)


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

## Continuous Deployment (CI/CD)

This project includes a GitHub Actions workflow to automatically build and publish the Docker image to Docker Hub.

### How It Works

The workflow is defined in `.github/workflows/docker-publish.yml` and is triggered by two events:

1.  **Push to `main` branch**: When code is pushed or merged to the `main` branch, a new Docker image is built and pushed with the `latest` tag.
2.  **New Release**: When you create a new release on GitHub (e.g., `v1.2.0`), a new Docker image is built and pushed with a tag matching the release version.

### Setup

To enable this workflow, you need to configure secrets in your GitHub repository:

1.  **Create a Docker Hub Access Token**: Go to your Docker Hub account settings, navigate to **Security**, and create a new access token with **Read & Write** permissions.
2.  **Add Secrets to GitHub**: In your GitHub repository, go to **Settings > Secrets and variables > Actions** and add the following two repository secrets:
    - `DOCKER_USERNAME`: Your Docker Hub username.
    - `DOCKER_PASSWORD`: The access token you just generated.

Once these secrets are in place, the workflow will run automatically on the next push to `main` or the next release publication.


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
