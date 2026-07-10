FROM python:3.11-alpine

RUN pip install --no-cache-dir requests

COPY src/ci_triage_agent/ /app/ci_triage_agent/

WORKDIR /app

CMD ["python", "-m", "ci_triage_agent.cli.watcher_entry"]
