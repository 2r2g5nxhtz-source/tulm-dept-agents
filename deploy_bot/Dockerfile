FROM python:3.11-slim
WORKDIR /app

# docker CLI + git нужны для деплоя ботам через бот/webhook
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir python-telegram-bot==20.7
COPY bot.py webhook_server.py start.sh ./
RUN chmod +x start.sh
CMD ["./start.sh"]
