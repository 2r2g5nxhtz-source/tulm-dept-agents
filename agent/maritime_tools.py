import psycopg2
import os
from langchain_core.tools import tool
from datetime import datetime, date

def _conn():
    return psycopg2.connect(os.getenv('PG_CONNECTION_STRING'))

# ─────────────────────────────────────────────
# 1. ДЕБИТОРКА морского направления
# ─────────────────────────────────────────────

@tool
def get_maritime_receivables(status_filter: int = 0) -> str:
    """Дебиторка морского отдела ТЛЦТ — статусы 1-5, риск-алерты.
    status_filter: 0=все, 1-5=конкретный статус.
    Статусы: 1-Заявка, 2-В работе, 3-Акт не подписан, 4-Не оплачено, 5-Закрыто.
    Риск: сумма > 100000 TMT + статус 4, или дней без движения > 30 + статус 4."""
    STATUS = {1:'Заявка', 2:'В работе', 3:'Акт не подписан', 4:'Не оплачено', 5:'Закрыто'}
    try:
        db = _conn(); cur = db.cursor()
        where = "WHERE TRUE"
        params = []
        if status_filter and 1 <= status_filter <= 5:
            where += " AND status = %s"; params.append(status_filter)
        cur.execute(f"""
            SELECT client, amount, currency, status, days_inactive, description,
                   CASE WHEN (amount > 100000 AND currency='TMT' AND status=4) THEN '🚨РИСК'
                        WHEN (days_inactive > 30 AND status=4) THEN '⚠️ПРОСРОЧКА'
                        ELSE '' END as alert
            FROM maritime_receivables {where}
            ORDER BY status DESC, amount DESC LIMIT 50
        """, params)
        rows = cur.fetchall()
        cur.execute(f"""
            SELECT status, COUNT(*),
                   SUM(CASE WHEN currency='TMT' THEN amount ELSE 0 END),
                   SUM(CASE WHEN currency='USD' THEN amount ELSE 0 END)
            FROM maritime_receivables {where}
            GROUP BY status ORDER BY status
        """, params)
        stats = cur.fetchall()
        cur.close(); db.close()
        if not rows:
            return "📋 Дебиторка море: записей нет."
        result = "🚢 Дебиторка морского отдела ТЛЦТ\n\nПо статусам:\n"
        for st, cnt, tmt, usd in stats:
            result += f"  {st}-{STATUS.get(st,str(st))}: {cnt} | TMT: {tmt:,.0f} | USD: {usd:,.2f}\n"
        result += "\nДетали:\n"
        for client, amount, curr, status, days, desc, alert in rows:
            result += f"{alert} {client[:40]}\n"
            result += f"  Сумма: **{amount:,.2f} {curr}** | {status}-{STATUS.get(status,str(status))} | Дней: {days}\n"
            if desc:
                result += f"  {desc}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка дебиторки море: {e}"

@tool
def update_maritime_receivable_status(client: str, new_status: int, notes: str = "") -> str:
    """Обновить статус дебиторки морского отдела по клиенту.
    new_status: 1=Заявка, 2=В работе, 3=Акт не подписан, 4=Не оплачено, 5=Закрыто."""
    if not 1 <= new_status <= 5:
        return "❌ Статус от 1 до 5"
    STATUS = {1:'Заявка', 2:'В работе', 3:'Акт не подписан', 4:'Не оплачено', 5:'Закрыто'}
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            UPDATE maritime_receivables
            SET status=%s, days_inactive=0, description=%s, updated_at=now()
            WHERE LOWER(client) LIKE LOWER(%s)
            RETURNING client, amount, currency
        """, (new_status, notes or None, f"%{client}%"))
        rows = cur.fetchall()
        db.commit(); cur.close(); db.close()
        if not rows:
            return f"❌ Клиент '{client}' не найден."
        result = f"✅ Статус → {new_status}-{STATUS[new_status]}\n"
        for c, a, curr in rows:
            result += f"  {c}: {a:,.2f} {curr}\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"

@tool
def add_maritime_receivable(client: str, amount: float, currency: str,
                             description: str = "") -> str:
    """Добавить запись в дебиторку морского отдела (статус 1-Заявка по умолчанию).
    currency: TMT или USD."""
    if currency.upper() not in ('TMT', 'USD'):
        return "❌ Валюта: TMT или USD"
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO maritime_receivables (client, amount, currency, status, days_inactive, description)
            VALUES (%s, %s, %s, 1, 0, %s) RETURNING id
        """, (client, amount, currency.upper(), description or None))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        return f"✅ Дебиторка добавлена (ID: {rec_id})\n  {client}: {amount:,.2f} {currency.upper()}\n  Статус: 1-Заявка"
    except Exception as e:
        return f"Ошибка: {e}"

