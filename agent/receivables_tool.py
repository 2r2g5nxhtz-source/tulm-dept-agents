import psycopg2
import os
from langchain_core.tools import tool

@tool
def get_receivables_stats() -> str:
    """Статистика дебиторской задолженности ТЛЦТ — итоги по TMT и USD, топ должники.
    Используй когда спрашивают об общей дебиторке, итогах, сколько должны."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()

        # Итого по валютам (только дебиторы debit > credit)
        cur.execute("""
            SELECT currency, COUNT(*), SUM(debit - credit)
            FROM receivables
            WHERE debit > credit
            GROUP BY currency ORDER BY currency
        """)
        totals = cur.fetchall()

        # Топ-5 TMT
        cur.execute("""
            SELECT company, debit - credit as balance
            FROM receivables
            WHERE currency = 'TMT' AND debit > credit
            ORDER BY balance DESC LIMIT 5
        """)
        top_tmt = cur.fetchall()

        # Топ-5 USD
        cur.execute("""
            SELECT company, debit - credit as balance
            FROM receivables
            WHERE currency = 'USD' AND debit > credit
            ORDER BY balance DESC LIMIT 5
        """)
        top_usd = cur.fetchall()

        cur.close()
        conn.close()

        result = "📊 Дебиторская задолженность ТЛЦТ\n\n"
        for currency, count, total in totals:
            result += f"**{currency}:** {count} должников | Итого: **{total:,.2f} {currency}**\n"

        result += "\n🔴 Топ-5 TMT (по балансу):\n"
        for i, (company, balance) in enumerate(top_tmt, 1):
            result += f"  {i}. {company[:45]}: **{balance:,.0f} TMT**\n"

        result += "\n🔴 Топ-5 USD (по балансу):\n"
        for i, (company, balance) in enumerate(top_usd, 1):
            result += f"  {i}. {company[:45]}: **{balance:,.2f} USD**\n"

        return result
    except Exception as e:
        return f"Ошибка получения дебиторки: {e}"


@tool
def search_receivables(query: str) -> str:
    """Поиск должника в дебиторской задолженности ТЛЦТ по названию компании.
    Используй когда спрашивают о конкретной компании: 'сколько должен KSIT', 'долг Ынамлы улаг' и т.п."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()
        cur.execute("""
            SELECT company, debit, credit, debit - credit as balance, currency, type
            FROM receivables
            WHERE LOWER(company) LIKE LOWER(%s)
            ORDER BY ABS(debit - credit) DESC LIMIT 10
        """, (f'%{query}%',))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return f"Компания '{query}' не найдена в реестре дебиторки."

        result = f"🔍 Дебиторка по '{query}':\n\n"
        for company, debit, credit, balance, currency, tp in rows:
            status = "⬆️ ДОЛЖЕН" if balance > 0 else "✅ переплата"
            result += f"**{company}**\n"
            result += f"  Дт: {debit:,.2f} | Кт: {credit:,.2f} | Баланс: **{balance:,.2f} {currency}** {status}\n"
            if tp:
                result += f"  Тип: {tp}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка поиска: {e}"


@tool
def get_critical_receivables() -> str:
    """Критические должники ТЛЦТ — баланс > 100,000 (приоритетные к взысканию).
    Используй когда спрашивают о крупных долгах, критических должниках, риск-листе."""
    try:
        conn = psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))
        cur = conn.cursor()

        # TMT > 100k
        cur.execute("""
            SELECT company, debit - credit as balance, type
            FROM receivables
            WHERE currency = 'TMT' AND debit - credit > 100000
            ORDER BY balance DESC
        """)
        critical_tmt = cur.fetchall()

        # USD > 100k
        cur.execute("""
            SELECT company, debit - credit as balance, type
            FROM receivables
            WHERE currency = 'USD' AND debit - credit > 100000
            ORDER BY balance DESC
        """)
        critical_usd = cur.fetchall()

        cur.close()
        conn.close()

        result = "🚨 Критические должники (баланс > 100,000)\n\n"

        result += f"**TMT — {len(critical_tmt)} компаний:**\n"
        for i, (company, balance, tp) in enumerate(critical_tmt, 1):
            result += f"  {i}. {company[:50]}: **{balance:,.0f} TMT**\n"

        result += f"\n**USD — {len(critical_usd)} компаний:**\n"
        for i, (company, balance, tp) in enumerate(critical_usd, 1):
            result += f"  {i}. {company[:50]}: **{balance:,.2f} USD**\n"

        return result
    except Exception as e:
        return f"Ошибка: {e}"
