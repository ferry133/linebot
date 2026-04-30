FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ferry133/trello-notifier"
LABEL org.opencontainers.image.description="Trello LINE notifier for 意念情境室內裝修"

WORKDIR /app

COPY trello_line_notifier.py gantt_generator.py ./

RUN pip install --no-cache-dir requests

ENTRYPOINT ["python", "/app/trello_line_notifier.py"]