# ─────────────────────────────────────────────
# 2. БАЛКАНСКИЙ ФИЛИАЛ
# ─────────────────────────────────────────────

@tool
def add_balkansk_operation(op_date: str, ferry_name: str, wagon_or_container: str,
                            client: str, expeditor: str = "", amount: float = 0,
                            currency: str = "USD", notes: str = "") -> str:
    """Добавить операцию Балканского филиала ТЛЦТ.
    op_date: дата операции (ДД.ММ.ГГГГ).
    ferry_name: название парома/судна.
    wagon_or_container: номер вагона или контейнера.
    Статус по умолчанию: офлайн (требует синхронизации)."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try: fd = datetime.strptime(op_date.strip(), fmt).date(); break
        except: fd = None
    if not fd:
        return f"❌ Неверный формат даты: {op_date}"
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO balkansk_operations
              (op_date, ferry_name, wagon_or_container, client, expeditor,
               amount, currency, status, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'офлайн',%s) RETURNING id
        """, (fd, ferry_name, wagon_or_container, client, expeditor or None,
              amount or 0, currency.upper(), notes or None))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        return (f"✅ Операция Балкан добавлена (ID: {rec_id})\n"
                f"  {fd.strftime('%d.%m.%Y')} | {ferry_name}\n"
                f"  {wagon_or_container} | {client}\n"
                f"  Сумма: {amount:,.2f} {currency.upper()} | Статус: офлайн")
    except Exception as e:
        return f"Ошибка Балкан: {e}"

@tool
def sync_balkansk_operations() -> str:
    """Синхронизировать офлайн-операции Балканского филиала (перевести статус офлайн → синхронизирован).
    Используй когда филиал передаёт данные для синхронизации."""
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            UPDATE balkansk_operations SET status='синхронизирован'
            WHERE status='офлайн'
            RETURNING id, ferry_name, client
        """)
        rows = cur.fetchall()
        db.commit(); cur.close(); db.close()
        if not rows:
            return "📋 Балкан: офлайн-операций для синхронизации нет."
        result = f"✅ Синхронизировано {len(rows)} операций:\n"
        for rid, ferry, client in rows:
            result += f"  ID {rid}: {ferry} | {client}\n"
        return result
    except Exception as e:
        return f"Ошибка синхронизации: {e}"

@tool
def get_balkansk_list(status_filter: str = "") -> str:
    """Список операций Балканского филиала.
    status_filter: 'офлайн', 'синхронизирован', 'счёт выставлен', или пусто=все."""
    try:
        db = _conn(); cur = db.cursor()
        where = "WHERE TRUE"; params = []
        if status_filter:
            where += " AND status = %s"; params.append(status_filter)
        cur.execute(f"""
            SELECT op_date, ferry_name, wagon_or_container, client,
                   amount, currency, status, notes
            FROM balkansk_operations {where}
            ORDER BY op_date DESC LIMIT 50
        """, params)
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*), SUM(amount) FROM balkansk_operations {where}", params)
        total, total_amt = cur.fetchone()
        cur.close(); db.close()
        if not rows:
            return "📋 Балканский филиал: записей нет."
        result = f"🏭 Балканский филиал — {total} операций | {total_amt:,.2f}\n\n"
        for d, ferry, wagon, client, amt, curr, status, notes in rows:
            result += f"{d.strftime('%d.%m.%Y') if d else '?'} | {ferry} | {wagon}\n"
            result += f"  {client[:35]} | {amt:,.2f} {curr} | {status}\n"
            if notes:
                result += f"  {notes}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка Балкан: {e}"

# ─────────────────────────────────────────────
# 3. КОНТЕЙНЕРЫ
# ─────────────────────────────────────────────

@tool
def add_container(container_number: str, container_type: str, client: str,
                  location: str = "на складе", cargo_type: str = "",
                  notes: str = "") -> str:
    """Добавить контейнер в реестр ТЛЦТ.
    container_type: 20, 40, 45, HC, tank.
    location: на складе / в пути / у клиента / на таможне."""
    VALID_TYPES = {'20', '40', '45', 'HC', 'tank'}
    if container_type not in VALID_TYPES:
        return f"❌ Тип контейнера: {', '.join(VALID_TYPES)}"
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO containers (container_number, type, client, location,
                                    status, cargo_type, entry_date, notes)
            VALUES (%s,%s,%s,%s,'на складе',%s,now(),%s) RETURNING id
        """, (container_number.upper().strip(), container_type, client,
              location, cargo_type or None, notes or None))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        return (f"✅ Контейнер добавлен (ID: {rec_id})\n"
                f"  №{container_number.upper()} | {container_type}\n"
                f"  Клиент: {client} | Локация: {location}")
    except Exception as e:
        return f"Ошибка контейнера: {e}"

