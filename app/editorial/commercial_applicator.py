"""Transactional applicator; isolated by default, exact production capability required otherwise."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import Field, field_validator
from sqlalchemy import Table, MetaData, JSON, inspect, select, update

from app.editorial.application_receipts import receipts
from app.editorial.candidate_lookup import _sqlite_file
from app.editorial.commercial_preparation import _validated_inputs, _prepare_with_reader, PreparationError
from app.editorial.config import Authorization
from app.editorial.patches import DomainModel, BEER_FIELDS

REPO = Path(__file__).resolve().parents[2]
PERMISSION = 'beer.commercial.apply'


class ApplicationError(ValueError):
    """Fixed error code; callers must not log underlying DB exceptions or private payloads."""


class CommercialApproval(DomainModel):
    reference: UUID  # Opaque authorization receipt, never a Telegram/user identifier.
    case_id: UUID
    revision: int = Field(strict=True, gt=0)
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: Literal[True]

    @field_validator('confirmed', mode='before')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('Explicit confirmation required')
        return value


@dataclass(frozen=True)
class ApplicationResult:
    application_id: str
    replayed: bool
    receipt: dict = field(repr=False)


def approval_digest(proposal, interview_context):
    p, _, _, _, baseline_hash, _ = _validated_inputs(proposal, interview_context)
    raw = {'proposal':p.model_dump(mode='json'), 'baseline_sha256':baseline_hash}
    return sha256(json.dumps(raw, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _isolated_path(path, root):
    root, path = Path(root).resolve(strict=True), Path(path).resolve(strict=True)
    if not root.is_dir() or root == REPO or root in REPO.parents or REPO in root.parents \
            or root not in path.parents or not path.is_file() or path.name.casefold() == 'atlas.db':
        raise ApplicationError('isolated_test_storage_required')
    return path


def _catalog_path(engine, root):
    return _isolated_path(_sqlite_file(str(engine.url)), root)


def _check_receipts(connection):
    schema = inspect(connection)
    if not schema.has_table(receipts.name):
        raise ApplicationError('explicit_isolated_receipt_setup_required')
    if {c['name'] for c in schema.get_columns(receipts.name)} != set(receipts.c.keys()) \
            or schema.get_pk_constraint(receipts.name)['constrained_columns'] != ['application_id'] \
            or not any(set(c['column_names']) == {'case_id','proposal_revision'} for c in schema.get_unique_constraints(receipts.name)):
        raise ApplicationError('unsupported_receipt_schema')


def initialize_receipts_for_isolated_tests(engine, *, isolated_root):
    """Explicit additive setup ONLY outside the repo and inside the supplied test root."""
    _catalog_path(engine, isolated_root)
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            receipts.create(connection, checkfirst=True)
            _check_receipts(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def apply_commercial_update(engine, *, editorial_database, isolated_root, draft_id,
                            case_id, revision, approval, authorization, chat_id, user_id, transaction_guard=None,
                            production_scope=None):
    """Load trusted source records under SQLite locks; apply and receipt in main DB.

    The supplied Authorization must come from trusted configuration, not a client.
    Without a production capability, repository/atlas.db storage is always refused.
    """
    try:
        if not isinstance(authorization, Authorization) or not authorization.allows(chat_id, user_id, PERMISSION) \
                or not authorization.allows(chat_id, user_id, 'beer.edit'):
            raise ApplicationError('unauthorized')
        approval = CommercialApproval.model_validate(approval.model_dump(mode='json', warnings=False)
                                                     if isinstance(approval, CommercialApproval) else approval)
        case_id = str(UUID(str(case_id)))
        if type(revision) is not int or revision <= 0 or approval.revision != revision or str(approval.case_id) != case_id:
            raise ApplicationError('approval_revision_mismatch')
        if production_scope is None:
            target = _catalog_path(engine, isolated_root)
            source = _isolated_path(editorial_database, isolated_root)
        else:
            from app.editorial.production_execution import validate_production_scope
            validate_production_scope(production_scope,catalog_engine=engine,editorial_database=editorial_database)
            if not callable(transaction_guard):
                raise ApplicationError('production_transaction_guard_required')
            target, source = Path(production_scope.allowlist[1][0]), Path(production_scope.allowlist[0][0])
        if source.samefile(target):
            raise ApplicationError('separate_editorial_source_required')
        with engine.connect() as connection:
            # Both files are writable handles for BEGIN IMMEDIATE to lock both
            # against writers. There is NO DML against the Editorial source.
            connection.exec_driver_sql('ATTACH DATABASE ? AS editorial_source', (str(source),))
            connection.commit()
            try:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                if not authorization.allows(chat_id, user_id, PERMISSION) or not authorization.allows(chat_id, user_id, 'beer.edit'):
                    raise ApplicationError('unauthorized')
                if transaction_guard:
                    transaction_guard(connection)
                _check_receipts(connection)
                owner = connection.exec_driver_sql('SELECT chat_id,user_id,state FROM editorial_source.editorial_drafts WHERE id=?', (draft_id,)).first()
                if not owner or owner[0] != chat_id or owner[1] != user_id:
                    raise ApplicationError('proposal_owner_mismatch')
                row = connection.exec_driver_sql('SELECT payload FROM editorial_source.editorial_proposals WHERE draft_id=? AND revision=?', (draft_id,revision)).first()
                history_row = connection.exec_driver_sql('SELECT history FROM editorial_source.editorial_interviews WHERE id=?', (draft_id,)).first()
                if not row or not history_row:
                    raise ApplicationError('proposal_missing')
                proposal, history = json.loads(row[0]), json.loads(history_row[0])
                if proposal.get('case_id') != case_id or proposal.get('revision') != revision:
                    raise ApplicationError('proposal_integrity_mismatch')
                latest = connection.exec_driver_sql("SELECT MAX(revision) FROM editorial_source.editorial_proposals WHERE draft_id=? AND json_extract(payload,'$.case_id')=?", (draft_id,case_id)).scalar()
                if latest != revision:
                    raise ApplicationError('superseded_proposal')
                if history.get('navigation',{}).get('case_id') == case_id:
                    if owner[2] != 'saved':
                        raise ApplicationError('finish_proposal_before_application')
                    context = history
                else:
                    entry = history.get('saved_cases',{}).get(case_id,{})
                    if entry.get('status') != 'saved':
                        raise ApplicationError('saved_proposal_context_required')
                    context = entry['context']
                digest = approval_digest(proposal, context)
                if digest != approval.request_sha256:
                    raise ApplicationError('approval_content_mismatch')
                application_id = str(uuid5(NAMESPACE_URL, 'atlas:commercial:' + case_id + ':' + str(revision)))
                original = connection.execute(select(receipts).where(receipts.c.application_id == application_id)).mappings().first()
                if original:
                    if original['request_sha256'] != digest:
                        raise ApplicationError('idempotency_content_mismatch')
                    connection.commit()
                    return ApplicationResult(application_id, True, dict(original))
                beers = Table('beers', MetaData(), autoload_with=connection)

                def current(beer_id):
                    columns = [beers.c[key] for key in (*BEER_FIELDS,'prices','is_deleted')]
                    value = connection.execute(select(*columns).where(beers.c.id == beer_id)).mappings().first()
                    if not value or value['is_deleted'] not in (False, 0):
                        raise ApplicationError('beer_missing_or_deleted')
                    snapshot = dict(value)
                    snapshot.pop('is_deleted')
                    if isinstance(snapshot['prices'], str):
                        snapshot['prices'] = json.loads(snapshot['prices'])
                    return snapshot

                prepared = _prepare_with_reader(proposal, context, current)
                if prepared.status != 'prepared':
                    raise ApplicationError('conflict' if prepared.status == 'conflict' else 'noop')
                fields = {change.path[0] for change in prepared.changes}
                if not fields <= set(BEER_FIELDS) | {'prices'}:
                    raise ApplicationError('noncommercial_field')
                values = {key: prepared.proposed[key] for key in fields}
                # Existing SQLite fixtures may declare prices as TEXT; SQLAlchemy
                # reflection follows the real column type instead of importing a live engine.
                if 'prices' in values and not isinstance(beers.c.prices.type, JSON):
                    values['prices'] = json.dumps(values['prices'], allow_nan=False)
                if transaction_guard:
                    transaction_guard(connection)
                changed = connection.execute(update(beers).where(beers.c.id == prepared.beer_id).values(**values))
                if changed.rowcount != 1:
                    raise ApplicationError('update_count_mismatch')
                receipt = dict(application_id=application_id, case_id=case_id, proposal_revision=revision,
                               action_id=str(prepared.action_id), beer_id=prepared.beer_id, request_sha256=digest,
                               authorization_ref=str(approval.reference), status='applied',
                               applied_at=datetime.now(timezone.utc).isoformat(),
                               changes=[asdict(change) for change in prepared.changes])
                connection.execute(receipts.insert().values(**receipt))
                # Read the persisted JSON representation for consistent retry responses.
                stored = dict(connection.execute(select(receipts).where(receipts.c.application_id == application_id)).mappings().one())
                if transaction_guard:
                    transaction_guard(connection)
                connection.commit()
                return ApplicationResult(application_id, False, stored)
            except BaseException:
                connection.rollback()
                raise
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.exec_driver_sql('DETACH DATABASE editorial_source')
                connection.commit()
    except PreparationError:
        raise ApplicationError('invalid_commercial_preparation') from None
    except ApplicationError:
        raise
    except Exception:
        raise ApplicationError('application_failed_rolled_back') from None
