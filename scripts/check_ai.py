#!/usr/bin/env python3
"""Check server AI configuration without printing credentials."""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка настройки AI без вывода ключа.")
    parser.add_argument("--request", action="store_true", help="Выполнить один запрос с синтетической карточкой; используется лимит вашего API.")
    args = parser.parse_args()
    try:
        from app.config import load_local_env
        from app.models import TaskFields
        from app.semantic_quality import SemanticReviewError, evaluate_semantic, semantic_configured
    except ImportError:
        print("Сначала установите зависимости: python3 scripts/setup.py")
        print("Запускайте проверку через backend/.venv/bin/python scripts/check_ai.py")
        return 1
    load_local_env()
    if not semantic_configured():
        print("Ключ не задан. Добавьте OPENAI_API_KEY в .env в корне проекта и сохраните файл.")
        return 1
    model = os.environ.get("OPENAI_RATING_MODEL", "").strip() or os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"
    print(f"Ключ задан. Модель для рейтинга: {model}. Значение ключа скрыто.")
    if not args.request:
        print("Соединение с API не проверялось. Для одного синтетического запроса добавьте --request.")
        return 0
    fields = TaskFields(
        title="Синтетическая проверка импорта заказов",
        context="Предзаказы записывают в тетрадь, из-за чего теряются статусы.",
        need="Собрать список заказов и отслеживать их готовность.",
        users="Администратор пекарни отмечает готовые заказы.",
        data="Есть CSV с 30 синтетическими заказами: номер, дата и статус.",
        constraints="Прототип на Python за 7 дней, без платных интеграций.",
        expectedResult="Веб-страница со списком заказов, импортом CSV и фильтром по статусу.",
        successCriteria="Все 30 строк импортируются без потерь; фильтр отвечает до 1 секунды.",
        contact="demo@example.com",
        interactionFormat="Консультация в Telegram по вторникам; обратная связь за 1 день.",
        feedbackProcess="Проверка на синтетических данных.",
    )
    try:
        report = evaluate_semantic(fields)
    except SemanticReviewError as error:
        print(str(error))
        return 1
    print(f"API ответил; формат и источники проверены. Режим: {report.mode}.")
    print(report.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