@tool
def update_container_status(container_number: str, new_status: str,
                             new_location: str = "") -> str:
    """Обновить статус/локацию контейнера.
    new_status: на складе / в пути / у клиента / на таможне."""
    try:
        db = _conn(); cur = db.cursor()
        updates = ["status=%s", "updated_at=now()"]
        params = [new_status]
        if new_location:
            updates.append("location=%s"); params.append(new_location)
        if new_status in ('у клиента', 'вышел'):
            updates.append("exit_date=now()")
        params.append(container_number.upper().strip())
        cur.execute(f"""
            UPDATE containers SET {', '.join(updates)}
            WHERE container_number=%s RETURNING container_number, client
        """, params)
        row = cur.fetchone()
        db.commit(); cur.close(); db.close()
        if not row:
            return f"❌ Контейнер {container_number.upper()} не найден."
        return f"✅ Контейнер {row[0]} → {new_status}\n  Клиент: {row[1]}"
    except Exception as e:
        return f"Ошибка: {e}"

@tool
def get_container_list(status_filter: str = "", client_filter: str = "") -> str:
    """Список контейнеров ТЛЦТ с фильтром по статусу или клиенту."""
    try:
        db = _conn(); cur = db.cursor()
        conditions = []; params = []
        if status_filter:
            conditions.append("status = %s"); params.append(status_filter)
        if client_filter:
            conditions.append("LOWER(client) LIKE LOWER(%s)"); params.append(f"%{client_filter}%")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cur.execute(f"""
            SELECT container_number, type, client, location, status,
                   entry_date,
                   EXTRACT(DAY FROM now() - entry_date)::int as days_stored,
                   cargo_type, notes
            FROM containers {where}
            ORDER BY entry_date DESC LIMIT 50
        """, params)
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM containers {where}", params)
        total = cur.fetchone()[0]
        cur.close(); db.close()
        if not rows:
            return "📦 Контейнеры: не найдено."
        result = f"📦 Контейнеры ТЛЦТ — {total} шт.\n\n"
        for num, ctype, client, loc, status, entry, days, cargo, notes in rows:
            storage_warn = " ⚠️" if days and days > 30 else ""
            result += f"№{num} [{ctype}] — {status}{storage_warn}\n"
            result += f"  {client[:35]} | {loc} | {days or 0} дней\n"
            if cargo:
                result += f"  Груз: {cargo}\n"
            result += "\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"

@tool
def get_container_stats() -> str:
    """Статистика контейнерного парка ТЛЦТ — по типам, статусам, просрочкам хранения."""
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("SELECT type, status, COUNT(*) FROM containers GROUP BY type, status ORDER BY type, status")
        rows = cur.fetchall()
        cur.execute("""
            SELECT COUNT(*), type FROM containers
            WHERE EXTRACT(DAY FROM now() - entry_date) > 30 AND status != 'у клиента'
            GROUP BY type
        """)
        overdue = cur.fetchall()
        cur.close(); db.close()
        result = "📦 Статистика контейнеров ТЛЦТ\n\n"
        cur_type = None
        for ctype, status, cnt in rows:
            if ctype != cur_type:
                result += f"**{ctype}ft:**\n"; cur_type = ctype
            result += f"  {status}: {cnt}\n"
        if overdue:
            result += "\n⚠️ Просрочка хранения (>30 дней):\n"
            for cnt, ctype in overdue:
                result += f"  {ctype}ft: {cnt} шт.\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"

# ─────────────────────────────────────────────
# 4. РАСЧЁТ УСЛУГ ПОРТА (Нырхнама №1-2024)
# ─────────────────────────────────────────────

