import psycopg2
import os
from langchain_core.tools import tool

@tool
def search_contracts(query: str) -> str:
    """Поиск договоров ТЛЦТ по названию компании, номеру договора или имени директора.
    Используй когда спрашивают о конкретной компании, договоре или партнёре."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()
        cur.execute("""
            SELECT number, date, company, director, status, type, currency, phone
            FROM contracts
            WHERE
                LOWER(company) LIKE LOWER(%s) OR
                LOWER(number) LIKE LOWER(%s) OR
                LOWER(director) LIKE LOWER(%s)
            ORDER BY id LIMIT 5
        """, (f'%{query}%', f'%{query}%', f'%{query}%'))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return f"Договоры по '{query}' не найдены в реестре ТЛЦТ."
        result = f"Найдено {len(rows)} договор(ов) по '{query}':\n\n"
        for r in rows:
            result += f"№{r[0]} от {r[1]}\n"
            result += f"  Компания: {r[2]}\n"
            result += f"  Директор: {r[3]}\n"
            result += f"  Статус: {r[4]} | Тип: {r[5]} | Валюта: {r[6]}\n"
            if r[7] and str(r[7]) != 'nan':
                result += f"  Тел: {r[7]}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка поиска: {e}"

@tool
def get_contracts_stats() -> str:
    """Статистика по реестру договоров ТЛЦТ — общее количество, по типам и статусам."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM contracts")
        total = cur.fetchone()[0]
        cur.execute("SELECT status, COUNT(*) FROM contracts GROUP BY status ORDER BY COUNT(*) DESC")
        statuses = cur.fetchall()
        cur.execute("SELECT type, COUNT(*) FROM contracts GROUP BY type ORDER BY COUNT(*) DESC LIMIT 7")
        types = cur.fetchall()
        cur.execute("SELECT currency, COUNT(*) FROM contracts GROUP BY currency ORDER BY COUNT(*) DESC")
        currencies = cur.fetchall()
        cur.close()
        conn.close()
        result = f"📊 Реестр договоров ТЛЦТ\n\nВсего: {total}\n\nПо статусу:\n"
        for s, c in statuses:
            result += f"  {s}: {c}\n"
        result += "\nПо типу:\n"
        for t, c in types:
            result += f"  {t}: {c}\n"
        result += "\nПо валюте:\n"
        for c, n in currencies:
            result += f"  {c}: {n}\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"
