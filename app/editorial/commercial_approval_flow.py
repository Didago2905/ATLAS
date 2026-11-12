"""Authenticated review/approval UI. SQL execution is deliberately NEVER invoked."""
from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4, uuid5, UUID, NAMESPACE_URL

from app.editorial import draft_lifecycle
from app.editorial.models import Interview
from app.editorial.commercial_preparation import prepare_commercial_update
from app.editorial.commercial_applicator import CommercialApproval, approval_digest, PERMISSION
from app.editorial.candidate_lookup import _sqlite_file

DISABLED = 'La ejecución SQL está deshabilitada en este flujo. Esta interfaz no aplica cambios.'
STALE = 'La revisión ya no está vigente. Usa /aplicar22 para revisar de nuevo.'


def _notice(enabled):
    if enabled == 'production':
        return 'Ejecución comercial habilitada para destinos expresamente autorizados.'
    return 'Solo este entorno temporal allowlisted permite ejecución post-commit. Producción sigue bloqueada.' if enabled else DISABLED


def _allowed(auth, payload):
    return auth.allows(payload['chat'],payload['user'],'beer.edit') and auth.allows(payload['chat'],payload['user'],PERMISSION)


def _binding(url):
    return sha256(str(_sqlite_file(url)).encode()).hexdigest()


def _saved(db, draft, case_id, revision):
    if draft is None or draft.state not in draft_lifecycle.INACTIVE:
        raise ValueError()
    state = db.get(Interview,draft.id)
    entry = draft_lifecycle.archive(state).get(str(UUID(case_id)))
    if not entry or entry['status'] != 'saved' or entry['context']['commercial']['mode'] != 'edit':
        raise ValueError()
    row = draft_lifecycle.case_latest(db,draft.id,case_id)
    if not row or row.revision != revision:
        raise ValueError()
    return row.payload, entry['context']


def _pages(prepared):
    title = 'Conflictos: valores originales → SQL actual' if prepared.status == 'conflict' else 'Cambios: SQL actual → propuesta'
    diffs = prepared.conflicts if prepared.status == 'conflict' else prepared.changes
    text = title + '\n'
    for diff in diffs:
        text += json.dumps(list(diff.path),ensure_ascii=False) + '\n'
        text += 'Antes: ' + (json.dumps(diff.before,ensure_ascii=False) if diff.before_present else '(clave ausente)') + '\n'
        text += 'Después: ' + (json.dumps(diff.after,ensure_ascii=False) if diff.after_present else '(clave ausente)') + '\n\n'
    if not diffs:
        text += 'No hay cambios efectivos.'
    # No truncation: long before/after values are split across sequential pages.
    return [text[i:i+1400] for i in range(0,len(text),1400)]


def _store(state, review):
    state.history = {**state.history,'application_review':review}


def _render(review):
    page = review['page']
    header = f"Revisión SQL · cerveza #{review['beer_id']} · r{review['revision']}\nCaso: {review['case_id']}\nPágina {page+1}/{len(review['pages'])}\n"
    buttons = []
    if page + 1 < len(review['pages']):
        buttons.append([{'text':'Siguiente página','callback_data':f"a22:{review['nonce']}:p{page+1}"}])
    elif review['status'] == 'reviewed':
        header += ('Confirma este contenido exacto; se solicitará su aplicación.\n' if review.get('isolated_execution_enabled')
                   else 'Confirma la autorización de este contenido exacto; NO se ejecutará SQL.\n')
        buttons.append([{'text':'Confirmar autorización','callback_data':f"a22:{review['nonce']}:confirm"}])
    else:
        header += 'No puede autorizarse: resuelve conflictos o cambios vacíos primero.\n'
    return header + review['pages'][page] + '\n' + _notice(review.get('isolated_execution_enabled',False)), {'inline_keyboard':buttons} if buttons else None, None, False


def _receipt(url, review, *, notice=DISABLED, request=None):
    """Private, bounded, read-only receipt lookup. Never creates a receipt table."""
    application_id = str(uuid5(NAMESPACE_URL,'atlas:commercial:' + review['case_id'] + ':' + str(review['revision'])))
    with closing(sqlite3.connect(_sqlite_file(url).as_uri()+'?mode=ro',uri=True,timeout=15)) as connection:
        connection.execute('PRAGMA query_only=ON')
        def authorize(action,table,column,database,trigger):
            if action == sqlite3.SQLITE_READ:
                return sqlite3.SQLITE_OK if table == 'editorial_commercial_applications' else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_FUNCTION) else sqlite3.SQLITE_DENY
        connection.set_authorizer(authorize)
        row = connection.execute('SELECT application_id,case_id,proposal_revision,beer_id,request_sha256,authorization_ref,status,applied_at,action_id,changes '
                                 'FROM editorial_commercial_applications WHERE application_id=?',(application_id,)).fetchone()
    if not row or row[1:5] != (review['case_id'],review['revision'],review['beer_id'],review['request_sha256']) \
            or row[5] != review['approval']['reference'] or row[6] != 'applied':
        return 'No hay recibo de aplicación confirmado para esta autorización. ' + notice
    if request:
        from datetime import datetime
        from app.editorial.commercial_execution import _binding, _json
        if request.get('binding_sha256')!=_binding(request) or row[8]!=request['action_id'] \
                or _json(json.loads(row[9]))!=_json(request['expected_changes']) \
                or not datetime.fromisoformat(request['approved_at'])<=datetime.fromisoformat(row[7])<=datetime.fromisoformat(request['expires_at']):
            return 'El recibo no coincide con la solicitud. No se afirma ninguna aplicación.'
    return f'Recibo persistido\nID: {row[0]}\nCerveza #{row[3]} · revisión {row[2]}\nEstado: {row[6]}\nUTC: {row[7]}'


