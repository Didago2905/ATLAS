"""Catalog-local receipts; separate metadata, never auto-created by ATLAS startup."""
from sqlalchemy import MetaData, Table, Column, String, Integer, JSON, UniqueConstraint

metadata = MetaData()
receipts = Table('editorial_commercial_applications', metadata,
    Column('application_id', String(36), primary_key=True),
    Column('case_id', String(36), nullable=False),
    Column('proposal_revision', Integer, nullable=False),
    Column('action_id', String(36), nullable=False),
    Column('beer_id', Integer, nullable=False),
    Column('request_sha256', String(64), nullable=False),
    Column('authorization_ref', String(36), nullable=False),
    Column('status', String(16), nullable=False),
    Column('applied_at', String(40), nullable=False),
    Column('changes', JSON, nullable=False),
    UniqueConstraint('case_id', 'proposal_revision', name='uq_editorial_commercial_case_revision'),
)