@tool
def calculate_port_service(service_type: str, cargo_category: str,
                            quantity: float, is_loaded: bool = True,
                            trade_direction: str = "транзит",
                            client_type: str = "нерезидент",
                            volume_tons: float = 0) -> str:
    """Рассчитать стоимость услуг порта Туркменбаши (Нырхнама №1-2024).
    
    service_type: 'погрузка' / 'аппарель' / 'авто'
    cargo_category: 'общие' / 'металл_мелкий' / 'металл_крупный' / 'лес' / 'зерно' /
                    'импорт_мелкий' / 'импорт_крупный' / 'тяжелый_35_70' / 'тяжелый_71_130' / 'тяжелый_131+'
    quantity: тоннаж (для погрузки) или количество вагонов/авто (для аппарели)
    is_loaded: True=гружёный, False=порожний (для аппарели/авто)
    trade_direction: 'транзит' / 'экспорт' / 'импорт'
    client_type: 'резидент' / 'нерезидент'
    volume_tons: объём в тоннах для расчёта скидки (0=без скидки)
    
    ВАЖНО: USD и TMT — отдельные тарифные сетки. Конвертация USD↔TMT не производится.
    """
    # Тарифная сетка погрузки/выгрузки (USD/т)
    CARGO_RATES = {
        'общие':        9.00,
        'металл_мелкий':12.00,
        'металл_крупный':10.00,
        'лес':          8.40,
        'зерно':        6.00,
        'импорт_мелкий':22.05,
        'импорт_крупный':18.45,
        'тяжелый_35_70':75.00,
        'тяжелый_71_130':100.00,
        'тяжелый_131+': 145.00,
    }
    # Аппарель (USD/единица)
    APPAREL_RATES = {
        'вагон': {True: 56.00, False: 36.00},
        'авто_малый': {True: 28.00, False: 18.00},
        'авто_большой': {True: 38.00, False: 28.00},
    }

    lines = [f"📐 Расчёт услуг порта Туркменбаши (Нырхнама №1-2024)\n"]
    lines.append(f"  Направление: {trade_direction} | Клиент: {client_type}")

    if service_type in ('аппарель', 'авто'):
        key = 'вагон' if service_type == 'аппарель' else ('авто_малый' if cargo_category == '<=16.5' else 'авто_большой')
        rate = APPAREL_RATES.get(key, APPAREL_RATES['вагон'])[is_loaded]
        base = rate * quantity
        loaded_str = "гружёный" if is_loaded else "порожний"
        lines.append(f"  Тип: {service_type.capitalize()} {loaded_str}")
        lines.append(f"  Тариф: {rate:.2f} USD × {quantity:.0f} = **{base:.2f} USD**")
    else:
        rate = CARGO_RATES.get(cargo_category)
        if not rate:
            avail = ', '.join(CARGO_RATES.keys())
            return f"❌ Категория груза не найдена. Доступные: {avail}"
        base = rate * quantity
        lines.append(f"  Категория: {cargo_category} | Тариф: {rate:.2f} USD/т")
        lines.append(f"  Тоннаж: {quantity:.2f} т → Базовая стоимость: **{base:.2f} USD**")

    # НДС и комиссия ТЛЦТ
    if trade_direction == 'транзит':
        commission = base * 0.05
        lines.append(f"\n  Комиссия ТЛЦТ (транзит): {base:.2f} × 5% = **{commission:.2f} USD**")
        lines.append(f"  Счёт клиенту: **{base:.2f} USD** (без НДС, транзит)")
    else:
        with_vat = base * 1.15
        commission = with_vat * 0.05
        lines.append(f"\n  НДС 15%: {base:.2f} × 1.15 = {with_vat:.2f} USD")
        lines.append(f"  Комиссия ТЛЦТ ({trade_direction}): {with_vat:.2f} × 5% = **{commission:.2f} USD**")
        lines.append(f"  Счёт клиенту: **{with_vat:.2f} USD**")

    # Скидки по объёму
    if volume_tons > 0 and trade_direction in ('экспорт', 'транзит'):
        if volume_tons <= 30000:
            disc = 0.20; disc_label = "10 000–30 000 т → 20%"
        elif volume_tons <= 50000:
            disc = 0.30; disc_label = "30 001–50 000 т → 30%"
        else:
            disc = 0.40; disc_label = "50 001+ т → 40%"
        discounted = base * (1 - disc)
        lines.append(f"\n  Скидка по объёму ({disc_label}): **{discounted:.2f} USD**")

    # Предупреждение о валюте
    if client_type == 'резидент':
        lines.append(f"\n  ⚠️ Клиент-резидент: счёт может выставляться в TMT.")
        lines.append(f"  USD↔TMT конвертация не производится. Уточните у менеджера.")

    return "\n".join(lines)

