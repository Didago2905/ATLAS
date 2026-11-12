"""Durable execution requests with isolated or explicitly file-bound production capability."""
from copy import deepcopy
from dataclasses import dataclass, field
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from sqlalchemy import select, inspect
from sqlalchemy.orm import Session

from app.editorial.candidate_lookup import _sqlite_file
from app.editorial.commercial_applicator import (apply_commercial_update, CommercialApproval, ApplicationError,
                                               approval_digest, PERMISSION, _isolated_path)
from app.editorial.commercial_preparation import _validated_inputs
from app.editorial.config import Authorization
from app.editorial.models import Interview, Draft
from app.editorial import draft_lifecycle
from app.editorial.production_execution import ProductionExecutionScope, validate_production_scope, validate_request

TTL = timedelta(minutes=15)
LEASE = timedelta(seconds=60)
BACKOFF = timedelta(seconds=30)
MAX_ATTEMPTS = 3
_SEAL = object()


def utcnow():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False)


def _binding(request):
    keys = ('id','draft_id','chat','operator','case_id','revision','beer_id','action_id','approval','request_sha256',
            'catalog_binding','approved_at','expires_at','expected_changes','response_update_id')
    values = {key:request[key] for key in keys}
    if 'production_activation' in request:
        values['production_activation'] = request['production_activation']
    return sha256(_json(values).encode()).hexdigest()


def enqueue(state, draft, review, prepared, *, update_id=None, production_activation=None):
    """Only called after final authenticated confirmation; committed by Editorial inbox transaction."""
    now = utcnow()
    approval = CommercialApproval.model_validate(review['approval'])
    if prepared.status!='prepared' or str(approval.case_id)!=str(prepared.case_id) or approval.revision!=prepared.proposal_revision \
            or (review['chat'],review['operator'])!=(draft.chat_id,draft.user_id) \
            or review['request_sha256']!=approval.request_sha256 or review['current_sha256']!=prepared.current_sha256:
        raise ValueError('invalid_execution_approval_binding')
    request = dict(id=str(approval.reference),draft_id=draft.id,chat=draft.chat_id,operator=draft.user_id,
                   case_id=str(approval.case_id),revision=approval.revision,beer_id=prepared.beer_id,action_id=str(prepared.action_id),
                   approval=approval.model_dump(mode='json'),request_sha256=approval.request_sha256,
                   catalog_binding=review['catalog_binding'],approved_at=now.isoformat(),expires_at=(now+TTL).isoformat(),
                   expected_changes=[asdict(change) for change in prepared.changes],response_update_id=update_id,
                   state='pending',attempts=0,retryable=True,error_code=None,lease_token=None,lease_until=None,
                   next_attempt_at=None,receipt_id=None)
    if production_activation is not None:
        request['production_activation'] = production_activation
    request['binding_sha256'] = _binding(request)
    requests = deepcopy(state.history.get('execution_requests',{}))
    if request['id'] in requests:
        raise ValueError('duplicate_execution_authorization')
    requests[request['id']] = request
    state.history = {**state.history,'execution_requests':requests}
    return request['id']


@dataclass(frozen=True)
class IsolatedExecutionScope:
    editorial_engine: object = field(repr=False)
    catalog_engine: object = field(repr=False)
    temporary: object = field(repr=False)
    allowlist: tuple = field(repr=False)
    seal: object = field(default=None,repr=False)


def _file_identity(path):
    stat = path.stat()
    if stat.st_nlink != 1:
        raise ValueError('hardlinked_execution_target')
    return (str(path),stat.st_dev,stat.st_ino)


def allow_isolated_execution(editorial_engine,catalog_engine,*,temporary_directory):
    if not isinstance(temporary_directory,tempfile.TemporaryDirectory):
        raise ValueError('temporary_directory_capability_required')
    root = Path(temporary_directory.name).resolve(strict=True)
    if Path(tempfile.gettempdir()).resolve() not in root.parents:
        raise ValueError('temporary_storage_required')
    paths = tuple(_isolated_path(_sqlite_file(str(engine.url)),root) for engine in (editorial_engine,catalog_engine))
    if paths[0].samefile(paths[1]):
        raise ValueError('separate_execution_files_required')
    return IsolatedExecutionScope(editorial_engine,catalog_engine,temporary_directory,
                                  tuple(_file_identity(path) for path in paths),_SEAL)


def validate_scope(scope):
    if type(scope) is ProductionExecutionScope:
        validate_production_scope(scope)
        return None
    if type(scope) is not IsolatedExecutionScope or scope.seal is not _SEAL:
        raise ValueError('isolated_execution_disabled')
    root = Path(scope.temporary.name).resolve(strict=True)
    identities = tuple(_file_identity(_isolated_path(_sqlite_file(str(engine.url)),root))
                       for engine in (scope.editorial_engine,scope.catalog_engine))
    if identities != scope.allowlist:
        raise ValueError('execution_target_not_allowlisted')
    return root


