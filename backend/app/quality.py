"""Explainable local quality checks, not a factual or semantic verification service.

Rules deliberately require field-specific evidence rather than rewarding length.
They work primarily with Russian descriptions and common technical English terms.
No external model, dictionary download, or network request is used.
"""

from collections import Counter
import re

from .models import QualityField, QualityReport, TaskFields


QUALITY_VERSION = "rules-v2"
SCORED_FIELDS = (
    "context", "need", "data", "expectedResult", "successCriteria",
    "constraints", "users", "contact", "interactionFormat",
)
PLACEHOLDERS = {"уточнить", "неизвестно", "tbd", "todo", "n/a", "пока неизвестно", "будет уточнено"}
HINTS = {
    "context": "Опишите, кто и как работает сейчас, и назовите конкретную проблему этого процесса.",
    "need": "Назовите действие, которое нужно изменить, и объект изменения: что объединить, сократить или начать отслеживать.",
    "data": "Укажите доступный источник или формат материалов и их состав: какие записи, поля, примеры либо ссылка доступны команде.",
    "expectedResult": "Назовите передаваемый результат и его функции: что именно команда покажет, передаст или запустит.",
    "successCriteria": "Опишите проверку результата: наблюдаемое действие и порог метрики либо условие теста с ожидаемым исходом.",
    "constraints": "Укажите конкретную границу проекта: срок, бюджет, разрешённые технологии, доступы или запрет интеграций.",
    "users": "Назовите конкретную группу пользователей и её роль, место работы или действия в решении.",
    "contact": "Добавьте рабочий email, телефон с кодом страны, Telegram-контакт или прямую ссылку для связи.",
    "interactionFormat": "Укажите канал консультаций и договорённость о времени: периодичность встреч, день либо срок ответа.",
}
READY_MESSAGES = {
    "context": "Есть описание текущего процесса и его предмета.",
    "need": "Указаны требуемое изменение и предмет работы.",
    "data": "Названы материалы или источник и сведения об их составе.",
    "expectedResult": "Названы результат работы и его функции или предмет.",
    "successCriteria": "Есть наблюдаемый результат и измерение либо воспроизводимое условие проверки.",
    "constraints": "Есть конкретная граница проекта.",
    "users": "Названа группа пользователей с контекстом или ролью.",
    "contact": "Указан контактный адрес или канал в распознаваемом формате.",
    "interactionFormat": "Указаны канал общения и время или периодичность обратной связи.",
}