@tool
def calculate_storage_fee(cargo_type: str, days: int, quantity: float,
                           trade_direction: str = "транзит",
                           client_type: str = "нерезидент") -> str:
    """Рассчитать стоимость хранения на складе порта Туркменбаши.
    
    cargo_type: 'общий' / '20ft' / '40ft' / '45ft' / 'танк_гружёный' / 'вагон'
    days: количество дней хранения
    quantity: количество единиц (контейнеров, вагонов) или тонн для общего груза
    trade_direction: 'транзит' / 'экспорт' / 'импорт'
    
    Первые 30 дней — бесплатно (кроме танк-контейнеров и вагонов 4+ дней).
    ВАЖНО: Конвертация USD↔TMT не производится."""
    lines = [f"🏗️ Расчёт хранения порт Туркменбаши (Нырхнама №1-2024)\n"]
    lines.append(f"  Тип груза: {cargo_type} | Дней: {days} | Кол-во: {quantity}")

    RATES = {
        'общий':        {'free_days': 30, 'rate': 0.10, 'unit': 'USD/т/день'},
        '20ft':         {'free_days': 30, 'rate': 2.50, 'unit': 'USD/конт/день'},
        '40ft':         {'free_days': 30, 'rate': 4.00, 'unit': 'USD/конт/день'},
        '45ft':         {'free_days': 30, 'rate': 4.20, 'unit': 'USD/конт/день'},
        'танк_гружёный':{'free_days': 0,  'rate': 10.00,'unit': 'USD/конт/день'},
        'вагон':        {'free_days': 3,  'rate': 5.00, 'unit': 'USD/вагон/день'},
    }

    cfg = RATES.get(cargo_type)
    if not cfg:
        return f"❌ Тип груза не найден. Доступные: {', '.join(RATES.keys())}"

    free = cfg['free_days']
    billable_days = max(0, days - free)

    if billable_days == 0:
        lines.append(f"\n  ✅ Хранение БЕСПЛАТНО (не превышает {free} дней)")
        lines.append(f"  (тариф начисляется с {free+1}-го дня)")
        return "\n".join(lines)

    base = cfg['rate'] * billable_days * quantity
    lines.append(f"\n  Бесплатный период: {free} дней")
    lines.append(f"  Платных дней: {days} - {free} = {billable_days}")
    lines.append(f"  Тариф: {cfg['rate']} {cfg['unit']}")
    lines.append(f"  Расчёт: {cfg['rate']} × {billable_days} дн × {quantity} = **{base:.2f} USD**")

    if trade_direction == 'транзит':
        commission = base * 0.05
        lines.append(f"\n  Комиссия ТЛЦТ (транзит 5%): **{commission:.2f} USD**")
    else:
        with_vat = base * 1.15
        commission = with_vat * 0.05
        lines.append(f"\n  НДС 15%: {with_vat:.2f} USD")
        lines.append(f"  Комиссия ТЛЦТ ({trade_direction} 5%): **{commission:.2f} USD**")

    if client_type == 'резидент':
        lines.append(f"\n  ⚠️ Резидент: уточните у менеджера о выставлении в TMT.")

    return "\n".join(lines)

