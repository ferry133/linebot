FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ferry133/linebot"
LABEL org.opencontainers.image.description="LINE customer service bot for 意念情境室內裝修"

WORKDIR /app

COPY trello_line_notifier.py linebot_server.py gantt_generator.py ./

RUN pip install --no-cache-dir requests flask anthropic

# 兩種執行模式（由 k8s workload 的 command 指定）：
#   Webhook server:  python /app/linebot_server.py
#   CronJob:         python /app/trello_line_notifier.py [morning|noon|evening]
