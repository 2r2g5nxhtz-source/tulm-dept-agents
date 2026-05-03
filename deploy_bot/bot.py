"""
TULM Deploy Bot — управление Hetzner через Telegram
Команды: /deploy /status /logs <бот>
Авторизация: только ADMIN_CHAT_ID
"""
import os, subprocess, asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["DEPLOY_BOT_TOKEN"]
APP_DIR = os.environ.get("REPO_DIR", "/repo")
COMPOSE_FILE = os.environ.get("COMPOSE_FILE", f"{APP_DIR}/docker-compose.prod.yml")

# Whitelist: ADMIN_CHAT_ID или ALLOWED_USERS (csv) — список разрешённых chat_id
_raw_admin = os.environ.get("ADMIN_CHAT_ID", "0")
_raw_allowed = os.environ.get("ALLOWED_USERS", "")
_ids = {int(x.strip()) for x in (_raw_admin + "," + _raw_allowed).split(",") if x.strip().isdigit()}
ADMIN_IDS = _ids - {0}

def is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_IDS

async def run(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=APP_DIR
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
    return out.decode("utf-8", errors="replace")[-3000:]

async def cmd_deploy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text("🚀 Деплой запущен...")
    result = await run(
        f"git pull origin main && "
        f"docker compose -f {COMPOSE_FILE} up -d --build 2>&1"
    )
    await update.message.reply_text(f"✅ Готово:\n```\n{result[-2000:]}\n```", parse_mode="Markdown")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    result = await run(f"docker compose -f {COMPOSE_FILE} ps 2>&1")
    await update.message.reply_text(f"```\n{result}\n```", parse_mode="Markdown")

async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    args = ctx.args
    service = args[0] if args else "finance-bot"
    result = await run(f"docker compose -f {COMPOSE_FILE} logs --tail=50 {service} 2>&1")
    await update.message.reply_text(f"```\n{result[-2000:]}\n```", parse_mode="Markdown")

async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    args = ctx.args
    service = args[0] if args else ""
    if not service:
        await update.message.reply_text("Использование: /restart <имя-сервиса>\nПример: /restart finance-bot")
        return
    result = await run(f"docker compose -f {COMPOSE_FILE} restart {service} 2>&1")
    await update.message.reply_text(f"♻️ Перезапущен {service}:\n```\n{result}\n```", parse_mode="Markdown")

async def run_on_host(cmd: str) -> str:
    """Выполнить команду НА ХОСТЕ через одноразовый docker-контейнер с mount /:/host"""
    escaped = cmd.replace('"', '\\"')
    docker_cmd = (
        f'docker run --rm --pid=host --network=host '
        f'-v /:/host -w /host/root '
        f'alpine sh -c "chroot /host sh -c \\"{escaped}\\""'
    )
    proc = await asyncio.create_subprocess_shell(
        docker_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
    return out.decode("utf-8", errors="replace")[-3000:]


async def cmd_sh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выполнить shell-команду. По умолчанию — внутри контейнера в /repo.
    Префикс `host:` — выполнить на хосте Hetzner (через docker chroot)."""
    if not is_admin(update): return
    raw = update.message.text.partition(' ')[2].strip()
    if not raw:
        await update.message.reply_text(
            "Использование: /sh <команда>\n\n"
            "По умолчанию выполняется в контейнере (cwd=/repo).\n"
            "Префикс `host:` выполняет на хосте Hetzner.\n\n"
            "Примеры:\n"
            "• /sh ls — список файлов /repo\n"
            "• /sh docker ps — список контейнеров\n"
            "• /sh host: ls /root — корень хоста\n"
            "• /sh host: df -h — место на диске хоста\n"
            "• /sh host: cat /root/tulm-dept-agents/.env"
        )
        return

    on_host = raw.startswith("host:")
    cmd = raw[5:].strip() if on_host else raw
    target = "🖥️ host" if on_host else "📦 container"
    await update.message.reply_text(f"⚙️ {target}: `{cmd[:200]}`", parse_mode="Markdown")
    try:
        result = await (run_on_host(cmd) if on_host else run(cmd))
    except asyncio.TimeoutError:
        result = "[timeout 300s]"
    if not result.strip():
        result = "(пустой вывод)"
    chunk = result[-3500:]
    await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Расширенный health-check: контейнеры + uptime + диск + RAM хоста"""
    if not is_admin(update): return
    await update.message.reply_text("🩺 Собираю health-check...")
    # docker ps — через docker.sock (внутри контейнера, есть docker CLI)
    containers = await run("docker ps --format '{{.Names}}|{{.Status}}' 2>&1 | grep -E 'tulm-dept-agents|tulm-' | sort | awk -F'|' '{printf \"%-42s %s\\n\", $1, $2}'")
    # uptime / df / free хоста — через chroot (внутри slim нет этих утилит)
    uptime = await run_on_host("uptime")
    disk = await run_on_host("df -h /")
    ram = await run_on_host("free -h")

    msg = (
        "📦 *Контейнеры:*\n```\n" + (containers[:1800] or "(нет)") + "\n```\n"
        "⏱️ *Uptime:* `" + uptime.strip()[:120] + "`\n"
        "💾 *Диск:*\n```\n" + disk[:300] + "\n```\n"
        "🧠 *RAM:*\n```\n" + ram[:300] + "\n```"
    )
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")


async def cmd_allow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Добавить chat_id в whitelist dept-бота. Пример: /allow ves 562755251"""
    if not is_admin(update): return
    args = ctx.args
    if len(args) != 2:
        await update.message.reply_text(
            "Использование: `/allow <бот> <chat_id>`\n"
            "Боты: finance, ves, railway, maritime\n"
            "Пример: `/allow maritime 562755251`",
            parse_mode="Markdown"
        )
        return
    bot, chat_id = args[0].lower(), args[1]
    if bot not in {"finance","ves","railway","maritime"}:
        await update.message.reply_text(f"❌ Неизвестный бот: {bot}. Доступны: finance, ves, railway, maritime")
        return
    if not chat_id.lstrip("-").isdigit():
        await update.message.reply_text(f"❌ chat_id должен быть числом, получил: {chat_id}")
        return
    env_file = ".env" if bot == "finance" else f".env.{bot}"
    # Хост-команда: добавить chat_id в ALLOWED_USERS этого бота, перезапустить контейнер
    cmd = (
        f"cd /repo && "
        f"if grep -q '^ALLOWED_USERS=' {env_file}; then "
        f"  sed -i 's/^ALLOWED_USERS=\\(.*\\)$/ALLOWED_USERS=\\1,{chat_id}/' {env_file}; "
        f"else "
        f"  echo 'ALLOWED_USERS={chat_id}' >> {env_file}; "
        f"fi && "
        f"docker rm -f tulm-dept-agents_{bot}-bot_1 2>/dev/null; "
        f"export COMPOSE_PROJECT_NAME=tulm-dept-agents && "
        f"docker compose -f docker-compose.prod.yml up -d --no-deps {bot}-bot 2>&1 | tail -3"
    )
    await update.message.reply_text(f"⚙️ Добавляю `{chat_id}` в `{bot}-bot`...", parse_mode="Markdown")
    result = await run_on_host(cmd)
    await update.message.reply_text(
        f"✅ Готово. Сервис пересоздан.\n```\n{result[-1500:]}\n```",
        parse_mode="Markdown"
    )


async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запустить pg_dump всех 4 БД на хосте. Авто-cron в 03:00 UTC ежедневно."""
    if not is_admin(update): return
    await update.message.reply_text("💾 Запускаю backup всех 4 БД...")
    result = await run_on_host("/root/backup-pg.sh && tail -10 /root/backups/backup.log")
    today = (await run_on_host("date +%F")).strip()
    sizes = await run_on_host(f"ls -lah /root/backups/{today}/ | tail -n +2")
    msg = (
        f"✅ *Backup готов:* `/root/backups/{today}/`\n\n"
        f"*Лог:*\n```\n{result[-800:]}\n```\n"
        f"*Файлы:*\n```\n{sizes[:600]}\n```"
    )
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")


async def cmd_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает твой chat_id, username и admin-статус. Открыто всем (helper для добавления админов)"""
    u = update.effective_user
    role = "✅ admin" if is_admin(update) else "❌ not in whitelist"
    msg = (
        f"👤 *Ваш Telegram:*\n"
        f"chat_id: `{u.id}`\n"
        f"username: @{u.username or '—'}\n"
        f"имя: {u.first_name or ''} {u.last_name or ''}\n"
        f"роль: {role}\n\n"
        f"Текущий whitelist: `{sorted(ADMIN_IDS)}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text(
            f"❌ Доступ запрещён.\n"
            f"Ваш chat_id: `{update.effective_user.id}`\n"
            f"Попросите Мердана добавить вас в whitelist.",
            parse_mode="Markdown"
        )
        return
    await update.message.reply_text(
        "🤖 TULM Hetzner Bot\n\n"
        "📊 *Информация:*\n"
        "/status — `docker compose ps`\n"
        "/health — контейнеры + uptime + диск + RAM\n"
        "/me — мой chat_id и whitelist\n"
        "/logs <бот> — логи 50 строк\n\n"
        "🚀 *Управление:*\n"
        "/deploy — git pull + пересобрать всё\n"
        "/restart <бот> — перезапуск\n"
        "/backup — pg_dump всех 4 БД (auto cron 03:00 UTC)\n"
        "/allow <бот> <chat_id> — добавить пользователя в whitelist отдела\n\n"
        "🔧 *Произвольные команды:*\n"
        "/sh <cmd> — в контейнере (cwd=/repo)\n"
        "/sh host: <cmd> — на хосте Hetzner\n\n"
        "Имена ботов: finance-bot, ves-bot, railway-bot, maritime-bot",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("allow", cmd_allow))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("sh", cmd_sh))
    app.run_polling()

if __name__ == "__main__":
    main()