@tool
def calculate_container_handling(container_type: str, is_loaded: bool,
                                  quantity: int = 1,
                                  trade_direction: str = "транзит",
                                  client_type: str = "нерезидент") -> str:
    """Рассчитать погрузку/выгрузку контейнеров в порту Туркменбаши.
    container_type: 'стандарт' (20/40/45) или 'танк'.
    is_loaded: True=гружёный, False=порожний.
    ВАЖНО: USD↔TMT конвертация не производится."""
    RATES = {
        ('стандарт', True):  84.00,
        ('стандарт', False): 42.00,
        ('танк', True):     126.00,
        ('танк', False):     42.00,
    }
    rate = RATES.get((container_type, is_loaded))
    if not rate:
        return "❌ container_type: 'стандарт' или 'танк'. is_loaded: True/False"

    loaded_str = "гружёный" if is_loaded else "порожний"
    base = rate * quantity
    lines = [f"📦 Расчёт обработки контейнеров (Нырхнама №1-2024)\n"]
    lines.append(f"  {container_type.capitalize()} {loaded_str} × {quantity} шт")
    lines.append(f"  Тариф: {rate:.2f} USD × {quantity} = **{base:.2f} USD**")

    if trade_direction == 'транзит':
        commission = base * 0.05
        lines.append(f"\n  Комиссия ТЛЦТ (транзит 5%): **{commission:.2f} USD**")
        lines.append(f"  Счёт: **{base:.2f} USD**")
    else:
        with_vat = base * 1.15
        commission = with_vat * 0.05
        lines.append(f"\n  НДС 15%: {with_vat:.2f} USD")
        lines.append(f"  Комиссия ТЛЦТ ({trade_direction} 5%): **{commission:.2f} USD**")
        lines.append(f"  Счёт: **{with_vat:.2f} USD**")

    if client_type == 'резидент':
        lines.append(f"\n  ⚠️ Резидент: уточните у менеджера о выставлении в TMT.")

    return "\n".join(lines)

@tool
def calculate_bl_fee(document_type: str, container_count: int = 0) -> str:
    """Рассчитать стоимость подготовки коносаментов (BL) порт Туркменбаши.
    document_type: 'сухогруз' / 'танкер' / 'паром' / 'контейнер'
    container_count: количество контейнеров (только для типа 'контейнер')."""
    lines = ["📄 Расчёт коносаментов (Нырхнама №1-2024)\n"]
    if document_type in ('сухогруз', 'танкер'):
        lines.append(f"  Тип: {document_type.capitalize()}")
        lines.append(f"  Стоимость: **240.00 USD/комплект**")
    elif document_type == 'паром':
        lines.append(f"  Тип: Паром")
        lines.append(f"  Стоимость: **50.00 USD/комплект**")
    elif document_type == 'контейнер':
        if container_count <= 10:      fee = 20.00;  bracket = "1-10"
        elif container_count <= 20:    fee = 40.00;  bracket = "11-20"
        elif container_count <= 40:    fee = 80.00;  bracket = "21-40"
        elif container_count <= 60:    fee = 130.00; bracket = "41-60"
        else:                          fee = 200.00; bracket = "61+"
        lines.append(f"  Тип: Контейнеры ({container_count} шт, скобка {bracket})")
        lines.append(f"  Стоимость: **{fee:.2f} USD/комплект**")
    else:
        return "❌ Тип: 'сухогруз', 'танкер', 'паром', 'контейнер'"
    lines.append(f"\n  ⚠️ USD↔TMT конвертация не производится. Уточните у менеджера.")
    return "\n".join(lines)

# ─────────────────────────────────────────────
# 5. РЕЙСЫ И ОТЧЁТЫ
# ─────────────────────────────────────────────

