FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY agents ./agents
COPY models.yaml .
COPY data ./data
COPY prototype ./prototype
COPY frontend/dist ./frontend/dist
# servers use the raw API: set ANTHROPIC_API_KEY (+ ANTHROPIC_WORKSPACE_ID if identity-linked)
ENV FORCE_PROVIDER=anthropic
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
