"""Quality regressions: factual inputs, measurable outcomes and earned points."""

import pytest

from app.domain import calculate_rating
from app.models import TaskFields
from app.quality import assess_quality
from test_part1_api import FULL_FIELDS, checked, empty_fields


def report_for(field, value):
    fields = TaskFields(**empty_fields(**{field: value}))
    return next(item for item in assess_quality(fields).fields if item.field == field)


@pytest.mark.parametrize("value, expected", [
    ("100 строк импортируются без потерь; фильтр отвечает до 1 секунды", "ready"),
    ("После перезапуска приложения сохранённые заказы отображаются в списке", "ready"),
    ("При вводе неверного email форма отклоняет запись и показывает ошибку", "ready"),
    ("Точность прогноза на контрольной выборке не ниже 90%", "ready"),
    ("Компания работает с 2026 года и имеет 10 сотрудников", "needs_work"),
    ("CSV содержит 100 строк", "needs_work"),
    ("Есть доступ к 100 заказам", "needs_work"),
    ("Импорт не работает, 100 строк", "needs_work"),
    ("Критерии пока не сформулированы; CSV содержит 100 строк", "needs_work"),
    ("Всё должно работать хорошо и качественно", "needs_work"),
])
def test_success_criteria_require_observable_result_and_measurement_or_test(value, expected):
    assert report_for("successCriteria", value).status == expected


@pytest.mark.parametrize("value, expected", [
    ("Есть тестовая таблица из 30 заказов", "ready"),
    ("Доступны 100 синтетических заказов в CSV и описание полей", "ready"),
    ("CSV с заказами отсутствует", "needs_work"),
    ("Доступ к CSV с заказами не предоставлен", "needs_work"),
    ("Доступ к таблице заказов ещё не согласован", "needs_work"),
    ("Таблицы с тестовыми заказами нет", "needs_work"),
    ("Доступ к CSV с заказами не предоставлен. Есть 30 синтетических заказов в JSON с описанием полей", "ready"),
    ("Данных пока нет. Планируем собрать 30 заказов в CSV", "needs_work"),
])
def test_data_distinguishes_available_materials_from_unavailable_or_planned(value, expected):
    assert report_for("data", value).status == expected


def test_short_concrete_constraints_are_not_rejected_for_length():
    assert report_for("constraints", "Только Python").status == "ready"


@pytest.mark.parametrize("value", ["а", "аб", "абв", "ыва", "qwe", "Только abc", "Только ыва"])
def test_few_letters_and_keyboard_fragments_never_earn_points(value):
    fields = TaskFields(**empty_fields(**{name: value for name in TaskFields.model_fields}))
    result = calculate_rating(fields)
    assert result.score == 0
    assert result.quality.version == "rules-v2"


def test_technical_identifiers_and_function_words_may_repeat_in_real_criteria():
    text = (
        "Загружаются 60 из 60 корректных строк; правильно обработаны 10 из 10 контрольных примеров; "
        "выгрузка содержит sku, stock_qty, min_qty, shortage_qty; "
        "shortage_qty = max(0, min_qty - stock_qty). "
        "Импорт и экспорт и поиск и фильтр и сохранение доступны в прототипе."
    )
    assert report_for("successCriteria", text).status == "ready"


@pytest.mark.parametrize("value", [
    "заказы заказы заказы заказы заказы заказы заказы заказы вручную",
    "заказы вручную заказы вручную заказы вручную",
    "asdf qwerty таблица заказов",
    "Заказы ааааа записываем в тетрадь",
])
def test_repetition_and_keyboard_filler_do_not_earn_quality(value):
    result = report_for("context", value)
    assert result.status == "needs_work"
    assert result.message and result.suggestion


def test_duplicate_text_cannot_fill_several_different_sections_for_points():
    fields = TaskFields(**empty_fields(
        context="Заказы записываем вручную, нужно создать единый список заказов",
        need="Заказы записываем вручную, нужно создать единый список заказов",
    ))
    rating = calculate_rating(fields)
    assert rating.score == 0
    assert all(item.status == "needs_work" for item in rating.quality.fields if item.field in {"context", "need"})


def test_quality_report_does_not_rewrite_business_facts_or_award_unconfirmed_fields():
    fields = TaskFields(**FULL_FIELDS)
    before = fields.model_dump()
    assert calculate_rating(fields).score == 100
    unconfirmed = calculate_rating(fields, confirmed=False)
    assert unconfirmed.score == 0
    assert len(unconfirmed.quality.eligibleFields) == 9
    assert calculate_rating(fields, confirmed_fields=["context", "need"]).score == 20
    assert fields.model_dump() == before


def test_readme_scenario_scores_concrete_information_and_explains_vague_criteria(client):
    fields = empty_fields(title="Заказы", context="Заказы записываем в тетрадь", need="Нужен единый список заказов")
    assert checked(client.post("/api/rating/preview", json={"fields": fields}))["score"] == 20
    fields.update(data="Есть тестовая таблица из 30 заказов", expectedResult="Веб-список заказов с поиском")
    assert checked(client.post("/api/rating/preview", json={"fields": fields}))["score"] == 55
    fields["successCriteria"] = "Всё должно работать хорошо"
    preview = checked(client.post("/api/rating/preview", json={"fields": fields}))
    assert preview["score"] == 55
    criterion = next(item for item in preview["quality"]["fields"] if item["field"] == "successCriteria")
    assert criterion["status"] == "needs_work" and criterion["suggestion"]
    fields["successCriteria"] = "100 строк импортируются без потерь; фильтр отвечает до 1 секунды"
    assert checked(client.post("/api/rating/preview", json={"fields": fields}))["score"] == 70
