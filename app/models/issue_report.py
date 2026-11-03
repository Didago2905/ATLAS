from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, JSON, LargeBinary, String, Text, text

from app.core.database import Base


class IssueReport(Base):
    __tablename__ = "issue_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    categories = Column(JSON, nullable=False)
    description = Column(Text, nullable=False)
    diagnostic_consent = Column(Boolean, nullable=False)
    schema_version = Column(Integer, nullable=False)
    diagnostics = Column(JSON, nullable=True)
    # Private database blob: never written to public/static directories.
    screenshot = Column(LargeBinary, nullable=True)
    screenshot_mime = Column(String(32), nullable=True)
    idempotency_key = Column(String(36), nullable=False, unique=True)
    payload_digest = Column(String(64), nullable=False)
    notification_state = Column(String(16), nullable=False, default="pending")
    notification_attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    notification_next_attempt_at = Column(DateTime, nullable=True)
    notification_lease_expires_at = Column(DateTime, nullable=True)
    notification_lease_token = Column(String(36), nullable=True)
    notification_sent_at = Column(DateTime, nullable=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    notification_error_code = Column(String(40), nullable=True)
    notification_destination = Column(String(32), nullable=False, default="incidents", server_default=text("'incidents'"))

    __table_args__ = (Index("ix_issue_reports_delivery", "notification_state", "notification_destination",
                           "notification_next_attempt_at", "notification_lease_expires_at"),)
