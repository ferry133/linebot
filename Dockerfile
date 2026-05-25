FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ferry133/linebot"
LABEL org.opencontainers.image.description="LINE customer service bot for 意念情境室內裝修"

WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

COPY trello_line_notifier.py linebot_server.py gantt_generator.py ./
COPY migrations/ ./migrations/
COPY shared/ ./shared/
COPY agents/ ./agents/
COPY gateway/ ./gateway/

RUN pip install --no-cache-dir requests flask anthropic psycopg2-binary "paho-mqtt>=2.0" pyyaml

# 執行模式（由 k8s workload 的 command 指定）：
#   LINE Gateway:    python /app/gateway/line_gateway.py
#   Customer Agent:  python /app/agents/customer_service.py
#   CronJob:         python /app/trello_line_notifier.py [morning|noon|evening]
#   Legacy server:   python /app/linebot_server.py  (過渡期保留)
