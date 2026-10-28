
# TaskHub API

TaskHub is a RESTful backend API for managing workspaces,
projects, tasks, labels, and comments.

Built with FastAPI, PostgreSQL, SQLAlchemy Async, Redis,
Alembic, and Docker Compose.

## Tech Stack

- Python 3.13
- FastAPI
- PostgreSQL 16
- SQLAlchemy Async / asyncpg
- Alembic
- Redis 7
- Pydantic v2
- uv
- Docker / Docker Compose

## Features

- JWT Authentication
- User Profile
- Workspace Management
- Workspace Member Management
- Role-Based Access Control (OWNER, EDITOR, VIEWER)
- Project CRUD and Archive
- Task CRUD
- Task Filtering and Pagination
- Project Labels
- Task Labels (Many-to-Many)
- Task Comments and Pagination
- Redis Task Caching
- Health Check
- Request Logging

## Requirements

Install Docker Desktop or another environment that
supports Docker Compose.

You do not need to install Python, PostgreSQL, or Redis
directly on your computer when using Docker Compose.

## Getting Started

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd taskhub
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and replace the placeholder values.

Use the same PostgreSQL password in:

- DATABASE_URL
- DOCKER_DATABASE_URL
- POSTGRES_PASSWORD

Generate a JWT secret with:

```bash
openssl rand -hex 32
```

Copy the generated value into SECRET_KEY.

### 3. Start the containers

```bash
docker compose up -d --build
```

This starts:

- FastAPI
- PostgreSQL
- Redis

### 4. Run database migrations

```bash
docker compose exec api uv run --no-sync alembic upgrade head
```

### 5. Open Swagger

http://localhost:8000/docs

### 6. Check application health

http://localhost:8000/api/v1/health

Expected response when PostgreSQL and Redis are healthy:

```json
{
  "status": "healthy",
  "services": {
    "database": "up",
    "redis": "up"
  }
}
```

## Project Structure

```text
app/
├── api/v1/        # API endpoints
├── core/          # Config, security, Redis, logging
├── db/            # Database session and Base
├── models/        # SQLAlchemy models
└── schemas/       # Pydantic schemas

alembic/           # Database migrations
Dockerfile
compose.yaml
pyproject.toml
uv.lock
```

## API Modules

| Module | Description |
|--------|-------------|
| Authentication | JWT authentication |
| Users | User profile |
| Workspaces | Workspace management |
| Projects | Project CRUD and archive |
| Tasks | CRUD, filtering, pagination |
| Labels | Label management |
| Task Labels | Attach and detach labels |
| Comments | Comment CRUD and pagination |
| Health | Database and Redis status |

For the complete endpoint list, see Swagger.

## Roles and Permissions

| Role | Read | Write |
|------|------|-------|
| OWNER | Yes | Yes |
| EDITOR | Yes | Yes |
| VIEWER | Yes | No |

Additional resource-specific permissions apply to comments
and archived projects.

## Useful Docker Commands

Start services:

```bash
docker compose up -d
```

Rebuild and start:

```bash
docker compose up -d --build
```

Show running containers:

```bash
docker compose ps
```

View API logs:

```bash
docker compose logs -f api
```

Check Alembic migration state:

```bash
docker compose exec api uv run --no-sync alembic current
```

Stop containers without deleting volumes:

```bash
docker compose down
```

## Redis Cache

Task list responses are cached in Redis with a short TTL.

Cache keys include project ID, cache version,
filters, and pagination parameters.

Task creation, updates, and deletion trigger cache
invalidation through version increments.

Authentication and authorization are checked before
serving cached data.

## Development Status

TaskHub is a learning project.

The core backend modules have been implemented.
Automated tests and production hardening are not yet complete.
