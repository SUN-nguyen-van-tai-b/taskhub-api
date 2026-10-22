FROM python:3.13-slim

WORKDIR /app

# Cài uv để quản lý dependencies.
RUN pip install --no-cache-dir uv

# Copy metadata trước để tận dụng Docker build cache.
COPY pyproject.toml uv.lock ./

# Cài dependencies vào .venv.
RUN uv sync --frozen --no-dev

# Copy source code.
COPY . .

EXPOSE 8000

# Chạy FastAPI trong container.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]