@tool
def add_voyage(vessel_name: str, voyage_number: str,
               departure_port: str, arrival_port: str,
               departure_date: str, cargo_type: str,
               cargo_weight: float, client: str,
               revenue_usd: float = 0, revenue_tmt: float = 0) -> str:
    """Добавить рейс в реестр морских операций ТЛЦТ.
    departure_date: ДД.ММ.ГГГГ.
    revenue_usd и revenue_tmt — отдельные, не конвертируются."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try: dd = datetime.strptime(departure_date.strip(), fmt).date(); break
        except: dd = None
    if not dd:
        return f"❌ Неверный формат даты: {departure_date}"
    try:
        db = _conn(); cur = db.cursor()
        cur.execute("""
            INSERT INTO maritime_voyages
              (vessel_name, voyage_number, departure_port, arrival_port,
               departure_date, cargo_type, cargo_weight, client,
               revenue_usd, revenue_tmt, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'в пути') RETURNING id
        """, (vessel_name, voyage_number, departure_port, arrival_port,
              dd, cargo_type, cargo_weight, client, revenue_usd, revenue_tmt))
        rec_id = cur.fetchone()[0]
        db.commit(); cur.close(); db.close()
        return (f"✅ Рейс добавлен (ID: {rec_id})\n"
                f"  {vessel_name} | Рейс {voyage_number}\n"
                f"  {departure_port} → {arrival_port} | {dd.strftime('%d.%m.%Y')}\n"
                f"  Груз: {cargo_type} {cargo_weight:,.1f} т | {client}\n"
                f"  Выручка: {revenue_usd:,.2f} USD | {revenue_tmt:,.2f} TMT")
    except Exception as e:
        return f"Ошибка рейса: {e}"

@tool
def get_voyage_report(vessel_filter: str = "", status_filter: str = "") -> str:
    """Отчёт по рейсам морского отдела ТЛЦТ.
    vessel_filter: название судна (частичное совпадение).
    status_filter: 'в пути' / 'прибыл' / 'завершён'."""
    try:
        db = _conn(); cur = db.cursor()
        conditions = []; params = []
        if vessel_filter:
            conditions.append("LOWER(vessel_name) LIKE LOWER(%s)"); params.append(f"%{vessel_filter}%")
        if status_filter:
            conditions.append("status = %s"); params.append(status_filter)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cur.execute(f"""
            SELECT vessel_name, voyage_number, departure_port, arrival_port,
                   departure_date, cargo_type, cargo_weight, client,
                   revenue_usd, revenue_tmt, status
            FROM maritime_voyages {where}
            ORDER BY departure_date DESC LIMIT 30
        """, params)
        rows = cur.fetchall()
        cur.execute(f"""
            SELECT COUNT(*), SUM(revenue_usd), SUM(revenue_tmt)
            FROM maritime_voyages {where}
        """, params)
        total, tusd, ttmt = cur.fetchone()
        cur.close(); db.close()
        if not rows:
            return "📋 Рейсы: не найдено."
        result = f"⚓ Рейсы морского отдела — {total} шт\n"
        result += f"  Итого: {tusd or 0:,.2f} USD | {ttmt or 0:,.2f} TMT\n\n"
        for vessel, vnum, dep, arr, ddate, cargo, weight, client, rusd, rtmt, status in rows:
            result += f"🚢 {vessel} | Рейс {vnum} | {status}\n"
            result += f"  {dep} → {arr} | {ddate.strftime('%d.%m.%Y') if ddate else '?'}\n"
            result += f"  {cargo} {weight:,.1f}т | {client[:30]}\n"
            result += f"  USD: {rusd:,.2f} | TMT: {rtmt:,.2f}\n\n"
        return result
    except Exception as e:
        return f"Ошибка: {e}"

@tool
def get_maritime_summary() -> str:
    """Сводка по морскому отделу ТЛЦТ — дебиторка, контейнеры, рейсы, Балкан."""
    try:
        db = _conn(); cur = db.cursor()
        result = "🌊 Морской отдел ТЛЦТ — сводка\n\n"

        cur.execute("SELECT COUNT(*), SUM(CASE WHEN currency='TMT' THEN amount ELSE 0 END), SUM(CASE WHEN currency='USD' THEN amount ELSE 0 END) FROM maritime_receivables WHERE status != 5")
        cnt, tmt, usd = cur.fetchone()
        result += f"📊 Дебиторка (открытые): {cnt or 0} | TMT: {tmt or 0:,.0f} | USD: {usd or 0:,.2f}\n"

        cur.execute("SELECT COUNT(*) FROM maritime_receivables WHERE amount > 100000 AND currency='TMT' AND status=4")
        risk = cur.fetchone()[0]
        if risk:
            result += f"  🚨 Риск-алерты: {risk} клиентов\n"

        cur.execute("SELECT status, COUNT(*) FROM containers GROUP BY status")
        cont_rows = cur.fetchall()
        result += "\n📦 Контейнеры:\n"
        for status, cnt in cont_rows:
            result += f"  {status}: {cnt}\n"

        cur.execute("SELECT status, COUNT(*) FROM maritime_voyages GROUP BY status")
        voy_rows = cur.fetchall()
        if voy_rows:
            result += "\n⚓ Рейсы:\n"
            for status, cnt in voy_rows:
                result += f"  {status}: {cnt}\n"

        cur.execute("SELECT COUNT(*) FROM balkansk_operations WHERE status='офлайн'")
        offline = cur.fetchone()[0]
        if offline:
            result += f"\n🏭 Балкан офлайн (нужна синхр.): {offline}\n"

        cur.close(); db.close()
        return result
    except Exception as e:
        return f"Ошибка сводки: {e}"
