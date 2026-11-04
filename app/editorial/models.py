"""Separate metadata: importing Editorial never loads the live database engine."""
from sqlalchemy import Column, Integer, BigInteger, String, Text, JSON, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Cursor(Base):
    __tablename__ = "editorial_cursor"
    id = Column(Integer, primary_key=True)
    next_offset = Column(BigInteger, nullable=False, default=0)
    schema_version = Column(Integer, nullable=False, default=1)


class Update(Base):
    __tablename__ = "editorial_updates"
    id = Column(BigInteger, primary_key=True)
    payload = Column(JSON, nullable=False)
    state = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    error_code = Column(String(40), nullable=True)


class Asset(Base):
    __tablename__ = "editorial_assets"
    id = Column(String(32), primary_key=True)
    digest = Column(String(64), nullable=False, unique=True)
    extension = Column(String(8), nullable=False)
    byte_count = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)


class Draft(Base):
    __tablename__ = "editorial_drafts"
    id = Column(String(32), primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    state = Column(String(16), nullable=False, default="draft")
    revision = Column(Integer, nullable=False, default=0)
    prompt_message_id = Column(BigInteger, nullable=True)
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)


class Version(Base):
    __tablename__ = "editorial_versions"
    id = Column(Integer, primary_key=True)
    draft_id = Column(String(32), ForeignKey("editorial_drafts.id"), nullable=False)
    revision = Column(Integer, nullable=False)
    asset_id = Column(String(32), ForeignKey("editorial_assets.id"), nullable=False)
    compressed_photo = Column(Boolean, nullable=False)
    operation = Column(String(32), nullable=True)
    created_at = Column(String(40), nullable=False)
    __table_args__ = (UniqueConstraint("draft_id", "revision"),)


class Reply(Base):
    """Durable response intent; uncertainty never replays catalog operations."""
    __tablename__ = "editorial_replies"
    id = Column(Integer, primary_key=True)
    update_id = Column(BigInteger, ForeignKey("editorial_updates.id"), nullable=False, unique=True)
    draft_id = Column(String(32), ForeignKey("editorial_drafts.id"), nullable=True)
    chat_id = Column(BigInteger, nullable=False)
    text = Column(Text, nullable=False)
    markup = Column(JSON, nullable=True)
    is_prompt = Column(Boolean, nullable=False, default=False)
    asset_id = Column(String(32), ForeignKey("editorial_assets.id"), nullable=True)
    state = Column(String(16), nullable=False, default="pending")
    message_id = Column(BigInteger, nullable=True)
