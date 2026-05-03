FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir python-telegram-bot==20.7
COPY bot.py webhook_server.py ./
CMD ["python", "webhook_server.py"]
