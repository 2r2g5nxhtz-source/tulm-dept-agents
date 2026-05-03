"""
Freight CRM tools — для @Tulm_freight_bot
Сохранение клиентов, заявок и котировок в БД.
"""
import os
import logging
import psycopg2
import psycopg2.extras
import urllib.request
import urllib.parse
import json
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "812770094"))
# Токен @merdan_tulm_bot — для уведомлений ГД о новых заявках
TASKBOT_TOKEN = os.environ.get("TASKBOT_NOTIFY_TOKEN", "")


def _conn():
    """Подключение к общей БД tulm_db (на Hetzner host через docker0 bridge),
    где живут freight_clients/requests/vendors/quotes — общие с taskbot."""
    return psycopg2.connect(os.getenv('CRM_DB_URL') or os.getenv('PG_CONNECTION_STRING'))


def _notify_admin(text: str) -> bool:
    """Отправить уведомление ГД через @merdan_tulm_bot (taskbot)."""
    if not TASKBOT_TOKEN:
        logger.warning("TASKBOT_NOTIFY_TOKEN не задан — пропускаю уведомление ГД")
        return False
    try:
        url = f"https://api.telegram.org/bot{TASKBOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": ADMIN_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
        if ok:
            logger.info(f"Уведомление ГД отправлено")
        return ok
    except Exception as e:
        logger.error(f"Ошибка уведомления ГД: {e}")
        return False


