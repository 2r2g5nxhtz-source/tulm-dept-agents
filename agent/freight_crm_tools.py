"""
Freight CRM tools — для @Tulm_freight_bot
Сохранение клиентов, заявок и котировок в БД.
"""
import os
import psycopg2
import psycopg2.extras
from langchain_core.tools import tool

ADMIN_CHAT_ID = 812770094  # ГД ТЛЦТ — получает уведомления о новых заявках


def _conn():
    return psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))


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
    Вызывай ВСЕГДА после получения запроса от клиента.
    client_name: название компании клиента (обязательно)
    origin/destination: точки маршрута
    mode: sea / rail / multimodal / auto / air
    cargo_description: описание груза словами
    weight_ton: вес в тоннах (0 если не указан)
    raw_message: исходное сообщение клиента дословно
    pickup_date: дата отгрузки в формате YYYY-MM-DD (пусто если не указана)"""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Найти/создать клиента
        cur.execute("""
            INSERT INTO freight_clients (name, country)
            VALUES (%s, %s)
            ON CONFLICT (name, country) DO UPDATE SET updated_at = NOW()
            RETURNING id
        """, (client_name.strip(), destination_country.strip() or None))
        client_id = cur.fetchone()['id']

        # 2. Создать заявку
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

        return (f"✅ Заявка **#{req['id']}** сохранена\n"
                f"Клиент: {client_name} (id={client_id})\n"
                f"Маршрут: {origin} → {destination} ({mode})\n"
                f"Груз: {cargo_description} {weight_ton}т\n"
                f"Статус: NEW — назначена ГД для распределения\n\n"
                f"📨 Уведомление отправлено в @merdan_tulm_bot")
    except Exception as e:
        return f"❌ Ошибка сохранения заявки: {e}"


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
