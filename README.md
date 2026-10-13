# Spencer AI (v2.0) — Local Ollama & PostgreSQL Upgrade

**Advanced Voice Assistant & Intelligent Problem Solver**

Spencer is an advanced AI assistant built with FastAPI, LangChain, locally hosted **Ollama (`llama3.1`)**, and **PostgreSQL** for persistent conversation history. It provides streaming responses via Server-Sent Events (SSE), dynamic cognitive mode detection (Debugging, Optimization, Learning), resilient memory management, and optional Whisper-based voice transcription.

---

## 1. Architecture Overview

```mermaid
flowchart TD
    subgraph Client ["Frontend (HTML5 / Vanilla JS / CSS3)"]
        UI["Web Interface (localhost:8000)"]
        SSE_Recv["SSE Stream Consumer / Audio Recorder"]
    end

    subgraph Backend ["FastAPI Application (Port 8000)"]
        Router["FastAPI Routers (/health, /chat/stream, /conversations, /sessions)"]
        Lifespan["Async Lifespan & Diagnostics"]
        Repo["ConversationRepository (SQLAlchemy 2.0 Async)"]
        Memory["MemoryManager (PostgreSQL-backed Session Memory)"]
        Agent["SpencerAgent (Cognitive Mode Detector)"]
        Voice["VoiceTranscriber (Optional Whisper)"]
    end

    subgraph AI_Services ["AI Inference"]
        Ollama["Local Ollama Daemon (localhost:11434)"]
        Model["Llama 3.1 LLM"]
        Whisper["OpenAI Whisper API (Optional Voice Only)"]
    end

    subgraph Storage ["Persistent Storage"]
        PG[(PostgreSQL Database: spencer_db)]
        Alembic["Alembic Migrations"]
    end

    UI -->|HTTP / SSE| Router
    Router --> Agent
    Router --> Repo
    Agent --> Memory
    Memory --> Repo
    Repo --> PG
    Alembic -->|Schema Migrations| PG
    Agent -->|ChatOllama / Stream| Ollama
    Ollama --> Model
    Router --> Voice
    Voice -.->|Requires API Key| Whisper
```

---

## 2. Key Enhancements in Version 2.0

- **Local AI Inference**: Switched from cloud OpenAI GPT models to locally hosted **Ollama (`llama3.1`)**. Ordinary text conversations require **no OpenAI API key**.
- **PostgreSQL Persistence**: Replaced MongoDB with **PostgreSQL** using SQLAlchemy 2.x async engine (`asyncpg`) and **Alembic** schema migrations.
- **Relational Conversation Schema**: Bounded context management, UUID primary keys, cascade deletion, UTC timestamps, and JSONB metadata support.
- **Backward-Compatible API**: Full compatibility with the existing frontend UI (`/sessions`, `/sessions/{id}/history`, `/chat/stream`) alongside new RESTful conversation routes (`/conversations`).
- **Comprehensive Diagnostics**: `/health` endpoint distinguishes FastAPI application status, PostgreSQL connection health, Ollama service availability, and `llama3.1` model installation.
- **Data Migration Tool**: Included `scripts/migrate_mongo_to_postgres.py` to preserve existing conversation history from MongoDB.

---

## 3. Prerequisites