STOP_WORDS = set("и или а но в во на по к с со из за у о об от до для над под это эти этот эта то что как кто мы вы они он она оно наш наша наши ваш его ее их есть будет будут должен должна должно нужно нужен нужна надо хотим можно очень более менее только все всё всем каждого каждый уже пока также при после если когда через между раз два три".split())
GENERIC_WORDS = set("задача задачи задача проект проекта систему система системы решение решения работа работы работать сделать делать улучшить улучшение хороший хорошо хорошие качественный качественно качественное лучше лучший лучших быстро быстрее удобный удобно удобное эффективный эффективно современный современно бизнес бизнеса развитие помощь успешно успех результат результата результаты пользователей пользователь пользователи люди всех любой разные прочее другое другое многое нужно важно полезно нормальный нормально отлично супер".split())
VAGUE = re.compile(
    r"^(?:вс[её]\s+(?:хорошо|отлично|работает|понятно|нормально)|"
    r"(?:сделать|нужно|надо|хотим|будет)\s+(?:вс[её]\s+)?(?:хорошо|лучше|удобно|быстро|качественно)|"
    r"(?:для\s+)?(?:всех|любых)\s*(?:людей|пользователей|желающих)?|"
    r"(?:любые|разные|какие-то)\s+(?:данные|пользователи|материалы)|"
    r"(?:готовое|хорошее|качественное|удобное)\s+(?:решение|приложение|система))$"
)
PROCESS = re.compile(r"вручную|таблиц|тетрад|журнал|чат|мессендж|сейчас|сегодня|вед[еёу]|записыва|собира|перенос|поступа|обрабатыва|теря|дублир|задерж|ошиб|сверя|рассыла|получа|отдельн|разрознен|ежеднев|weekly|manual|spreadsheet")
CHANGE = re.compile(r"объедин|собра|сократ|уменьш|увелич|улучш|автоматиз|устран|исключ|сниз|выяв|упрост|контрол|отслеж|показыва|провер|формир|вести|созда|сдела|нужн|нужен|нужна|разработ|хотим|выдел|упорядоч|искать|находить|определ|reduce|automate|track|combine")
ARTIFACT = re.compile(r"прототип|приложени|веб|сайт|бот\b|дашборд|отч[её]т|макет|инструкц|алгоритм|модел|прогноз|скрипт|ноутбук|api\b|модул|реестр|форм[ауы]\b|таблиц|список|панел|схем|план\b|dashboard|report|prototype|script")
FUNCTION = re.compile(r"импорт|экспорт|выгруз|фильтр|поиск|создани|просмотр|изменени|отмен|запис|списк|уч[её]т|расч[её]т|причин|анализ|прогноз|показ|ответ|статус|загруз|провер|рекоменд|расписани|инструкц|управлен|регистрац|filter|search|import|export")
AUDIENCE = re.compile(r"менеджер|клиент|покупател|заказчик|администратор|мастер|преподавател|студент|ученик|учител|родител|реб[её]нок|дет[еи]|курьер|диспетчер|руководител|сотрудник|оператор|аналитик|закупщик|управляющ|продавец|продавц|пекар|владелец|владельц|посетител|гост[ьи]|врач|пациент|бухгалтер|агроном|фермер|водител|разработчик|пользовател|customer|student|manager|operator")
DATA_SOURCE = re.compile(r"\bcsv\b|\bjson\b|\bxlsx?\b|\bsql\b|\bapi\b|\bcrm\b|\bpdf\b|\blog\b|таблиц|датасет|набор|выборк|баз[аеуы]\s+данных|файл|лог[иао]\b|опрос|интервью|пример|запис|источник|https?://")
DATA_UNAVAILABLE = re.compile(
    r"(?:нет|отсутству\w*|недоступ\w*)\s+(?:(?:пока|никаких|исходных|доступных|тестовых)\s+){0,2}(?:данн|материал|пример|доступ)|"
    r"(?:^|[.,:]\s*)(?:данн\w*|материал\w*|csv|json|файл\w*|доступ\w*)\s+(?:пока\s+)?(?:нет|отсутств|недоступ|не\s+(?:предостав|доступ|извест))|"
    r"доступ\w*\s+(?:к\s+\w+\s+)?(?:пока\s+)?(?:нет|неизвест|не\s+соглас)|"
    r"\b(?:csv|json|файл\w*|таблиц\w*|данн\w*|доступ\w*)\b.{0,80}\b(?:недоступ\w*|отсутству(?:ет|ют)|нет\s*$|не\s+(?:предоставл|получен|согласован|доступен|доступны))|"
    r"\b(?:планируем|предстоит|будем)\s+(?:собрать|собирать|создать|получить)|ещ[её]\s+не\s+(?:собран|получен|определен)"
)
NO_CRITERIA = re.compile(
    r"(?:нет|отсутству\w*)\s+(?:(?:пока|никаких|измеримых|ч[её]тких)\s+){0,2}(?:критери|метрик|проверок)|"
    r"(?:критери\w*|метрик\w*)\s+(?:пока\s+)?(?:нет|отсутств|неизвест|не\s+(?:определ|задан|соглас|сформулир|описан|готов|извест|нуж))|"
    r"(?:критери\w*|метрик\w*)\s+(?:определим|зададим|согласуем|сформулируем|уточним)\s+(?:позже|потом)|"
    r"(?:не\s+будем|не\s+планируем)\s+(?:провер|измер)|без\s+(?:проверки|критериев|метрик)"
)
# Possession of a CSV or access to a dataset is an input fact, not a tested
# outcome. Avoid generic "contains"/"access" matching that rewards row counts
# without any action performed by the proposed solution.
OBSERVABLE = re.compile(r"импорт|загружа|выгруз|экспорт|обработ|сохран|отклон|возвращ|отображ|показыва|совпад|соответств|проход|пройд|ответ|ошибк|точност|полнот|wape|mape|rmse|accuracy|precision|recall|f1\b|верн|теря|потер|дублик|восстан|рассчит|вычисл|определ|отправ|фильтр|сч[её]тчик|latency")
MEASUREMENT = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|процент)|"
    r"\d+\s*(?:из|/)\s*\d+|"
    r"\d+(?:[.,]\d+)?\s*(?:мс\b|ms\b|секунд|миллисекунд|минут|строк|запис|контрольн|тестов|заказ|товар|отправлен|байт|мб\b|mb\b|запрос)|"
    r"(?:не\s+(?:более|менее|выше|ниже)|максимум|минимум|[<>≤≥]=?)\s*\d+(?:[.,]\d+)?\s*(?:$|[,.;])"
)
TEST_CONDITION = re.compile(r"после\s+(?:перезагруз|повтор|перезапуск)|при\s+(?:повтор|импорт|ввод|пуст|неверн|некоррект|ошиб|сбо|отсутств)|если\s+|когда\s+|повторн\w*\s+|неверн\w*\s+|некорректн\w*\s+|пуст\w*\s+|выбранн|исходн\w*\s+данн|контрольн|согласованн\w*\s+тест|без\s+(?:потерь|дубликатов)|не\s+теря|не\s+созда[её]т\w*\s+дублик")
FAILED_OUTCOME = re.compile(r"не\s+(?:работа|импортиру|загружа|обрабатыва|сохраня|отобража|отправля|отвеча|проход)|невозможно\s+(?:провер|измер|импорт|сохран)|не\s+удалось")
NEGATIVE_TEST = re.compile(r"неверн|некорректн|невалидн|пуст\w*\s+(?:пол|ввод|знач)|дубликат|ошибочн|отсутств\w*\s+обязательн")
VAGUE_CONDITION = re.compile(r"(?:если|когда)\s+(?:вс[её]\s+)?(?:хорошо|нормально|готово|получится)|(?:может|возможно|наверное|надеемся)\s+")
BOUNDARY = re.compile(r"срок|бюджет|дедлайн|пилот|только|без\s+\w+|не\s+(?:использ|подключ|отправ|хран|передава)|запрещ|разреш|огранич|до\s+\d|за\s+\d|не\s+(?:более|позднее)|must|only|without")
CHANNEL = re.compile(r"созвон|встреч|консультац|онлайн|видео|почт|чат|телефон|telegram|телеграм|zoom|teams|email|e-mail|slack")
SCHEDULE = re.compile(r"ежеднев|еженед|кажд|раз\s+в|в\s+(?:день|неделю|месяц)|в\s+течение|по\s+(?:понедельник|вторник|сред|четверг|пятниц|суббот|воскресен)|(?:понедельник|вторник|сред[ау]|четверг|пятниц|суббот|воскресен)|\d+\s*(?:час|минут|дн|день)|weekly|daily")


