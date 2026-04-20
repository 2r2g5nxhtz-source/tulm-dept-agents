import psycopg2
import os

def search_contracts(query: str, limit: int = 5) -> str:
    """Поиск договоров по компании, номеру или директору"""
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
            ORDER BY id
            LIMIT %s
        """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if not rows:
            return f"Договоры по запросу '{query}' не найдены в реестре."
        
        result = f"Найдено: {len(rows)} договор(ов) по '{query}'\n\n"
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

def search_contracts_filtered(contract_type: str = "", currency: str = "") -> str:
    """Перекрёстный поиск договоров по типу и/или валюте (например: ЖД + TMT)"""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()

        conditions = []
        params = []

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

def get_contracts_stats() -> str:
    """Статистика по реестру договоров"""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM contracts")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT status, COUNT(*) FROM contracts GROUP BY status ORDER BY COUNT(*) DESC")
        statuses = cur.fetchall()
        
        cur.execute("SELECT type, COUNT(*) FROM contracts GROUP BY type ORDER BY COUNT(*) DESC LIMIT 6")
        types = cur.fetchall()
        
        cur.execute("SELECT currency, COUNT(*) FROM contracts GROUP BY currency ORDER BY COUNT(*) DESC")
        currencies = cur.fetchall()
        
        cur.close()
        conn.close()
        
        result = f"📊 Реестр договоров ТЛЦТ\n\n"
        result += f"Всего: {total} договоров\n\n"
        result += "По статусу:\n"
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
