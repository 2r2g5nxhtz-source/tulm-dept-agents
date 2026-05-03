import psycopg2
import os
from langchain_core.tools import tool

_TYPE_MAP = {
    "жд": "Demirýol", "железнодорожный": "Demirýol", "железная дорога": "Demirýol",
    "аппарель": "Apparel",
    "мультимодал": "Multimodal", "мультимодальный": "Multimodal",
    "авто": "Awto", "автомобильный": "Awto",
    "авиа": "Awia", "авиационный": "Awia", "авиаперевозки": "Awia",
    "морской": "Deňiz", "море": "Deňiz",
    "фрахт": "Fraht",
    "вагон": "Wagon", "аренда вагонов": "Wagon kärende",
    "контейнер": "Konteýner", "аренда контейнеров": "Konteýner kärende",
    "склад": "Ammar",
    "агентство": "Agentlik", "агентский": "Agentlik",
    "поручение": "Tabşyryk",
}
_CURRENCY_MAP = {
    "tmt": "Manat", "манат": "Manat", "манаты": "Manat",
    "usd": "USD", "доллар": "USD", "доллары": "USD",
    "eur": "EUR", "евро": "EUR",
    "мульти": "Multiwalýuta", "мультивалюта": "Multiwalýuta", "мультивалютный": "Multiwalýuta",
}


def _map_type(value: str) -> str:
    if not value: return value
    return _TYPE_MAP.get(value.strip().lower(), value)


def _map_currency(value: str) -> str:
    if not value: return value
    return _CURRENCY_MAP.get(value.strip().lower(), value)


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
def search_contracts_filtered(contract_type: str = "", currency: str = "") -> str:
    """Перекрёстный поиск договоров ТЛЦТ по типу и/или валюте.
    Используй когда спрашивают: 'ЖД договоры в манатах', 'автомобильные в USD', 'все договоры типа ЖД'.
    contract_type: ЖД / автомобильный / морской / авиа / мультимодал / аппарель / фрахт / контейнер / вагон / склад
    currency: TMT (манаты) / USD (доллары) / EUR (евро) / мультивалюта.
    Русские термины автоматически переводятся в туркменские (Demirýol, Manat, и т.д.)."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()

        conditions = []
        params = []

        contract_type = _map_type(contract_type)
        currency = _map_currency(currency)

        if contract_type:
            conditions.append("LOWER(type) LIKE LOWER(%s)")
            params.append(f'%{contract_type}%')
        if currency:
            conditions.append("LOWER(currency) LIKE LOWER(%s)")
            params.append(f'%{currency}%')

        if not conditions:
            return "Укажи хотя бы один фильтр: тип договора или валюту."

        where_clause = " AND ".join(conditions)
        cur.execute(f"""
            SELECT number, date, company, director, status, type, currency, phone
            FROM contracts
            WHERE {where_clause}
            ORDER BY id LIMIT 10
        """, params)

        rows = cur.fetchall()

        # Считаем общее количество по фильтру
        cur.execute(f"SELECT COUNT(*) FROM contracts WHERE {where_clause}", params)
        total = cur.fetchone()[0]

        cur.close()
        conn.close()

        if not rows:
            filter_desc = []
            if contract_type:
                filter_desc.append(f"тип={contract_type}")
            if currency:
                filter_desc.append(f"валюта={currency}")
            return f"Договоры по фильтру [{', '.join(filter_desc)}] не найдены."

        filter_desc = []
        if contract_type:
            filter_desc.append(f"тип: {contract_type}")
        if currency:
            filter_desc.append(f"валюта: {currency}")

        result = f"📋 Договоры [{', '.join(filter_desc)}] — всего {total}, показываю первые {len(rows)}:\n\n"
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
