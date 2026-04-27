import psycopg2
from dotenv import load_dotenv
import os

load_dotenv('.env')

def search_contracts(query: str, limit: int = 5) -> str:
    """Поиск договоров по названию компании или номеру"""
    conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
    cur = conn.cursor()
    
    cur.execute("""
        SELECT number, date, company, director, status, type, currency, phone
        FROM contracts
        WHERE 
            LOWER(company) LIKE LOWER(%s) OR
            LOWER(number) LIKE LOWER(%s) OR
            LOWER(director) LIKE LOWER(%s)
        LIMIT %s
    """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return f"Договоры по запросу '{query}' не найдены."
    
    result = f"Найдено договоров: {len(rows)}\n\n"
    for r in rows:
        result += f"№{r[0]} | {r[1]} | {r[2]}\n"
        result += f"  Директор: {r[3]}\n"
        result += f"  Статус: {r[4]} | Тип: {r[5]} | Валюта: {r[6]}\n"
        if r[7] and r[7] != 'nan':
            result += f"  Тел: {r[7]}\n"
        result += "\n"
    
    return result

# Тест
if __name__ == "__main__":
    print(search_contracts("Meno"))
    print("---")
    print(search_contracts("001"))
