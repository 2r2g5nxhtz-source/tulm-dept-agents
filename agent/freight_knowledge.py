"""
TULM Freight knowledge base — критичные требования по типам перевозок
+ справочник GNG/HS-кодов (12708 кодов из UIC NHM 2026).
"""
import os
import psycopg2
import psycopg2.extras
from langchain_core.tools import tool


def _conn():
    """Подключение к БД с GNG-кодами (общий tulm_db, через CRM_DB_URL)."""
    return psycopg2.connect(os.getenv('CRM_DB_URL') or os.getenv('PG_CONNECTION_STRING'))


# Критичные требования по типам перевозок (ТЛЦТ практика)
_REQUIREMENTS = {
    "rail": {
        "description": "Железнодорожная перевозка (колея 1520, ОСЖД)",
        "critical_fields": [
            "GNG-код груза (или ЕТСНГ) — для расчёта тарифа и СМГС-накладной",
            "Тип подвижного состава: полувагон / крытый / цистерна / фитинговая платформа / 40HC/20DC контейнер",
            "СПС или МПС: контейнеры/вагоны клиента (SOC=собственные, COC=железной дороги/оператора)",
            "Кол-во единиц + вес нетто на вагон/контейнер",
            "Станция отправления и назначения (желательно с кодами ЕСР)",
            "Погранпереходы (Сарахс/Этрек/Хоргос/Алтынколь — это РАЗНЫЕ станции!)",
            "Даты: готовность груза + дата подачи порожних под погрузку (разные, минимум 5-7 дней!)",
            "Плательщики по плечам (ТМ/УЗ/КЗ/РФ/КНР — кто платит и в какой валюте)",
            "Получатель на станции назначения (без него вагон не выгрузят)",
        ],
        "warnings": [
            "Опасный груз — нужен класс по РИД (правила перевозки опасных грузов по ЖД ОСЖД)",
            "Хоргос ≠ Алтынколь (в Китай через Алтынколь!) — уточняй конечную станцию КНР",
            "ТМ-плечо требует договор с «Туркмендемирёллары»",
            "Транзитная декларация для каждого государства отдельно",
            "Документ на ЖД = СМГС-накладная (НЕ CMR, CMR это для авто)",
        ],
    },
    "auto": {
        "description": "Автомобильная перевозка",
        "critical_fields": [
            "Объём груза (м³) — для подбора типа машины (тент 86 м³ / 96 м³ / 120 м³)",
            "Точная масса груза (тонн)",
            "Габариты крупных мест (если есть негабарит)",
        ],
        "warnings": [
            "Нагрузка на ось — груз >23т на ось делает перевозку тяжеловесной (другой тариф, разрешение Минтранс)",
            "Негабарит (>2.55м ширина / >4.0м высота / >20м длина) — нужно специальное разрешение и сопровождение",
            "Опасный груз — класс ADR (1-9), специальная машина с допуском",
            "Температурный режим — рефрижератор",
        ],
    },
    "sea": {
        "description": "Морская перевозка (паром Каспий)",
        "critical_fields": [
            "Тип контейнера (20DC / 40HC / 40REF / OOG out-of-gauge) или конвенциональный груз",
            "Вес брутто на единицу/контейнер",
            "Порт отправления и назначения (Туркменбаши / Баку / Актау)",
        ],
        "warnings": [
            "Опасный груз — класс IMDG (Морской кодекс)",
            "Рефрижераторный груз — нужна температурная карта",
            "Негабарит OOG — сюрчардж + сопровождение",
        ],
    },
    "air": {
        "description": "Авиаперевозка",
        "critical_fields": [
            "Упаковочный лист (packing list) — ОБЯЗАТЕЛЬНО для расчёта",
            "Вес брутто и объёмный вес (рассчитывается как ДxШxВ см / 6000)",
            "Размеры мест (см) и количество мест",
        ],
        "warnings": [
            "Опасный груз — класс ИАТА DGR (Dangerous Goods Regulations)",
            "Литий-ионные батареи — отдельные правила (UN3480/UN3481)",
            "Авиаспецифика: тарифы рассчитываются по бо́льшему из веса/объёмного веса",
        ],
    },
    "multimodal": {
        "description": "Мультимодальная (несколько видов транспорта)",
        "critical_fields": [
            "Описание плеч: где какой транспорт (например: авто Стамбул→Поти, паром Поти→Туркменбаши, авто Туркменбаши→Ашхабад)",
            "Точки перевалки",
            "Требования к каждому плечу (см. требования соответствующего транспорта)",
        ],
        "warnings": [
            "Каждое плечо требует своих документов и тарифов",
            "Простой при перевалке учитывается отдельно",
        ],
    },
}


