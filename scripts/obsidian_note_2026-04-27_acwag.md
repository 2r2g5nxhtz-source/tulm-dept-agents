# ACWAG — Загрузка в railway_db + инструменты агента
**Дата:** 2026-04-27
**Теги:** #tulm #railway #acwag #bot #deploy
**Статус:** ✅ Готово — ждёт деплоя на Hetzner

---

## Что сделано

### Файл ACWAG.xlsx — проанализирован
- 6 листов: 2021–2026
- Структура: № | wagty (дата) | Kompaniya | sany (кол-во вагонов) | kod (ACWAG код) | styk (стык) | Baha (тариф USD/вагон)
- Стыки: Sarahs (Сарахс) / Akyayla (Акяйла)
- **~1,679 партий / ~19,600 вагонов за 6 лет**

### История тарифа Baha
| Год  | Тариф          |
|------|----------------|
| 2021 | 322 USD/вагон  |
| 2022 | 318 USD/вагон  |
| 2023 | 333 USD/вагон  |
| 2024 | 342 USD/вагон  |
| 2025 | 342 USD/вагон  |
| 2026 | 342 USD/вагон  |

---

## Новые файлы в репо tulm-dept-agents

| Файл | Назначение |
|------|------------|
| `agent/acwag_tool.py` | 3 инструмента для railway-bot |
| `scripts/load_acwag.py` | Загрузка xlsx → railbot_db |
| `scripts/deploy_railway.sh` | Деплой на Hetzner |
| `.env.railway` | Конфиг railway-bot |
| `agent/agent_factory.py` | Обновлён: _DEPT_TOOLS routing |

### Инструменты агента (acwag_tool.py)
- `get_acwag_stats()` — статистика по годам, тарифы, стыки
- `search_acwag_by_company(query)` — история компании по всем годам
- `search_acwag_filtered(year, styk, company)` — перекрёстный фильтр

### Схема таблицы railbot_db.acwag_records
```sql
year, num, wagon_date, company, wagon_count, acwag_code, styk, baha
```

---

## Деплой на Hetzner (TODO)

```bash
# 1. Скопировать ACWAG.xlsx на сервер (с Mac)
scp ACWAG.xlsx root@HETZNER_IP:~/tulm-dept-agents/

# 2. На сервере
cd ~/tulm-dept-agents
git pull origin main
bash scripts/deploy_railway.sh
```

⚠️ Перед деплоем: вставить реальный TELEGRAM_TOKEN в `.env.railway`

---

## Ответы на вопросы сессии

### Помнит ли Claude чат-проект "Tulum"?
**НЕТ.** Claude (обычный чат и Cowork) не имеет памяти между сессиями.
Каждая сессия начинается с нуля.
**Именно поэтому работает правило 4 мест:**
1. Notion (MASTER CONTEXT + сессионные страницы)
2. Obsidian (этот файл)
3. Репо tulm-dept-agents (код + .claude/logs/)
4. Claude Code CLAUDE.md

### Архитектура ботов (4 активных на Hetzner)
| Бот | База | .env файл | DEPT_MODE |
|-----|------|-----------|-----------|
| @TULM_Finance_bot | finbot_db | .env | finance |
| @TULM_VES_bot | vesbot_db | .env.ves | ves |
| @TULM_Railway_bot | railbot_db | .env.railway | railway |
| @merdan_tulm_bot | — | — | — |

---

## Ссылки
- Notion сессия: https://www.notion.so/34fd86a1fbdd81e8ba97e96d0f74517c
- Notion промпт Claude Code: https://www.notion.so/34fd86a1fbdd81958787e5093d8e02a5
- Репо: ~/tulm-dept-agents/