def _request(db,draft_id,request_id):
    state = db.get(Interview,draft_id)
    if not state or not isinstance(state.history,dict):
        raise ValueError('execution_request_missing')
    request = deepcopy(state.history.get('execution_requests',{}).get(request_id))
    if not request or request['id'] != request_id or request['binding_sha256'] != _binding(request):
        raise ValueError('execution_binding_mismatch')
    return state, request


def _load(scope,draft_id,request_id):
    with Session(scope.editorial_engine) as db:
        _, request = _request(db,draft_id,request_id)
        owner = db.get(Draft,draft_id)
        if not owner or (owner.chat_id,owner.user_id) != (request['chat'],request['operator']):
            raise ValueError('execution_owner_mismatch')
        return request


def _read_receipt(scope,request):
    """Verified historical receipt takes precedence over expiry/retries; never reapplies."""
    validate_scope(scope)
    from app.editorial.application_receipts import receipts
    application_id = str(uuid5(NAMESPACE_URL,'atlas:commercial:'+request['case_id']+':'+str(request['revision'])))
    with scope.catalog_engine.connect() as connection:
        if not inspect(connection).has_table(receipts.name):
            raise ValueError('receipt_schema_missing')
        row = connection.execute(select(receipts).where(receipts.c.application_id==application_id)).mappings().first()
    if not row:
        return None
    expected = dict(case_id=request['case_id'],proposal_revision=request['revision'],beer_id=request['beer_id'],action_id=request['action_id'],
                    authorization_ref=request['id'],request_sha256=request['request_sha256'],status='applied')
    if any(row[key]!=value for key,value in expected.items()) or _json(row['changes'])!=_json(request['expected_changes']) \
            or not datetime.fromisoformat(request['approved_at']) <= datetime.fromisoformat(row['applied_at']) <= datetime.fromisoformat(request['expires_at']):
        raise ValueError('receipt_inconsistent')
    return dict(row)


