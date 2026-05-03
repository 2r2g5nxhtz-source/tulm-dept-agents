FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir python-telegram-bot==20.7
COPY bot.py webhook_server.py start.sh ./
RUN chmod +x start.sh
CMD ["./start.sh"]