@tool
def register_client(name: str, country: str = "", contact_name: str = "",
                    phone: str = "", telegram: str = "", email: str = "") -> str:
    """Зарегистрировать клиента в БД ТЛЦТ. Если клиент уже есть — вернёт его id.
    Используй когда новая компания обращается с запросом на перевозку.
    name: название компании (обязательно)
    country: страна
    contact_name/phone/telegram/email: контактные данные представителя"""
    if not name.strip():
        return "❌ Имя компании обязательно"
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # upsert клиента
        cur.execute("""
            INSERT INTO freight_clients (name, country)
            VALUES (%s, %s)
            ON CONFLICT (name, country) DO UPDATE SET updated_at = NOW()
            RETURNING id, name, priority, created_at
        """, (name.strip(), country.strip() or None))
        client = cur.fetchone()

        # контакт
        if contact_name or phone or telegram or email:
            cur.execute("""
                INSERT INTO freight_client_contacts
                    (client_id, full_name, role, phone, telegram, email)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (client['id'], contact_name or None, 'основной',
                  phone or None, telegram or None, email or None))

        conn.commit()
        cur.close()
        conn.close()
        return (f"✅ Клиент **{client['name']}** id={client['id']} "
                f"(приоритет: {client['priority']}, регистрация: {client['created_at']:%Y-%m-%d})")
    except Exception as e:
        return f"❌ Ошибка БД: {e}"


@tool
def save_freight_request(
    client_name: str,
    origin: str,
    destination: str,
    mode: str,
    cargo_description: str,
    weight_ton: float = 0,
    raw_message: str = "",
    source_chat_id: int = 0,
    destination_country: str = "",
    cargo_type: str = "general",
    incoterms: str = "",
    pickup_date: str = "",
) -> str:
    """Сохранить фрахтовую заявку в БД ТЛЦТ.
    ВСЕГДА передавай source_chat_id — это ID отправителя в Telegram (нужен для дедупликации).
    Если ID отправителя уже присылал такую же заявку (тот же маршрут + груз) за последние 30 минут —
    система не создаст дубль, а вернёт существующий id.

    client_name: название компании клиента
    origin/destination: точки маршрута
    mode: sea / rail / multimodal / auto / air / unknown
    cargo_description: описание груза
    weight_ton: вес в тоннах (0 если не указан)
    raw_message: ТЕКСТ клиента дословно
    source_chat_id: Telegram user_id отправителя (передаётся системой)
    pickup_date: YYYY-MM-DD"""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. ДЕДУПЛИКАЦИЯ: same (chat_id + origin + destination + ~cargo) за последние 30 мин
        if source_chat_id:
            cur.execute("""
                SELECT id, created_at FROM freight_requests
                WHERE source_chat_id = %s
                  AND LOWER(origin) = LOWER(%s)
                  AND LOWER(destination) = LOWER(%s)
                  AND LOWER(LEFT(COALESCE(cargo_description,''), 30)) = LOWER(LEFT(%s, 30))
                  AND created_at > NOW() - INTERVAL '30 minutes'
                  AND status NOT IN ('cancelled')
                ORDER BY created_at DESC LIMIT 1
            """, (source_chat_id, origin.strip(), destination.strip(), cargo_description.strip()))
            existing = cur.fetchone()
            if existing:
                cur.close()
                conn.close()
                from datetime import timezone, timedelta
                t = existing['created_at'].astimezone(timezone(timedelta(hours=5)))
                return (f"ℹ️ Эта заявка уже зарегистрирована **#{existing['id']}** в {t:%H:%M} (Ашхабад). "
                        f"Не создаю дубль. Если нужно дополнить — напишите 'дополняю заявку #{existing['id']}'.")

        # 2. Найти/создать клиента
        cur.execute("""
            INSERT INTO freight_clients (name, country)
            VALUES (%s, %s)
            ON CONFLICT (name, country) DO UPDATE SET updated_at = NOW()
            RETURNING id
        """, (client_name.strip(), destination_country.strip() or None))
        client_id = cur.fetchone()['id']

        # 3. Создать заявку
        pd = pickup_date.strip() if pickup_date else None
        cur.execute("""
            INSERT INTO freight_requests (
                client_id, source, source_chat_id, raw_message,
                origin, destination, destination_country,
                mode, cargo_type, cargo_description, weight_ton,
                incoterms, pickup_date, status
            ) VALUES (
                %s, 'telegram', %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, 'new'
            )
            RETURNING id, created_at
        """, (
            client_id, source_chat_id or None, raw_message[:2000] or None,
            origin.strip() or None, destination.strip() or None, destination_country.strip() or None,
            mode.strip().lower() or 'unknown', cargo_type.strip().lower() or 'general',
            cargo_description.strip() or None, weight_ton or None,
            incoterms.strip().upper() or None, pd,
        ))
        req = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        # Уведомление ГД о новой заявке (Ашхабад UTC+5)
        from datetime import timezone, timedelta
        ashgabat_time = req['created_at'].astimezone(timezone(timedelta(hours=5)))
        wt_str = f"{weight_ton}т" if weight_ton else ""
        notification = (
            f"🆕 *Новая фрахтовая заявка #{req['id']}*\n\n"
            f"👤 Клиент: *{client_name}*\n"
            f"📦 Груз: {cargo_description} {wt_str}\n"
            f"🛣 Маршрут: {origin} → {destination} ({mode})\n"
            f"📅 Получена: {ashgabat_time:%Y-%m-%d %H:%M} (Ашхабад)\n\n"
            f"Команды:\n"
            f"`/quote {req['id']} vendor=<имя> price=<сумма>`\n"
            f"`/requests`"
        )
        _notify_admin(notification)

        return (f"✅ Заявка **#{req['id']}** принята: {origin}→{destination} ({mode}), "
                f"{cargo_description} {wt_str}. "
                f"Диспетчер свяжется в течение 24 часов.")
    except Exception as e:
        return f"❌ Ошибка сохранения: {e}"


@tool
def find_similar_requests(origin: str, destination: str, mode: str = "") -> str:
    """Найти похожие прошлые заявки по направлению.
    Используй чтобы дать клиенту ориентиры на основе нашей истории
    (но НЕ называй конкретные цены клиенту — это для внутренней справки)."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT request_count, avg_purchase_price, min_purchase, max_purchase,
                   avg_margin_pct, vendors_used, last_request_date
            FROM freight_direction_stats
            WHERE LOWER(origin) LIKE LOWER(%s)
              AND LOWER(destination) LIKE LOWER(%s)
              AND (%s = '' OR mode = %s)
            ORDER BY last_request_date DESC NULLS LAST
            LIMIT 3
        """, (f"%{origin}%", f"%{destination}%", mode, mode.lower()))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return f"📭 По направлению {origin}→{destination} ({mode or 'любой'}) истории нет — это новый маршрут для ТЛЦТ."

        lines = [f"📊 Найдено {len(rows)} похожих направлений:"]
        for r in rows:
            vendors = ", ".join(r['vendors_used']) if r['vendors_used'] else "—"
            lines.append(
                f"• {r['request_count']} заявок, средняя закупка: ${r['avg_purchase_price']}, "
                f"диапазон: ${r['min_purchase']}-${r['max_purchase']}, "
                f"маржа: {r['avg_margin_pct']}%, vendors: {vendors}"
            )
        lines.append("\n⚠️ ВНУТРЕННЯЯ справка — НЕ показывай эти цифры клиенту в ответе.")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка поиска истории: {e}"
