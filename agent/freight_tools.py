"""
Freight workflow tools для @tulm_freight_bot.
Адаптация прототипа CrewAI (см. ~/agents/tulm/experiments/) на наш LangGraph стек.
Используются ReAct агентом, тот же паттерн что у dept-ботов.
"""
from langchain_core.tools import tool


# Базовые маршруты ТЛЦТ — заглушки, в проде заменить на запросы к БД
_ROUTES = {
    ("туркменбаши", "баку", "sea"):       "✅ Прямой паром Туркменбаши→Баку. Транзит ~18 ч.",
    ("туркменбаши", "актау", "sea"):      "✅ Прямой паром Туркменбаши→Актау. Транзит ~12 ч.",
    ("ашхабад", "бухара", "rail"):        "✅ Ж/д Ашхабад→Бухара через Узбекистан. Транзит 2 суток.",
    ("туркменбаши", "поти", "multimodal"): "✅ Паром Каспий + ж/д Азербайджан→Грузия. Транзит 4-5 суток.",
    ("ашхабад", "стамбул", "multimodal"): "✅ ТМТМ коридор (Транскаспийский). Транзит 7-10 суток.",
    ("туркменбаши", "стамбул", "multimodal"): "✅ ТМТМ через Каспий+Кавказ. Транзит 7-10 суток.",
    ("сарахс", "иран", "rail"):           "✅ ЖД Сарахс (граница ACWAG). Транзит 1-2 суток.",
    ("этрек", "иран", "rail"):            "✅ ЖД Этрек (граница ACWAG). Транзит 1-2 суток.",
    ("ашхабад", "москва", "rail"):        "⚠️ Ж/д через Казахстан. Транзит 7-9 суток. Нужна сверка с диспетчером.",
}

# Базовые тарифы ТЛЦТ — в проде из БД tariffs
_RATES = {
    ("general", "sea"):        12.5,   # USD/тонна
    ("general", "rail"):       8.0,
    ("general", "multimodal"): 15.0,
    ("container", "sea"):      850.0,  # USD/TEU фикс
    ("container", "multimodal"): 1100.0,
    ("bulk", "sea"):           9.0,
    ("bulk", "rail"):          6.5,
    ("hazmat", "sea"):         22.0,
    ("hazmat", "rail"):        18.0,
    ("hazmat", "multimodal"):  25.0,
}

# Документы по странам назначения
_BASE_DOCS = ["Инвойс", "Упаковочный лист", "CMR/коносамент", "Сертификат происхождения"]
_COUNTRY_DOCS = {
    "азербайджан": ["Разрешение ГТК АЗ"],
    "казахстан":   ["Транзитная декларация ЕАЭС"],
    "узбекистан":  ["Транзитная декларация ЕАЭС"],
    "россия":      ["Транзитная декларация ЕАЭС"],
    "турция":      ["EUR.1 или A.TR сертификат"],
    "грузия":      ["DCFTA сертификат"],
    "иран":        ["Лицензия МИД ТМ", "Phytosanitary certificate"],
    "китай":       ["GB-стандарты соответствия", "GACC регистрация"],
    "афганистан":  ["Лицензия МИД ТМ"],
}


@tool
def check_route_feasibility(origin: str, destination: str, mode: str) -> str:
    """Проверить доступность маршрута через коридоры ТЛЦТ.
    origin/destination — города, mode — sea/rail/multimodal.
    Возвращает оценку транзита и доступность."""
    key = (origin.strip().lower(), destination.strip().lower(), mode.strip().lower())
    found = _ROUTES.get(key)
    if found:
        return found
    return (f"⚠️ Маршрут {origin}→{destination} ({mode}) — нет в базовом справочнике. "
            f"Требуется ручная проверка диспетчером ТЛЦТ.")


@tool
def estimate_cost(cargo_type: str, weight_ton: float, mode: str) -> str:
    """Предварительная оценка стоимости фрахта в USD.
    cargo_type: general / bulk / container / hazmat
    weight_ton: вес в тоннах (для контейнеров — общий вес груза)
    mode: sea / rail / multimodal
    Возвращает оценку с пометкой что финальная цена после диспетчера."""
    rate = _RATES.get((cargo_type.strip().lower(), mode.strip().lower()))
    if rate is None:
        return (f"⚠️ Тариф для {cargo_type} + {mode} нет в базовом справочнике. "
                f"Запросите диспетчера ТЛЦТ для расчёта.")

    if cargo_type.lower() == "container":
        teu = max(1, round(weight_ton / 20))
        cost = teu * rate
        note = f"~{teu} TEU × ${rate}/TEU"
    else:
        cost = weight_ton * rate
        note = f"{weight_ton} тонн × ${rate}/тонн"

    return (f"💰 Предварительная стоимость: **${cost:,.0f}** USD ({note}). "
            f"Финальная цена — после подтверждения диспетчером.")


@tool
def check_required_docs(cargo_type: str, destination_country: str) -> str:
    """Список обязательных документов для таможенного оформления.
    cargo_type: general / bulk / container / hazmat
    destination_country: страна назначения (азербайджан, турция, иран и т.д.)"""
    docs = list(_BASE_DOCS)
    extra = _COUNTRY_DOCS.get(destination_country.strip().lower(), [])
    docs.extend(extra)
    if cargo_type.strip().lower() == "hazmat":
        docs.extend(["MSDS (паспорт безопасности)", "Разрешение на перевозку ОГ (опасный груз)"])
    return "📋 **Документы:** " + ", ".join(docs)
