taskhub/
├── app/
│ ├── **init**.py
│ ├── main.py
│ ├── api/
│ │ ├── **init**.py
│ │ └── v1/
│ │ ├── **init**.py
│ │ ├── router.py
│ │ ├── auth.py
│ │ ├── users.py
│ │ ├── workspaces.py
│ │ ├── projects.py
│ │ └── tasks.py
│ ├── core/
│ │ ├── config.py
│ │ ├── security.py
│ │ └── permissions.py
│ ├── db/
│ │ ├── base.py
│ │ └── session.py
│ ├── models/
│ ├── schemas/
│ ├── services/
│ └── dependencies/
├── alembic/
├── tests/
├── Dockerfile
├── compose.yaml
├── .env
├── .env.example
├── pyproject.toml
└── uv.lock
