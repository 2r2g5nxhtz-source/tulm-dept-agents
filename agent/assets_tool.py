import psycopg2
import os
from langchain_core.tools import tool


def _conn():
    return psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))


@tool
def get_assets_summary() -> str:
    """Сводка по основным средствам ТЛЦТ — итого по категориям, общая стоимость.
    Используй когда спрашивают об основных средствах, балансе, имуществе компании."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT category, COUNT(*), SUM(quantity), SUM(total_cost)
            FROM fixed_assets
            GROUP BY category
            ORDER BY SUM(total_cost) DESC
        """)
        rows = cur.fetchall()
        cur.execute("SELECT SUM(total_cost), SUM(quantity) FROM fixed_assets")
        total_cost, total_qty = cur.fetchone()
        cur.close(); conn.close()

        result = "📦 Основные средства ТЛЦТ — 2026 Q1\n\n"
        result += f"**Итого позиций: 143 | Общая стоимость: {total_cost:,.2f} TMT**\n\n"
        result += "По категориям:\n"
        for cat, cnt, qty, cost in rows:
            pct = cost / total_cost * 100
            result += f"  • {cat}: {cnt} поз. | {cost:,.0f} TMT ({pct:.1f}%)\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"


@tool
def search_assets(query: str) -> str:
    """Поиск основного средства ТЛЦТ по названию.
    Используй когда спрашивают о конкретном оборудовании, мебели, технике: 'где принтеры', 'сколько контейнеров', 'Toyota' и т.п."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT num, name, quantity, unit_cost, total_cost, category
            FROM fixed_assets
            WHERE LOWER(name) LIKE LOWER(%s)
            ORDER BY total_cost DESC
            LIMIT 15
        """, (f'%{query}%',))
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            return f"Ничего не найдено по запросу '{query}'."

        result = f"🔍 Основные средства по '{query}':\n\n"
        for num, name, qty, uc, tc, cat in rows:
            result += f"**{num}. {name}**\n"
            result += f"   Кол-во: {qty:.0f} | Стоимость: **{tc:,.2f} TMT** | [{cat}]\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"


@tool
def get_assets_by_category(category: str) -> str:
    """Список основных средств ТЛЦТ по категории.
    Категории: IT, ПО, Мебель, Контейнеры, Транспорт, Бытовая техника, Лицензии, Прочее.
    Используй когда спрашивают 'покажи всё IT оборудование', 'список мебели', 'контейнерный парк'."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT num, name, quantity, total_cost
            FROM fixed_assets
            WHERE LOWER(category) = LOWER(%s)
            ORDER BY total_cost DESC
        """, (category,))
        rows = cur.fetchall()
        cur.execute("SELECT SUM(total_cost) FROM fixed_assets WHERE LOWER(category)=LOWER(%s)", (category,))
        total = cur.fetchone()[0] or 0
        cur.close(); conn.close()

        if not rows:
            return f"Категория '{category}' не найдена. Доступные: IT, ПО, Мебель, Контейнеры, Транспорт, Бытовая техника, Лицензии, Прочее."

        result = f"📋 {category} — {len(rows)} позиций | Итого: **{total:,.2f} TMT**\n\n"
        for num, name, qty, tc in rows:
            result += f"  {num}. {name[:55]} × {qty:.0f} = {tc:,.0f} TMT\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"


@tool
def get_top_assets(limit: int = 10) -> str:
    """Топ самых дорогих основных средств ТЛЦТ.
    Используй когда спрашивают о дорогостоящем имуществе, самых ценных активах."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT num, name, quantity, total_cost, category
            FROM fixed_assets
            ORDER BY total_cost DESC
            LIMIT %s
        """, (min(limit, 20),))
        rows = cur.fetchall()
        cur.close(); conn.close()

        result = f"🏆 Топ-{len(rows)} дорогих активов ТЛЦТ:\n\n"
        for i, (num, name, qty, tc, cat) in enumerate(rows, 1):
            result += f"  {i}. {name[:50]} × {qty:.0f}\n     **{tc:,.0f} TMT** [{cat}]\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"