def _finish(scope,draft_id,request_id,status,*,receipt=None,error=None,retryable=False,clock=utcnow,expected_lease=None):
    # Each source transaction finishes/closes before returning. No source transaction spans apply.
    with Session(scope.editorial_engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        state, request = _request(db,draft_id,request_id)
        if not receipt and expected_lease is not None and request['lease_token']!=expected_lease:
            return request['state']
        request.update(state=status,error_code=error,retryable=retryable,lease_token=None,lease_until=None,
                       next_attempt_at=(clock()+BACKOFF).isoformat() if retryable else None,
                       receipt_id=receipt['application_id'] if receipt else None,finished_at=clock().isoformat())
        state.history = {**state.history,'execution_requests':{**state.history['execution_requests'],request_id:request}}
        if receipt:
            # Only an actually verified receipt can replace a still-pending Telegram response.
            from app.editorial.models import Reply
            reply = db.scalar(select(Reply).where(Reply.update_id==request.get('response_update_id'),Reply.draft_id==draft_id,
                                                Reply.chat_id==request['chat'],Reply.state=='pending'))
            if reply:
                reply.text = f"Aplicación verificada · recibo {receipt['application_id']}\nCerveza #{receipt['beer_id']} · revisión {receipt['proposal_revision']}\nUTC: {receipt['applied_at']}"
                reply.markup, reply.is_prompt = None, False
        else:
            from app.editorial.models import Reply
            reply = db.scalar(select(Reply).where(Reply.update_id==request.get('response_update_id'),Reply.draft_id==draft_id,
                                                Reply.chat_id==request['chat'],Reply.state=='pending'))
            if reply:
                reply.text = f'Solicitud {request_id}: {status}. No se ha verificado un recibo de aplicación. ' + ('Usa /recuperar22 con este ID para solicitar un reintento controlado.' if retryable else 'No se reintentará automáticamente.')
                reply.markup, reply.is_prompt = None, False
        db.commit()
    return status


def _authorized(loader,request,*,require_base=False):
    try:
        auth = loader()
    except Exception:
        raise ApplicationError('authorization_unavailable') from None
    if not isinstance(auth,Authorization) or not auth.allows(request['chat'],request['operator'],'beer.edit') \
            or not auth.allows(request['chat'],request['operator'],PERMISSION) \
            or (require_base and not auth.allows(request['chat'],request['operator'])):
        raise ApplicationError('unauthorized')
    return auth


def execute_request(scope,*,draft_id,request_id,authorization_loader,clock=utcnow):
    """Post-commit boundary; production requires a separately enabled exact-target capability."""
    root = validate_scope(scope)
    checked_out = getattr(scope.editorial_engine.pool,'checkedout',lambda:0)
    if checked_out():
        raise ValueError('editorial_session_must_be_closed')
    request = _load(scope,draft_id,request_id)
    production = type(scope) is ProductionExecutionScope
    if production:
        validate_request(scope,request)
        _authorized(authorization_loader,request,require_base=True)
    # An interrupted process may have committed SQL before reconciling Editorial.
    try:
        receipt = _read_receipt(scope,request)
    except ValueError:
        return _finish(scope,draft_id,request_id,'failed',error='receipt_inconsistent',clock=clock)
    except Exception:
        return _finish(scope,draft_id,request_id,'failed',error='receipt_verification_unavailable',retryable=True,clock=clock)
    if receipt:
        return _finish(scope,draft_id,request_id,'applied',receipt=receipt,clock=clock)
    if request['state']=='applied':
        return _finish(scope,draft_id,request_id,'failed',error='persisted_receipt_missing',clock=clock)
    if request['state'] in {'conflict','expired'} or (request['state']=='failed' and not request['retryable']):
        return request['state']
    now=clock()
    if now>=datetime.fromisoformat(request['expires_at']):
        return _finish(scope,draft_id,request_id,'expired',error='approval_expired',clock=clock)
    with Session(scope.editorial_engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        state, request = _request(db,draft_id,request_id)
        if request['state'] in {'conflict','expired'} or (request['state']=='failed' and not request['retryable']):
            return request['state']
        if request['state']=='applied':
            return 'receipt_recheck_required'
        if request['state']=='executing' and request['lease_until'] and now<datetime.fromisoformat(request['lease_until']):
            return 'executing'
        if request.get('next_attempt_at') and now<datetime.fromisoformat(request['next_attempt_at']):
            return request['state']
        if request['attempts']>=MAX_ATTEMPTS:
            return _finish_after_close_error(db,state,request,request_id)
        request.update(state='executing',attempts=request['attempts']+1,lease_token=uuid4().hex,
                       lease_until=(now+LEASE).isoformat(),attempt_started_at=now.isoformat(),retryable=True)
        state.history={**state.history,'execution_requests':{**state.history['execution_requests'],request_id:request}}
        db.commit()
    # The claim transaction has exited and returned its connection BEFORE the applicator starts.
    try:
        validate_scope(scope)
        if request['catalog_binding']!=sha256(scope.allowlist[1][0].encode()).hexdigest():
            raise ApplicationError('catalog_binding_mismatch')
        auth=_authorized(authorization_loader,request,require_base=production)

        def transaction_guard(connection):
            validate_scope(scope)
            raw=connection.exec_driver_sql('SELECT history FROM editorial_source.editorial_interviews WHERE id=?',(draft_id,)).scalar_one()
            stored=json.loads(raw)['execution_requests'][request_id]
            if production:
                validate_request(scope,stored)
            if stored['binding_sha256']!=_binding(stored) or stored['binding_sha256']!=request['binding_sha256'] \
                    or stored['state']!='executing' or stored['lease_token']!=request['lease_token']:
                raise ApplicationError('execution_lease_or_binding_changed')
            if clock()>=datetime.fromisoformat(stored['expires_at']):
                raise ApplicationError('approval_expired')
            if clock()>=datetime.fromisoformat(stored['lease_until']):
                raise ApplicationError('execution_lease_expired')
            _authorized(authorization_loader,stored,require_base=production)

        production_options = {'production_scope':scope} if production else {}
        apply_commercial_update(scope.catalog_engine,editorial_database=scope.allowlist[0][0],isolated_root=root,
                                draft_id=draft_id,case_id=request['case_id'],revision=request['revision'],
                                approval=request['approval'],authorization=auth,chat_id=request['chat'],user_id=request['operator'],
                                transaction_guard=transaction_guard,**production_options)
        receipt=_read_receipt(scope,request)
        if not receipt:
            raise ApplicationError('persisted_receipt_missing')
        return _finish(scope,draft_id,request_id,'applied',receipt=receipt,clock=clock)
    except Exception as error:
        # Never infer rollback from an exception: it may have happened AFTER commit.
        try:
            receipt=_read_receipt(scope,request)
        except Exception:
            receipt=None
        if receipt:
            return _finish(scope,draft_id,request_id,'applied',receipt=receipt,clock=clock)
        code=str(error) if isinstance(error,ApplicationError) else 'execution_unavailable'
        if code=='approval_expired':
            return _finish(scope,draft_id,request_id,'expired',error=code,clock=clock,expected_lease=request['lease_token'])
        if code=='conflict':
            return _finish(scope,draft_id,request_id,'conflict',error=code,clock=clock,expected_lease=request['lease_token'])
        retry=code in {'execution_unavailable','application_failed_rolled_back','execution_lease_expired'} and request['attempts']<MAX_ATTEMPTS
        return _finish(scope,draft_id,request_id,'failed',error=code,retryable=retry,clock=clock,expected_lease=request['lease_token'])


def _finish_after_close_error(db,state,request,request_id):
    request.update(state='failed',retryable=False,error_code='attempt_budget_exhausted',lease_token=None,lease_until=None)
    state.history={**state.history,'execution_requests':{**state.history['execution_requests'],request_id:request}}
    db.commit()
    return 'failed'
