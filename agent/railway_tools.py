import psycopg2
import os
from langchain_core.tools import tool
from datetime import datetime

def _conn():
    return psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))

# ─────────────────────────────────────────────
# 1. АСВАК — коды TRK / ACWAG
# ─────────────────────────────────────────────

@tool
def add_trk_code(code_value: str, code_type: str, company: str,
                 route_from: str, route_to: str,
                 wagon_number: str = "", currency: str = "TMT",
                 freight_cost: float = 0.0) -> str:
    """Добавить новый код TRK или ACWAG в реестр АСВАК.
    code_type: 'TRK' (СНГ, 9 цифр) или 'ACWAG' (не-СНГ, Сарахс/Этрек).
    currency: TMT или USD.
    Используй когда просят выдать, добавить, зарегистрировать код."""
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO aswak_codes
              (code_value, code_type, company, route_from, route_to,
               wagon_number, currency, freight_cost, status, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'FREE',now())
            RETURNING id
        """, (code_value.strip().upper(), code_type.upper(), company,
                route_from, route_to, wagon_number or None,
                currency.upper(), freight_cost or 0))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        return (f"✅ Код {code_type.upper()} зарегистрирован\n"
                f"  Код: {code_value.upper()}\n"
                f"  Компания: {company}\n"
                f"  Маршрут: {route_from} → {route_to}\n"
                f"  Валюта: {currency} | Фрахт: {freight_cost}\n"
                f"  ID записи: {rec_id}")
    except Exception as e:
        return f"Ошибка добавления кода: {e}"

@tool
def revoke_trk_code(code_value: str, reason: str = "") -> str:
    """Отозвать (аннулировать) код TRK или ACWAG по значению кода.
    Используй когда просят отозвать, аннулировать, отменить код."""
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            UPDATE aswak_codes SET status='REVOKED', revoke_reason=%s, updated_at=now()
            WHERE code_value=%s AND status != 'REVOKED'
            RETURNING code_value, company, code_type
        """, (reason or 'Отозван по запросу', code_value.strip().upper()))
        row = cur.fetchone()
        db.commit(); cur.close(); db.close()
        if not row:
            return f"❌ Код {code_value.upper()} не найден или уже отозван."
        return (f"🔴 Код {row[2]} отозван\n"
                f"  Код: {row[0]}\n"
                f"  Компания: {row[1]}\n"
                f"  Причина: {reason or 'не указана'}")
    except Exception as e:
        return f"Ошибка отзыва кода: {e}"

@tool
def get_aswak_stats(currency: str = "") -> str:
    """Статистика АСВАК — реестр кодов TRK и ACWAG, итоги по статусам и валютам.
    Используй когда спрашивают о кодах, АСВАК, сколько кодов выдано/свободно."""
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("SELECT code_type, status, currency, COUNT(*), SUM(freight_cost) FROM aswak_codes GROUP BY code_type, status, currency ORDER BY code_type, status")
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM aswak_codes")
        total = cur.fetchone()[0]
        cur.close(); db.close()
        if not rows:
            return "📋 АСВАК: записей нет. Добавьте первый код командой 'добавить код TRK'."
        result = f"📋 АСВАК — реестр кодов ТЛЦТ (всего: {total})\n\n"
        cur_type = None
        for code_type, status, curr, cnt, total_freight in rows:
            if code_type != cur_type:
                result += f"**{code_type}:**\n"; cur_type = code_type
            fr = f" | Фрахт: {total_freight:,.0f} {curr}" if total_freight else ""
            result += f"  {status}: {cnt}{fr}\n"
        return result
    except Exception as e:
        return f"Ошибка АСВАК: {e}"

# ─────────────────────────────────────────────
# 2. Аппарель — реестр вагонов по паромам
# ─────────────────────────────────────────────

