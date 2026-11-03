from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from python_multipart.exceptions import MultipartParseError

from app.core.database import get_db
from app.schemas.issue_report import IssueReportCreate, IssueReportReceipt
from app.services.issue_report_service import MAX_REPORT_BYTES, MAX_REQUEST_BYTES, MAX_SCREENSHOT_BYTES, limiter, store_report

router = APIRouter(prefix="/public", tags=["Issue reports"])


@router.post("/issue-reports", response_model=IssueReportReceipt, status_code=201,
             openapi_extra={"security": [], "requestBody": {"required": True, "content": {
                 "multipart/form-data": {"schema": {"type": "object", "required": ["report"],
                     "properties": {"report": {"type": "string", "description": "IssueReportCreate JSON; see docs/issue-reporter.md"},
                                    "screenshot": {"type": "string", "format": "binary"}}}}}}})
async def create_issue_report(request: Request, response: Response, db: Session = Depends(get_db)):
    # Applied before body buffering or image decoding; trust only ASGI's client,
    # never unvalidated forwarded headers. Deployment must configure proxy trust.
    limiter.check(request.client.host if request.client else "unknown")
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "multipart/form-data":
        raise HTTPException(415, "Use multipart/form-data")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) < 0:
                raise ValueError()
            if int(declared) > MAX_REQUEST_BYTES:
                raise HTTPException(413, "Report request exceeds size limit")
        except ValueError:
            raise HTTPException(400, "Invalid Content-Length")
    # Bound the entire body before invoking multipart parsing, including chunked
    # requests. This also bounds multipart headers and unknown fields/files.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Report request exceeds size limit")
        body.extend(chunk)

    async def stream():
        yield bytes(body)

    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=1,
                                     max_part_size=MAX_REPORT_BYTES).parse()
    except (MultiPartException, MultipartParseError, UnicodeError) as error:
        raise HTTPException(400, "Invalid or oversized multipart report") from error
    try:
        items = list(form.multi_items())
        if len(items) != len(set(key for key, _ in items)) or any(key not in {"report", "screenshot"} for key, _ in items):
            raise HTTPException(422, "Use only report and optional screenshot parts")
        raw = form.get("report")
        screenshot = form.get("screenshot")
        if not isinstance(raw, str) or screenshot is not None and not isinstance(screenshot, UploadFile):
            raise HTTPException(422, "Invalid report parts")
        if len(raw.encode("utf-8")) > MAX_REPORT_BYTES:
            raise HTTPException(413, "Report JSON exceeds size limit")
        try:
            payload = IssueReportCreate.model_validate_json(raw)
        except ValidationError as error:
            # Do not echo user content, rejected fields, or validation inputs.
            raise HTTPException(422, "Invalid categories, description, consent, diagnostics or idempotency key") from error
        source = await screenshot.read(MAX_SCREENSHOT_BYTES + 1) if screenshot else None
        if source is not None and len(source) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(413, "Screenshot exceeds 5 MiB")
        receipt, replayed = await run_in_threadpool(store_report, db, payload, source)
        response.status_code = 200 if replayed else 201
        return receipt
    finally:
        await form.close()
