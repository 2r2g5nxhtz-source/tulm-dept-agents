"""
TULM Deploy Bot — управление Hetzner через Telegram
Команды: /deploy /status /logs <бот>
Авторизация: только ADMIN_CHAT_ID
"""
import os, subprocess, asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["DEPLOY_BOT_TOKEN"]
ADMIN_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
COMPOSE_FILE = "/app/docker-compose.prod.yml"
APP_DIR = "/app"

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

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

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text(
        "🤖 TULM Deploy Bot\n\n"
        "/deploy — git pull + пересобрать все боты\n"
        "/status — статус контейнеров\n"
        "/logs <бот> — логи (finance-bot/ves-bot/railway-bot/maritime-bot)\n"
        "/restart <бот> — перезапустить контейнер"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.run_polling()

if __name__ == "__main__":
    main()
