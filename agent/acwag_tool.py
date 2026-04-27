import psycopg2
import os
from langchain_core.tools import tool


@tool
def get_acwag_stats() -> str:
    """Статистика по реестру ACWAG — количество вагонов по годам, тарифы, стыки.
    Используй когда спрашивают: 'сколько вагонов прошло', 'статистика ACWAG', 'тариф по годам'."""
    try:
        conn = psycopg2.connect(os.getenv("PG_CONNECTION_STRING"))
        cur  = conn.cursor()

        # По годам
        cur.execute("""
            SELECT year, COUNT(*) as batches, SUM(wagon_count) as wagons,
                   MAX(baha) as tariff
            FROM acwag_records
            GROUP BY year ORDER BY year
        """)
        by_year = cur.fetchall()

        # По стыкам
        cur.execute("""
            SELECT styk, SUM(wagon_count) as wagons
            FROM acwag_records
            GROUP BY styk ORDER BY wagons DESC
        """)
        by_styk = cur.fetchall()

        # Итого
        cur.execute("SELECT COUNT(*), SUM(wagon_count) FROM acwag_records")
        total_batches, total_wagons = cur.fetchone()

        cur.close()
        conn.close()

        result = "📊 Реестр ACWAG (вагоны через границу)\n\n"
        result += f"Всего партий: {total_batches} | Всего вагонов: **{total_wagons:,}**\n\n"
        result += "По годам:\n"
        for year, batches, wagons, tariff in by_year:
            wagons_str = f"{wagons:,}" if wagons else "—"
            tariff_str = f"{tariff:.0f} USD/ваг" if tariff else "—"
            result += f"  {year}: **{wagons_str} вагонов** ({batches} партий) | тариф {tariff_str}\n"

        result += "\nПо стыку:\n"
        for styk, wagons in by_styk:
            result += f"  {styk}: {wagons:,} вагонов\n"

        return result
    except Exception as e:
        return f"Ошибка получения статистики ACWAG: {e}"


@tool
def search_acwag_by_company(query: str) -> str:
    """Поиск записей ACWAG по названию компании/экспедитора.
    Используй когда спрашивают: 'сколько вагонов у Raykam', 'ACWAG Zaveh Torbat', 'история перевозок компании X'.
    ВАЖНО: ищет по первому слову запроса чтобы найти все варианты написания компании."""
    try:
        conn = psycopg2.connect(os.getenv("PG_CONNECTION_STRING"))
        cur  = conn.cursor()

        # Берём первое слово запроса как корень — ловим "Raykam Logistic" / "Raykam Logistics" / "Raykam"
        root = query.strip().split()[0] if query.strip() else query

        cur.execute("""
            SELECT year, COUNT(*) as batches,
                   SUM(wagon_count) as total_wagons,
                   MIN(wagon_date) as first_date,
                   MAX(wagon_date) as last_date,
                   MAX(baha) as tariff
            FROM acwag_records
            WHERE LOWER(company) LIKE LOWER(%s)
            GROUP BY year
            ORDER BY year DESC
        """, (f"%{root}%",))
        rows = cur.fetchall()

        # Итог
        cur.execute("""
            SELECT COUNT(*), SUM(wagon_count)
            FROM acwag_records WHERE LOWER(company) LIKE LOWER(%s)
        """, (f"%{root}%",))
        total_b, total_w = cur.fetchone()

        cur.close()
        conn.close()

        if not rows:
            return f"Компания '{query}' не найдена в реестре ACWAG."

        result = f"🔍 ACWAG — **{query}** — итого **{total_w:,} вагонов** за все годы\n\n"
        result += "По годам:\n"
        for year, batches, wagons, first_d, last_d, tariff in rows:
            wagons_str = f"{wagons:,}" if wagons else "—"
            result += f"  **{year}**: {wagons_str} ваг. ({batches} партий)"
            if first_d:
                result += f" | {first_d} → {last_d}"
            if tariff:
                result += f" | {tariff:.0f} USD/ваг"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка поиска ACWAG: {e}"


@tool
def search_acwag_filtered(year: int = 0, styk: str = "", company: str = "") -> str:
    """Фильтрованный поиск по реестру ACWAG.
    Используй когда нужно: 'вагоны за 2024', 'через Сарахс в 2025', 'Akyayla 2023'.
    year: год (0 = все годы)
    styk: стык (Sarahs / Akyayla, пустая = все)
    company: название компании (пустая = все)"""
    try:
        conn = psycopg2.connect(os.getenv("PG_CONNECTION_STRING"))
        cur  = conn.cursor()

        conditions = []
        params = []

        if year and year > 0:
            conditions.append("year = %s")
            params.append(year)
        if styk:
            conditions.append("LOWER(styk) LIKE LOWER(%s)")
            params.append(f"%{styk}%")
        if company:
            conditions.append("LOWER(company) LIKE LOWER(%s)")
            params.append(f"%{company}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(f"""
            SELECT year, styk, company, wagon_date, wagon_count, acwag_code, baha
            FROM acwag_records
            {where}
            ORDER BY wagon_date DESC
            LIMIT 15
        """, params)
        rows = cur.fetchall()

        cur.execute(f"""
            SELECT COUNT(*), SUM(wagon_count)
            FROM acwag_records {where}
        """, params)
        total_r, total_w = cur.fetchone()

        cur.close()
        conn.close()

        if not rows:
            return "По заданным фильтрам записей не найдено."

        filters_desc = []
        if year: filters_desc.append(f"год={year}")
        if styk: filters_desc.append(f"стык={styk}")
        if company: filters_desc.append(f"компания={company}")
        desc = ", ".join(filters_desc) if filters_desc else "все записи"

        result = f"📋 ACWAG [{desc}] — всего {total_r} партий, **{total_w:,} вагонов**\n"
        result += f"Показываю последние {len(rows)}:\n\n"
        for yr, styk_, comp, dt, cnt, code, baha in rows:
            cnt_str = f"{cnt}" if cnt else "—"
            baha_str = f"{baha:.0f} USD" if baha else "—"
            result += f"  {dt} | {comp} | {cnt_str} ваг. | {styk_} | {code} | {baha_str}\n"
        return result
    except Exception as e:
        return f"Ошибка фильтрации ACWAG: {e}"