def normalized_text(value: str) -> str:
    return " ".join(value.casefold().split()).strip(" .…!?;:—–-_\"'«»()[]")


def has_content(value: str) -> bool:
    """Compatibility helper for AI missing-field checks; quality is separate."""
    normalized = normalized_text(value)
    return bool(re.search(r"\w", normalized, flags=re.UNICODE)) and normalized not in PLACEHOLDERS


def words(value: str) -> list[str]:
    return re.findall(r"[a-zа-яё]+", value.casefold())


def informative_words(value: str) -> list[str]:
    return [word for word in words(value) if len(word) > 2 and word not in STOP_WORDS | GENERIC_WORDS]


def noise_reason(value: str) -> str | None:
    value = normalized_text(value)
    tokens = words(value)
    letters = "".join(tokens)
    if letters and len(letters) <= 3 and not re.search(r"\d", value):
        return "Нескольких букв недостаточно, чтобы объяснить содержание поля."
    keyboard_rows = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю", "абвгде", "abcdef", "xyz")
    if any(len(token) == 3 and token != "про" and token in row for token in tokens for row in keyboard_rows):
        return "Текст содержит короткий набор букв вместо конкретного описания."
    if re.search(r"asdf|qwert|zxcv|йцук|фыв|ячсм|lorem\s+ipsum", value):
        return "Текст похож на случайный набор символов или шаблон-заполнитель."
    if re.search(r"([a-zа-яё])\1{3,}|([a-zа-яё]{2,4})\1{2,}", value):
        return "Повторяющиеся символы не объясняют содержание поля."
    # Repeated schema identifiers and function words are normal in acceptance
    # criteria. Reject dominance, not an arbitrary absolute word count.
    content_tokens = [token for token in tokens if token not in STOP_WORDS]
    if len(content_tokens) >= 4 and Counter(content_tokens).most_common(1)[0][1] / len(content_tokens) > 0.55:
        return "Повторение одних и тех же слов не добавляет проверяемых сведений."
    for width in range(2, min(8, len(tokens) // 3) + 1):
        if any(tokens[start:start + width] * 3 == tokens[start:start + width * 3] for start in range(len(tokens) - width * 3 + 1)):
            return "Повторение одних и тех же фраз не добавляет проверяемых сведений."
    if tokens and all(not re.search(r"[aeiouyаеёиоуыэюя]", word) for word in tokens if len(word) >= 4) and any(len(word) >= 6 for word in tokens):
        return "Не удаётся распознать осмысленное описание в наборе символов."
    return None


def hard_quality_failure(value: str) -> str | None:
    """Cheap input floor shared with semantic review; never a semantic verdict."""
    normalized = normalized_text(value)
    if not has_content(normalized):
        return "Поле пустое или содержит явную заглушку."
    reason = noise_reason(normalized)
    if reason:
        return reason
    if VAGUE.fullmatch(normalized) or not informative_words(normalized):
        return "Общая формулировка не содержит конкретных сведений для этого раздела."
    return None


def contact_ready(value: str) -> bool:
    if re.search(r"(?<![\w.+-])[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value, re.I):
        return True
    if re.search(r"(?:https?://)?(?:t\.me|wa\.me|telegram\.me)/[a-z0-9_+]{5,}", value, re.I):
        return True
    if re.search(r"(?<!\w)@[a-z][a-z0-9_]{4,31}\b", value, re.I):
        return True
    for match in re.finditer(r"(?<!\w)\+\d[\d ()-]{8,}\d", value):
        digits = re.sub(r"\D", "", match.group())
        if 10 <= len(digits) <= 15 and len(set(digits)) >= 4:
            return True
    return False


def clauses(value: str) -> list[str]:
    # Text is casefolded. A dot before whitespace ends a sentence, whereas
    # decimals, domains and URLs remain intact.
    return re.split(r"[;\n]|\.(?=\s)", value)


def data_ready(value: str) -> bool:
    for clause in clauses(value):
        if DATA_UNAVAILABLE.search(clause) or not DATA_SOURCE.search(clause):
            continue
        details = [word for word in informative_words(clause) if word not in {"данные", "данных", "файл", "файлы", "таблица", "csv", "json", "xlsx", "источник", "доступны", "доступен"}]
        if re.search(r"https?://[^\s]+", clause) or len(details) >= 2:
            return True
        if details and (re.search(r"\d+\s*\w+", clause) or re.search(r"пол[яе]\b|столбц|schema", clause)):
            return True
    return False


def success_ready(value: str) -> bool:
    if NO_CRITERIA.search(value):
        return False
    for clause in clauses(value):
        if not OBSERVABLE.search(clause) or VAGUE_CONDITION.search(clause):
            continue
        # A statement that the feature fails is not an acceptance criterion.
        # Intentional rejection of invalid input remains a valid negative test.
        if FAILED_OUTCOME.search(clause) and not NEGATIVE_TEST.search(clause):
            continue
        if MEASUREMENT.search(clause):
            return True
        if TEST_CONDITION.search(clause) and len(informative_words(clause)) >= 2:
            return True
    return False


def field_ready(field: str, value: str) -> bool:
    tokens = words(value)
    details = informative_words(value)
    if field == "contact":
        return contact_ready(value)
    if field == "data":
        return data_ready(value)
    if field == "successCriteria":
        return success_ready(value)
    if field == "context":
        return len(tokens) >= 4 and len(details) >= 2 and bool(PROCESS.search(value))
    if field == "need":
        return len(tokens) >= 3 and len(details) >= 2 and bool(CHANGE.search(value))
    if field == "expectedResult":
        return len(details) >= 2 and bool(ARTIFACT.search(value)) and bool(FUNCTION.search(value))
    if field == "users":
        return len(tokens) >= 2 and bool(AUDIENCE.search(value)) and bool(details)
    if field == "constraints":
        concrete_boundary = len(details) >= 2 or (bool(details) and bool(re.search(r"^(?:только|без|не\s+использовать)\s+\S+", value)))
        return concrete_boundary and bool(BOUNDARY.search(value)) and not re.search(r"ограничени[йя]\s+(?:пока\s+)?нет|без\s+ограничени", value)
    if field == "interactionFormat":
        return bool(CHANNEL.search(value)) and bool(SCHEDULE.search(value))
    return False


def assess_quality(fields: TaskFields) -> QualityReport:
    normalized = {name: normalized_text(getattr(fields, name)) for name in SCORED_FIELDS}
    repeated = Counter(value for value in normalized.values() if len(value) > 12 and len(words(value)) >= 3)
    results = []
    for field, value in normalized.items():
        if not has_content(value):
            status = "missing"
            message = "Поле пустое или содержит явную заглушку."
        else:
            reason = noise_reason(value)
            if repeated[value] > 1:
                reason = "Одинаковый текст скопирован в разные разделы карточки."
            if VAGUE.fullmatch(value) or (field != "contact" and not informative_words(value)):
                reason = "Общая формулировка не содержит конкретных сведений для этого раздела."
            if reason:
                status, message = "needs_work", reason
            elif not field_ready(field, value):
                status = "needs_work"
                message = {
                    "data": "Не описаны доступные материалы с составом, либо прямо указано отсутствие данных или доступа.",
                    "successCriteria": "Не найдена связка наблюдаемого результата с измерением или воспроизводимой проверкой; одних цифр недостаточно.",
                    "contact": "Не найден контактный адрес или прямой канал связи в распознаваемом формате.",
                    "interactionFormat": "Недостаточно канала общения или договорённости о времени обратной связи.",
                }.get(field, "Формулировку нужно конкретизировать для этого раздела.")
            else:
                status, message = "ready", READY_MESSAGES[field]
        results.append(QualityField(field=field, status=status, message=message, suggestion="" if status == "ready" else HINTS[field]))
    eligible = [result.field for result in results if result.status == "ready"]
    return QualityReport(
        version=QUALITY_VERSION,
        fields=results,
        eligibleFields=eligible,
        summary=f"Локальная проверка правил: {len(eligible)} из {len(SCORED_FIELDS)} разделов достаточно конкретны для баллов. Это эвристики, а не гарантия достоверности или смысловой корректности.",
    )