def handle(db, draft, payload, auth, catalog_url, *, update_id=None, isolated_execution_enabled=False, production_activation=None):
    if not _allowed(auth,payload):
        return 'No tienes permiso para autorizar aplicaciones comerciales.', None, None, False
    if draft is None or draft.chat_id != payload['chat'] or draft.user_id != payload['user']:
        return 'No hay propuestas propias disponibles para esta operación.', None, None, False
    state = db.get(Interview,draft.id)
    if state is None or not isinstance(state.history,dict):
        return 'No hay propuestas comerciales conservadas.', None, None, False
    command, callback = payload.get('command'), payload.get('callback','')
    if command == '/aplicar22':
        buttons = []
        for case_id, entry in list(draft_lifecycle.archive(state).items())[::-1]:
            if entry['status'] != 'saved' or entry['context']['commercial']['mode'] != 'edit':
                continue
            row = draft_lifecycle.case_latest(db,draft.id,case_id)
            if row:
                beer = row.payload['beers'][0]
                label = beer.get('snapshot',{}).get('name','Cerveza').replace('\n',' ').replace('\r',' ')[:40]
                buttons.append([{'text':'Revisar: '+label,'callback_data':f'a22:{UUID(case_id).hex}:{row.revision}:review'}])
            if len(buttons) == 10:
                break
        return 'Selecciona una propuesta propia conservada. Revisar no autoriza ni aplica. '+_notice(isolated_execution_enabled), {'inline_keyboard':buttons} if buttons else None, None, False
    try:
        if callback.endswith(':review'):
            _, case_id, revision, _ = callback.split(':')
            proposal, context = _saved(db,draft,case_id,int(revision))
            prepared = prepare_commercial_update(catalog_url,proposal=proposal,interview_context=context)
            review = dict(nonce=uuid4().hex,chat=payload['chat'],operator=payload['user'],case_id=str(prepared.case_id),
                          revision=prepared.proposal_revision,beer_id=prepared.beer_id,
                          request_sha256=approval_digest(proposal,context),current_sha256=prepared.current_sha256,
                          catalog_binding=_binding(catalog_url),pages=_pages(prepared),page=0,
                          status='reviewed' if prepared.status == 'prepared' else 'blocked',isolated_execution_enabled=isolated_execution_enabled,
                          production_activation=production_activation)
            _store(state,review)
            return _render(review)
        review = deepcopy(state.history.get('application_review',{}))
        review['isolated_execution_enabled'] = isolated_execution_enabled
        if review.get('chat') != payload['chat'] or review.get('operator') != payload['user'] or review.get('catalog_binding') != _binding(catalog_url):
            raise ValueError()
        if command == '/recibo22':
            if not review.get('approval'):
                return 'Primero debe existir una autorización confirmada. '+DISABLED,None,None,False
            try:
                request = state.history.get('execution_requests',{}).get(review.get('request_id'),{})
                status = 'Estado de solicitud: '+request['state']+'. ' if request and request['state']!='applied' else ''
                return status+_receipt(catalog_url,review,notice=_notice(isolated_execution_enabled),request=request),None,None,False
            except (ValueError,OSError,sqlite3.Error):
                return 'No se pudo verificar un recibo persistido. No se afirma ninguna aplicación.',None,None,False
        _, nonce, action = callback.split(':')
        if review.get('production_activation') != production_activation:
            raise ValueError()
        if nonce != review['nonce']:
            raise ValueError()
        proposal, context = _saved(db,draft,review['case_id'],review['revision'])
        if approval_digest(proposal,context) != review['request_sha256']:
            raise ValueError()
        if action.startswith('p') and action[1:].isdecimal() and int(action[1:]) == review['page']+1 and int(action[1:]) < len(review['pages']):
            review['page'] += 1
            _store(state,review)
            return _render(review)
        if action != 'confirm' or review['page'] != len(review['pages'])-1:
            raise ValueError()
        if review['status'] == 'confirmed_execution_disabled':
            return 'Autorización ya registrada. '+_notice(isolated_execution_enabled),None,None,False
        if review['status'] != 'reviewed':
            raise ValueError()
        current = prepare_commercial_update(catalog_url,proposal=proposal,interview_context=context)
        if current.status != 'prepared' or current.current_sha256 != review['current_sha256']:
            review.update(status='blocked',pages=_pages(current),page=0)
            _store(state,review)
            result = _render(review)
            return ('SQL cambió desde la revisión.\n'+result[0], *result[1:])
        approval = CommercialApproval(reference=uuid4(),case_id=review['case_id'],revision=review['revision'],
                                      request_sha256=review['request_sha256'],confirmed=True)
        review.update(status='confirmed_execution_disabled',approval=approval.model_dump(mode='json'))
        _store(state,review)
        from app.editorial.commercial_execution import enqueue
        request_id = enqueue(state,draft,review,current,update_id=update_id,production_activation=production_activation)
        review['request_id'] = request_id
        _store(state,review)
        return f'Autorización explícita registrada; solicitud pendiente. ID: {request_id}. Aprobado no significa aplicado. '+_notice(isolated_execution_enabled)+' /recibo22 verifica el recibo.',None,None,False
    except (ValueError,KeyError,TypeError,AttributeError,OSError):
        return STALE,None,None,False
