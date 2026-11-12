"""Saved commercial contexts in existing Interview JSON; proposals stay immutable."""
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select

from app.editorial.models import Interview, ProposalRevision
from app.editorial.navigation_v22 import NavigationState, reconcile_paths, navigate, callback_context
from app.editorial.proposal_v22 import Proposal22

INACTIVE = frozenset({"cancelled", "saved"})


def archive(state):
    return deepcopy(state.history.get("saved_cases", {})) if state and isinstance(state.history, dict) else {}


def execution_requests(state):
    return deepcopy(state.history.get('execution_requests',{})) if state and isinstance(state.history,dict) else {}


def legacy_steps(state):
    return state.history.get("steps", []) if isinstance(state.history, dict) else state.history


def set_legacy_steps(state, steps):
    saved = archive(state)
    requests = execution_requests(state)
    state.history = {"flow": "legacy_with_saved", "steps": steps, "saved_cases": saved,
                     "execution_requests":requests} if saved or requests else steps


def case_latest(db, draft_id, case_id):
    return db.scalar(select(ProposalRevision).where(ProposalRevision.draft_id == draft_id,
                     ProposalRevision.payload['case_id'].as_string() == str(UUID(str(case_id))))
                     .order_by(ProposalRevision.revision.desc()).limit(1))


def revision_after_history(db, draft, proposal):
    """Old cases can be resumed after newer cases: keep the global unique sequence."""
    latest = db.scalar(select(ProposalRevision).where(ProposalRevision.draft_id == draft.id)
                       .order_by(ProposalRevision.revision.desc()).limit(1))
    if latest and proposal.revision <= latest.revision:
        raw = proposal.model_dump(mode="json")
        raw.update(revision=latest.revision + 1, readiness="incomplete", preparation=None)
        return Proposal22.model_validate(raw)
    return proposal


def close(db, draft, *, status):
    state = db.get(Interview, draft.id)
    case_id = state.history['navigation']['case_id']
    proposal = Proposal22.model_validate(case_latest(db, draft.id, case_id).payload)
    nav = reconcile_paths(proposal, NavigationState.model_validate(state.history['navigation']))
    data = {**state.history, 'navigation': nav.model_dump(mode='json')}
    saved = archive(state)
    context = deepcopy(data)
    context.pop('saved_cases', None)
    context.pop('execution_requests', None)
    saved[str(proposal.case_id)] = {'context': context, 'revision': proposal.revision, 'status': status}
    state.history = {**data, 'saved_cases': saved}
    draft.state, draft.prompt_message_id = status, None


def listing(db, draft, auth, *, offset=0):
    state = db.get(Interview, draft.id) if draft else None
    cases = list(archive(state).items())[::-1]
    buttons, lines = [], ['Tus borradores comerciales V2.2 conservados (sin aprobación):']
    for case_id, saved in cases[offset:offset + 10]:
        mode = saved['context']['commercial']['mode']
        if not auth.allows(draft.chat_id, draft.user_id, 'beer.create' if mode == 'new' else 'beer.edit'):
            continue
        row = case_latest(db, draft.id, case_id)
        if row is None:
            continue
        proposal = Proposal22.model_validate(row.payload)
        beer = proposal.beers[0]
        name = beer.candidate.name if beer.kind == 'new' else beer.snapshot.name
        label = (name or 'Sin nombre').replace('\n', ' ').replace('\r', ' ')[:60]
        lines.append(f'{len(buttons) + 1}. {label} · revisión {proposal.revision}')
        buttons.append([{'text': f'Reabrir {len(buttons) + 1}: {label[:35]}',
                         'callback_data': f'r22:{proposal.case_id.hex}:{proposal.revision}'}])
    if offset:
        buttons.append([{'text':'Anteriores', 'callback_data':f'r22:list:{max(0,offset-10)}'}])
    if offset + 10 < len(cases):
        buttons.append([{'text':'Más borradores', 'callback_data':f'r22:list:{offset+10}'}])
    if len(lines) == 1:
        lines.append('No hay borradores conservados accesibles en esta página.')
    return '\n'.join(lines), {'inline_keyboard': buttons} if buttons else None, None, False


def reopen(db, draft, token, auth):
    if draft is None:
        return 'Ese borrador no está disponible para este operador.', None, None, False
    if draft.state not in INACTIVE:
        return 'Ya tienes un borrador activo. Finalízalo o usa /cancelar antes de reabrir otro.', None, None, False
    _, key, revision = token.split(':')
    state = db.get(Interview, draft.id)
    saved_cases = archive(state)
    case_id = str(UUID(key))
    saved = saved_cases.get(case_id)
    if saved is None:
        return 'Ese borrador no está disponible para este operador.', None, None, False
    row = case_latest(db, draft.id, case_id)
    if row is None or row.revision != int(revision):
        return 'La lista ya no está vigente. Usa /borradores22.', None, None, False
    context = deepcopy(saved['context'])
    required = 'beer.create' if context['commercial']['mode'] == 'new' else 'beer.edit'
    if not auth.allows(draft.chat_id, draft.user_id, required):
        return 'No tienes permiso para reabrir esta propuesta.', None, None, False
    proposal = Proposal22.model_validate(row.payload)
    nav = reconcile_paths(proposal, NavigationState.model_validate(context['navigation']))
    nav = navigate(proposal, nav, callback_context(nav), action='summary')
    context['commercial'].update(review=True, awaiting=False)
    context['navigation'] = nav.model_dump(mode='json')
    state.step, state.revision = 'v2.2', proposal.revision
    state.history = {**context, 'saved_cases': saved_cases, 'execution_requests':execution_requests(state)}
    draft.state, draft.prompt_message_id = 'draft', None
    from app.editorial.commercial_interview import render
    return render(db, draft)