- **Windows 10 / 11**
- **PowerShell 5.1+** or **PowerShell 7+**
- **Python 3.10+** (Python 3.13 supported)
- **Ollama for Windows** ([Download Ollama](https://ollama.com/download/windows))
- **PostgreSQL 15+** ([Download PostgreSQL](https://www.postgresql.org/download/windows/))

---

## 4. PostgreSQL Installation & Configuration on Windows

If PostgreSQL is not yet installed on your Windows system, follow these steps:

### Step 4.1: Download and Install PostgreSQL
1. Download the official PostgreSQL Windows installer from [EnterpriseDB](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads).
2. Run the installer (`postgresql-xx.x-x-windows-x64.exe`).
3. Select installation components: **PostgreSQL Server**, **pgAdmin 4**, and **Command Line Tools**.
4. Set a master password for the default `postgres` superuser (e.g. `postgres` or `admin123`). Keep note of this password.
5. Keep the default port `5432` and locale. Complete the installation.

### Step 4.2: Verify PostgreSQL Windows Service
Open PowerShell and check that the PostgreSQL service is active:
```powershell
Get-Service *postgres*
```
If not running, start it:
```powershell
Start-Service postgresql*
```

### Step 4.3: Create Database Role and Database
Open PowerShell and navigate to the PostgreSQL `bin` directory (or ensure it is added to your PATH, typically `C:\Program Files\PostgreSQL\<version>\bin`):

```powershell
# Open SQL Shell (psql) as superuser
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres
```

Inside the `psql` prompt, run the following SQL commands:
```sql
-- Create user role for Spencer
CREATE USER spencer_user WITH PASSWORD 'spencer_password';

-- Create dedicated database
CREATE DATABASE spencer_db OWNER spencer_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE spencer_db TO spencer_user;

-- Exit psql
\q
```

---

## 5. Ollama Setup (Llama 3.1)

1. Install Ollama for Windows from [ollama.com](https://ollama.com).
2. Ensure the Ollama daemon is running in the background (or launch `ollama serve` from a PowerShell window).
3. Download the `llama3.1` model:
   ```powershell
   ollama pull llama3.1
   ```
4. Verify the model is downloaded:
   ```powershell
   ollama list
   ```
   You should see `llama3.1:latest` listed.

---

## 6. Project Setup & Environment Configuration

### Step 6.1: Navigate to Workspace
```powershell
cd "c:\spencer bot"
```

### Step 6.2: Virtual Environment & Dependencies
```powershell
# If activating existing virtual environment:
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### Step 6.3: Environment Variables (`.env`)
Copy `.env.example` to `.env` and set your database credentials:
```powershell
Copy-Item .env.example .env
```
Edit `.env` to configure your settings:
```env
APP_ENV=development
HOST=127.0.0.1
PORT=8000

# Ollama Settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# PostgreSQL Connection String
DATABASE_URL=postgresql+asyncpg://spencer_user:spencer_password@localhost:5432/spencer_db

# Connection Pool Settings
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Conversation Context Limit
CHAT_CONTEXT_LIMIT=20

# Optional: Voice Transcription only (Whisper API)
# Leave blank if not using microphone audio input
OPENAI_API_KEY=
```

---

## 7. Database Migrations (Alembic)

Initialize and apply the database schema using Alembic:

```powershell
# Run from project root ("c:\spencer bot")
.\venv\Scripts\alembic upgrade head
```

To rollback a migration:
```powershell
.\venv\Scripts\alembic downgrade -1
```

### (Optional) Migrate Data from Existing MongoDB
If you have previous conversation history stored in MongoDB (`mongodb://localhost:27017`), run the migration script:

```powershell
# Perform a dry-run check first:
.\venv\Scripts\python scripts/migrate_mongo_to_postgres.py --dry-run

# Execute data transfer to PostgreSQL:
.\venv\Scripts\python scripts/migrate_mongo_to_postgres.py
```

---

## 8. Running the Application

Start the backend server with hot reloading enabled:
```powershell
# Run from project root ("c:\spencer bot")
.\venv\Scripts\python backend/main.py
```

The server will initialize and bind to `http://127.0.0.1:8000`.

### Open the Frontend Interface
Open your web browser and navigate to:
```
http://127.0.0.1:8000/
```
The static frontend is served directly by FastAPI and will connect to the backend automatically.

---

## 9. Running Automated Tests

Run the complete test suite:
```powershell
# Run from project root ("c:\spencer bot")
.\venv\Scripts\pytest -v
```

The test suite covers:
- **Configuration loading & validation**: Defaults, custom environment variables, sync URL derivation.
- **Database repository & models**: UUID handling, message ordering, UTC timestamps, cascading deletes, conversation isolation.
- **Ollama AI Agent**: Dynamic mode detection, bounded history limits, mocked inference & streaming, Ollama offline / missing model error reporting.
- **FastAPI Routes**: `/health` diagnostic breakdown, `/chat` non-streaming, `/chat/stream` SSE stream parsing, `/sessions` and `/conversations` CRUD.
- **Migrations**: Alembic configuration loading and migration file integrity.

---

## 10. API Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Diagnostics for App, PostgreSQL, and Ollama status & model availability |
| `POST` | `/chat` | Non-streaming text chat endpoint (`{"session_id": "...", "message": "..."}`) |
| `POST` | `/chat/stream` | Server-Sent Events (SSE) streaming chat endpoint |
| `POST` | `/chat/audio` | Voice audio input transcribed via optional Whisper and processed by Ollama |
| `GET` | `/sessions` | List sessions formatted for frontend sidebar (`?limit=50&offset=0`) |
| `GET` | `/sessions/{id}/history` | Retrieve full message history for a specific session |
| `DELETE` | `/sessions/{id}` | Delete a session and its associated messages |
| `POST` | `/conversations` | RESTful endpoint to create a new conversation |
| `GET` | `/conversations` | RESTful endpoint to list conversations with pagination |
| `GET` | `/conversations/{id}` | Retrieve conversation with messages by UUID |
| `DELETE` | `/conversations/{id}` | Delete conversation by UUID with cascade delete |

Interactive Swagger documentation is available at:
`http://127.0.0.1:8000/docs`

---

## 11. Troubleshooting Guide

### 1. `Cannot connect to Ollama at http://localhost:11434`
- Make sure Ollama is running. In PowerShell, execute:
  ```powershell
  ollama serve
  ```
- Check that `http://localhost:11434/api/tags` returns HTTP 200 in your browser or with `curl`.

### 2. `Model 'llama3.1' not downloaded`
- Spencer detected that Ollama is running, but the specified model has not been downloaded yet. Run:
  ```powershell
  ollama pull llama3.1
  ```

### 3. `PostgreSQL connection refused (password authentication failed)`
- Verify that the username and password in `DATABASE_URL` match what was created in PostgreSQL:
  ```powershell
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U spencer_user -d spencer_db
  ```
- Check that the PostgreSQL service is active with `Get-Service *postgres*`.

### 4. PowerShell `Activate.ps1 cannot be loaded because running scripts is disabled`
- In PowerShell running as Administrator (or CurrentUser), run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- Then retry: `.\venv\Scripts\Activate.ps1`.