@tool
def add_apparel_wagon(ferry_date: str, code: str, company: str,
                      station_from: str, station_to: str,
                      wagon_number: str, is_loaded: bool = True,
                      cargo_type: str = "", bill_number: str = "",
                      forwarder: str = "", payment_status: str = "Не оплачено",
                      currency: str = "USD") -> str:
    """Добавить вагон в реестр Аппарели (паром Туркменбаши).
    ferry_date: дата парома (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД).
    is_loaded: True=гружёный, False=порожний.
    payment_status: 'Оплачено' / 'Не оплачено' / 'Частично'.
    Используй когда добавляют вагон на паром, Аппарель Форма 4А."""
    try:
        # нормализуем дату
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try: fd = datetime.strptime(ferry_date.strip(), fmt).date(); break
            except: fd = None
        if not fd:
            return f"❌ Неверный формат даты: {ferry_date}. Используй ДД.ММ.ГГГГ"
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO apparel_wagons
              (ferry_date, code, company, station_from, station_to,
               wagon_number, is_loaded, cargo_type, bill_number,
               forwarder, payment_status, currency, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            RETURNING id
        """, (fd, code, company, station_from, station_to,
                wagon_number, is_loaded, cargo_type or None,
                bill_number or None, forwarder or None,
                payment_status, currency.upper()))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        loaded_str = "Гружёный" if is_loaded else "Порожний"
        return (f"✅ Вагон добавлен в Аппарель\n"
                f"  Паром: {fd.strftime('%d.%m.%Y')}\n"
                f"  Код: {code} | Компания: {company}\n"
                f"  Маршрут: {station_from} → {station_to}\n"
                f"  Вагон №{wagon_number} | {loaded_str}\n"
                f"  Оплата: {payment_status} ({currency})\n"
                f"  ID: {rec_id}")
    except Exception as e:
        return f"Ошибка добавления вагона: {e}"

@tool
def get_apparel_list(ferry_date: str = "", company: str = "") -> str:
    """Список вагонов Аппарели по дате парома или компании (Форма 4А).
    Используй когда просят показать аппарель, список паромных вагонов, Форма 4А."""
    try:
        db = _conn(); cur = db.cursor()
        conditions = []; params = []
        if ferry_date:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                try: fd = datetime.strptime(ferry_date.strip(), fmt).date(); break
                except: fd = None
            if fd:
                conditions.append("ferry_date = %s"); params.append(fd)
        if company:
            conditions.append("LOWER(company) LIKE LOWER(%s)"); params.append(f"%{company}%")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cur.execute(f"""
            SELECT ferry_date, code, company, station_from, station_to,
                   wagon_number, is_loaded, cargo_type, bill_number,
                   forwarder, payment_status, currency
            FROM apparel_wagons {where}
            ORDER BY ferry_date DESC, id DESC LIMIT 50
        """, params)
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM apparel_wagons {where}", params)
        total = cur.fetchone()[0]
        cur.close(); db.close()
        if not rows:
            return "📋 Аппарель: записей не найдено."
        result = f"🚢 Аппарель ТЛЦТ — {total} вагонов\n\n"
        for r in rows:
            loaded = "Груж" if r[6] else "Пор"
            result += (f"{r[0].strftime('%d.%m.%Y') if r[0] else '?'} | {r[2][:30]} | №{r[5]} | {loaded}\n"
                       f"  {r[3]} → {r[4]} | {r[10]} {r[11]}\n")
            if r[7]: result += f"  Груз: {r[7]}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка Аппарели: {e}"

# ─────────────────────────────────────────────
# 3. Расчёт комиссий (письмо №ТЛЦТ/1-137 от 31.01.2023)
# ─────────────────────────────────────────────

@tool
def calculate_commission(direction: str, currency: str, tariff: float = 0,
                          wagons: int = 1, tons: float = 0,
                          cargo_type: str = "general") -> str:
    """Рассчитать комиссию ТЛЦТ по тарифной сетке (письмо №ТЛЦТ/1-137 от 31.01.2023).
    direction: 'транзит', 'импорт', 'экспорт', 'порожний' (возврат порожних).
    currency: 'USD' или 'TMT'.
    tariff: тариф в указанной валюте (для % расчётов).
    wagons: количество вагонов.
    tons: тоннаж (для TMT сборных).
    cargo_type: 'general', 'oil' (нефтепродукты), 'gas' (сжиженный газ), 'sps' (СПС), 'mps' (МПС).
    Используй когда просят рассчитать комиссию, вознаграждение ТЛЦТ по ЖД."""
    d = direction.lower().strip()
    c = currency.upper().strip()

    lines = [f"📐 Расчёт комиссии ТЛЦТ (письмо №ТЛЦТ/1-137 от 31.01.2023)\n"]

    if c == "USD":
        if d in ("транзит", "импорт", "transit", "import"):
            rate = 0.0058
            commission = tariff * rate * wagons
            lines.append(f"  Тип: {direction.capitalize()} USD")
            lines.append(f"  Формула: тариф × 0.58% × {wagons} вагон(ов)")
            lines.append(f"  Тариф: {tariff:,.2f} USD")
            lines.append(f"  Комиссия: **{commission:,.2f} USD**")
        elif d in ("экспорт", "export"):
            rate = 41.0
            commission = rate * wagons
            lines.append(f"  Тип: Экспорт USD")
            lines.append(f"  Формула: 41 USD × {wagons} вагон(ов)")
            lines.append(f"  Комиссия: **{commission:,.2f} USD**")
        elif d in ("порожний", "порожние", "empty"):
            rate = 15.88
            commission = rate * wagons
            lines.append(f"  Тип: Возврат порожних USD")
            lines.append(f"  Формула: 15.88 USD × {wagons} вагон(ов)")
            lines.append(f"  Комиссия: **{commission:,.2f} USD**")
        else:
            return f"❌ Неизвестное направление '{direction}' для USD. Варианты: транзит, импорт, экспорт, порожний."

    elif c == "TMT":
        if d in ("импорт", "import"):
            commission = tariff * 0.10 * wagons
            lines.append(f"  Тип: Импорт TMT")
            lines.append(f"  Формула: тариф × 10% × {wagons} вагон(ов)")
            lines.append(f"  Тариф: {tariff:,.2f} TMT")
            lines.append(f"  Комиссия: **{commission:,.2f} TMT**")
        elif d in ("экспорт", "export"):
            ct = cargo_type.lower()
            if ct in ("oil", "нефть", "нефтепродукты"):
                rate = 20.0; label = "Нефтепродукты (СПС/МПС)"
            elif ct in ("gas", "газ", "сжиженный"):
                rate = 30.0; label = "Сжиженный газ (СПС/МПС)"
            elif ct in ("mps", "мпс"):
                rate = 20.0; label = "Сборные МПС"
            else:
                rate = 10.0; label = "Сборные СПС (общий)"
            commission = rate * tons
            lines.append(f"  Тип: Экспорт TMT — {label}")
            lines.append(f"  Формула: {rate} TMT × {tons} тонн")
            lines.append(f"  Комиссия: **{commission:,.2f} TMT**")
        elif d in ("порожний", "порожние", "empty"):
            rate = 55.58
            commission = rate * wagons
            lines.append(f"  Тип: Возврат порожних TMT")
            lines.append(f"  Формула: 55.58 TMT × {wagons} вагон(ов)")
            lines.append(f"  Комиссия: **{commission:,.2f} TMT**")
        else:
            return f"❌ Неизвестное направление '{direction}' для TMT. Варианты: импорт, экспорт, порожний."
    else:
        return f"❌ Валюта должна быть USD или TMT, получено: {currency}"

    return "\n".join(lines)

# ─────────────────────────────────────────────
# 4. Дебиторка ЖД (статусы 1-5, риск-алерты)
# ─────────────────────────────────────────────

@tool
def get_railway_receivables(status_filter: int = 0) -> str:
    """Дебиторка ЖД отдела — статусы 1-5, риск-алерты.
    status_filter: 0=все, 1-5=конкретный статус.
    Статусы: 1-Заявка, 2-В работе, 3-Акт не подписан, 4-Не оплачено, 5-Закрыто.
    Риск-алерт: сумма > 100 000 TMT + статус 4, или дней без движения > 30 + статус 4.
    Используй когда спрашивают о ЖД дебиторке, статусах, просрочках."""
    try:
        db = _conn(); cur = db.cursor()
        where = "WHERE dept = 'RAILWAY'"
        params = []
        if status_filter and 1 <= status_filter <= 5:
            where += " AND status = %s"; params.append(status_filter)
        cur.execute(f"""
            SELECT company, amount, currency, status, days_pending,
                   CASE WHEN (amount > 100000 AND currency='TMT' AND status=4) THEN '🚨РИСК'
                        WHEN (days_pending > 30 AND status=4) THEN '⚠️ПРОСРОЧКА'
                        ELSE '' END as alert
            FROM railway_receivables {where}
            ORDER BY status DESC, amount DESC LIMIT 50
        """, params)
        rows = cur.fetchall()
        cur.execute(f"""
            SELECT status, COUNT(*), SUM(CASE WHEN currency='TMT' THEN amount ELSE 0 END),
                   SUM(CASE WHEN currency='USD' THEN amount ELSE 0 END)
            FROM railway_receivables {where}
            GROUP BY status ORDER BY status
        """, params)
        stats = cur.fetchall()
        cur.close(); db.close()
        STATUS_LABELS = {1:'Заявка', 2:'В работе', 3:'Акт не подписан', 4:'Не оплачено', 5:'Закрыто'}
        if not rows:
            return "📋 Дебиторка ЖД: записей нет. Добавьте первую запись."
        result = "🚂 Дебиторка ЖД ТЛЦТ\n\n"
        result += "По статусам:\n"
        for st, cnt, tmt, usd in stats:
            label = STATUS_LABELS.get(st, str(st))
            result += f"  {st}-{label}: {cnt} | TMT: {tmt:,.0f} | USD: {usd:,.2f}\n"
        result += "\nДетали:\n"
        for company, amount, curr, status, days, alert in rows:
            label = STATUS_LABELS.get(status, str(status))
            result += f"{alert} {company[:40]}\n"
            result += f"  Сумма: **{amount:,.2f} {curr}** | Статус: {status}-{label} | Дней: {days}\n\n"
        return result
    except Exception as e:
        return f"Ошибка дебиторки ЖД: {e}"

@tool
def update_railway_receivable_status(company: str, new_status: int, notes: str = "") -> str:
    """Обновить статус дебиторки ЖД по компании.
    new_status: 1=Заявка, 2=В работе, 3=Акт не подписан, 4=Не оплачено, 5=Закрыто.
    Используй когда просят изменить, обновить статус должника ЖД."""
    if not 1 <= new_status <= 5:
        return "❌ Статус должен быть от 1 до 5"
    STATUS_LABELS = {1:'Заявка', 2:'В работе', 3:'Акт не подписан', 4:'Не оплачено', 5:'Закрыто'}
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            UPDATE railway_receivables
            SET status=%s, days_pending=0, notes=%s, updated_at=now()
            WHERE LOWER(company) LIKE LOWER(%s) AND dept='RAILWAY'
            RETURNING company, amount, currency
        """, (new_status, notes or None, f"%{company}%"))
        rows = cur.fetchall()
        db.commit(); cur.close(); db.close()
        if not rows:
            return f"❌ Компания '{company}' не найдена в ЖД дебиторке."
        result = f"✅ Статус обновлён → {new_status}-{STATUS_LABELS[new_status]}\n"
        for comp, amt, curr in rows:
            result += f"  {comp}: {amt:,.2f} {curr}\n"
        return result
    except Exception as e:
        return f"Ошибка обновления: {e}"