@tool
def search_gng_code(cargo_description: str) -> str:
    """Поиск GNG/HS-кода для груза по описанию.
    GNG (Гармонизированная номенклатура грузов) — обязателен для оформления СМГС-накладной
    при ЖД перевозках через ОСЖД (Туркменистан, СНГ, Иран, Китай).

    cargo_description: описание груза на английском или русском
    (например 'steel pipes', 'трубы стальные', 'нефтяной кокс', 'petroleum coke')

    Возвращает 3 наиболее подходящих кода для подтверждения клиентом."""
    if not cargo_description.strip():
        return "❌ Опишите груз."
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Trigram similarity на EN+RU описании
        cur.execute("""
            SELECT code, level, description_en, description_ru,
                   GREATEST(
                       similarity(description_en, %s),
                       COALESCE(similarity(description_ru, %s), 0)
                   ) AS sim
            FROM gng_codes
            WHERE level >= 4    -- только конкретные коды, не группы
              AND (description_en %% %s OR description_ru %% %s)
            ORDER BY sim DESC
            LIMIT 5
        """, (cargo_description, cargo_description, cargo_description, cargo_description))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return (f"⚠️ По описанию '{cargo_description}' код GNG не найден.\n"
                    f"Запроси у клиента точный код от его поставщика, либо "
                    f"диспетчер уточнит при оформлении СМГС-накладной.")
        lines = [f"🔍 Возможные коды GNG для '{cargo_description}':\n"]
        for r in rows:
            ru = r['description_ru'] or ''
            ru_part = f" / {ru}" if ru else ""
            lines.append(f"• `{r['code']}` — {r['description_en']}{ru_part}")
        lines.append(f"\nПопроси клиента ПОДТВЕРДИТЬ один из кодов или указать свой.")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка поиска GNG: {e}"


@tool
def validate_gng_code(code: str) -> str:
    """Проверить существует ли указанный клиентом GNG-код в справочнике.
    code: 4-10 цифр (с пробелами или без)"""
    code_clean = ''.join(c for c in code if c.isdigit())
    if len(code_clean) < 4:
        return f"❌ Код должен быть минимум 4 цифры. Получил: '{code}'"
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Точное совпадение или префикс
        cur.execute("""
            SELECT code, description_en, description_ru
            FROM gng_codes
            WHERE code = %s OR code LIKE %s
            ORDER BY LENGTH(code)
            LIMIT 3
        """, (code_clean, code_clean + '%'))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            # Проверим — может это вообще валидный код но из другого справочника
            return (f"⚠️ Код {code_clean} не найден в справочнике GNG/HS.\n"
                    f"Возможные причины: опечатка, или это код ТН ВЭД/ЕТСНГ (не GNG).\n"
                    f"Уточни у клиента источник кода.")
        lines = [f"✅ Код найден:"]
        for r in rows:
            ru = f" / {r['description_ru']}" if r['description_ru'] else ""
            lines.append(f"• `{r['code']}` — {r['description_en']}{ru}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка проверки: {e}"


@tool
def get_freight_requirements(mode: str) -> str:
    """Получить требования и нюансы по типу перевозки.
    Используй ПЕРЕД сохранением заявки чтобы понять какие критичные поля
    нужно уточнить у клиента (GNG-код для ЖД, объём для авто, упаковочный для авиа и т.д.).

    mode: rail / auto / sea / air / multimodal"""
    m = mode.strip().lower()
    if m not in _REQUIREMENTS:
        return (f"⚠️ Неизвестный тип '{mode}'. Доступны: rail, auto, sea, air, multimodal.\n"
                f"Если клиент не указал тип — спроси какой подходит, или сохрани с mode='unknown'.")
    r = _REQUIREMENTS[m]
    parts = [f"📋 *{r['description']}*\n"]
    parts.append("**Критично для расчёта:**")
    for f in r["critical_fields"]:
        parts.append(f"• {f}")
    if r.get("warnings"):
        parts.append("\n**Особенности (предупреди клиента):**")
        for w in r["warnings"]:
            parts.append(f"⚠️ {w}")
    return "\n".join(parts)
