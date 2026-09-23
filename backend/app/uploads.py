"""Bounded PDF upload parsing. Files are returned as data, never executed or rendered."""

import re
import unicodedata

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from .proposal_models import ProposalInput

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_PDF_BYTES + 512 * 1024


def pdf_filename(value: str | None) -> str:
    name = re.split(r"[/\\]", value or "")[-1]
    name = "".join(character for character in unicodedata.normalize("NFC", name) if not unicodedata.category(character).startswith("C"))
    name = name.strip(" .")
    if not name.lower().endswith(".pdf") or len(name) > 160:
        raise HTTPException(status_code=422, detail="Выберите PDF-файл с именем не длиннее 160 символов")
    return name


async def read_proposal_upload(request: Request) -> tuple[ProposalInput, tuple[str, bytes]]:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Для отправки файла используйте multipart/form-data")
    # Bound the incoming stream before the multipart parser can spool files.
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="PDF-файл слишком большой. Максимум — 10 МиБ")
        raw.extend(chunk)
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": bytes(raw), "more_body": False}

    bounded = Request(request.scope, receive)
    async with bounded.form(max_files=1, max_fields=1, max_part_size=256 * 1024) as form:
        if len(form.multi_items()) != 2 or set(form) != {"proposal", "file"}:
            raise HTTPException(status_code=422, detail="Передайте описание предложения и один PDF-файл")
        payload, file = form["proposal"], form["file"]
        if not isinstance(payload, str) or not isinstance(file, UploadFile):
            raise HTTPException(status_code=422, detail="Неверный формат описания или файла")
        try:
            proposal = ProposalInput.model_validate_json(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="Проверьте идею, план, срок, ссылку и выбранную команду") from error
        name = pdf_filename(file.filename)
        content = await file.read(MAX_PDF_BYTES + 1)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="PDF-файл слишком большой. Максимум — 10 МиБ")
        if file.content_type not in ("application/pdf", "application/octet-stream", ""):
            raise HTTPException(status_code=422, detail="Поддерживаются только PDF-файлы")
        if not re.match(rb"%PDF-[12]\.\d", content[:8]) or b"%%EOF" not in content[-1024:]:
            raise HTTPException(status_code=422, detail="Файл не похож на завершённый PDF. Проверьте его и повторите загрузку")
        return proposal, (name, content)
