"""Minimal Carta identity interview. Only the candidate reader touches the catalog."""
from dataclasses import asdict
from uuid import uuid4
from sqlalchemy import select

from app.editorial import interview
from app.editorial.draft_lifecycle import INACTIVE, archive, close
from app.editorial.candidate_lookup import lookup_beers, CandidateLookupError
from app.editorial.models import Draft, Interview, ProposalRevision, Reply
from app.editorial.navigation_v22 import NavigationState, CallbackContext, assert_callback, start_navigation, reconcile_paths
from app.editorial.proposal_v22 import Proposal22, IdentitySnapshot, identity_fingerprint

STALE = "Ese botón ya no está vigente. Usa /continuar para ver el estado actual."


def owns(db, draft):
    state = db.get(Interview, draft.id) if draft else None
    return bool(state and state.step == "v2.2" and isinstance(state.history, dict)
                and state.history.get("flow") == "carta_identity")


def _store(db, draft, state, proposal):
    state.revision = proposal.revision
    db.add(ProposalRevision(draft_id=draft.id, revision=proposal.revision,
                           payload=proposal.model_dump(mode="json")))
    db.flush()


def begin(db, draft, chat, user):
    if draft and draft.state not in INACTIVE:
        return draft, ("Ya tienes un borrador activo. Usa /continuar o /cancelar antes de iniciar Carta V2.2.", None, None, False)
    if draft is None:
        draft = Draft(id=uuid4().hex, chat_id=chat, user_id=user)
        db.add(draft)
        db.flush()
    previous = interview.latest(db, draft, include_inactive=True)
    revision = previous.revision + 1 if previous else 1
    proposal = Proposal22(schema_version="2.2", case_id=uuid4(), intake_origin="data_only", revision=revision,
                         beers=({"kind": "unresolved", "id": uuid4()},),
                         change_summary="Inicio de caso Carta: solo identificación")
    state = db.get(Interview, draft.id)
    if state and isinstance(state.history, dict) and state.history.get('phase') == 'commercial' and draft.state in INACTIVE:
        close(db, draft, status=draft.state)
    saved = archive(state)
    if state is None:
        state = Interview(id=draft.id, step="v2.2", revision=revision, history={})
        db.add(state)
    state.step = "v2.2"
    state.history = {"flow": "carta_identity", "operation": "carta", "phase": "name",
                     "navigation": start_navigation(proposal).model_dump(mode="json"), "candidates": [], "saved_cases": saved}
    draft.state, draft.prompt_message_id = "draft", None
    _store(db, draft, state, proposal)
    return draft, render(db, draft)


def render(db, draft):
    if draft.state == "saved":
        return "Propuesta conservada como borrador sin aprobación. Usa /borradores22 para recuperarla.", None, None, False
    if draft.state == "cancelled":
        return "Caso Carta cerrado. No se publicó nada.", None, None, False
    state = db.get(Interview, draft.id)
    if state.history.get("phase") == "commercial":
        from app.editorial.commercial_interview import render as commercial_render
        return commercial_render(db, draft)
    proposal = Proposal22.model_validate(interview.latest(db, draft).payload)
    data = state.history
    nav = NavigationState.model_validate(data["navigation"])

    def button(label, action):
        token = f"c22:{proposal.case_id.hex}:{nav.interaction_version}:{proposal.revision}:{action}"
        return [{"text": label, "callback_data": token}]

    if data["phase"] == "confirmed":
        beer = proposal.beers[0]
        return (f"Carta · identidad confirmada\n{beer.snapshot.name} · {beer.snapshot.brewery}\n"
                f"{beer.snapshot.style} · ID {beer.beer_id}\n"
                "Solo se guardó la identidad. No se aprobó ni publicó ningún cambio.", None, None, False)
    buttons = []
    if data["phase"] == "choose":
        lines = ["Carta · confirma una cerveza:"]
        for index, candidate in enumerate(data["candidates"]):
            availability = {True: "disponible", False: "no disponible", None: "disponibilidad sin indicar"}[candidate["is_available"]]
            lines.append(f"{index + 1}. {candidate['name']} · {candidate['brewery']} · {candidate['style']} · {availability}")
            buttons.append(button(f"Confirmar {index + 1}", str(index)))
        text, prompt = "\n".join(lines) + "\nConfirmar no autoriza publicación.", False
        buttons.append(button("Buscar de nuevo", "r"))
    else:
        # ForceReply cannot be combined with an inline keyboard. /cancelar stays available.
        return ("Carta V2.2 · ¿Cómo se llama la cerveza? Responde a este mensaje con su nombre completo. "
                "Usa /cancelar para salir.", {"force_reply": True, "input_field_placeholder": "Nombre de cerveza"}, None, True)
    buttons.append(button("Cancelar", "x"))
    return text, {"inline_keyboard": buttons}, None, prompt


def transition(db, draft, payload, catalog_url, uid):
    state = db.get(Interview, draft.id)
    if state.history.get("phase") == "commercial":
        from app.editorial.commercial_interview import transition as commercial_transition
        return commercial_transition(db, draft, payload)
    data = dict(state.history)
    proposal = Proposal22.model_validate(interview.latest(db, draft).payload)
    nav = NavigationState.model_validate(data["navigation"])
    if draft.state == "cancelled":
        return STALE, None, None, False
    if payload.get("command") == "/cancelar":
        draft.state, draft.prompt_message_id = "cancelled", None
        return "Caso Carta cerrado. No se publicó nada.", None, None, False
    if payload.get("command") in {"/continuar", "/vista"}:
        return render(db, draft)
    callback = payload.get("callback", "")
    if callback:
        parts = callback.split(":")
        if len(parts) != 5 or parts[0] != "c22" or parts[1] != proposal.case_id.hex \
                or parts[2] != str(nav.interaction_version) or parts[3] != str(proposal.revision) \
                or state.revision != proposal.revision or nav.content_revision != proposal.revision \
                or data["phase"] != "choose":
            return STALE, None, None, False
        try:
            assert_callback(proposal, nav, CallbackContext(case_id=parts[1], interaction_version=int(parts[2]),
                                                          content_revision=int(parts[3])))
        except ValueError:
            return STALE, None, None, False
        action = parts[4]
        if action == "x":
            draft.state, draft.prompt_message_id = "cancelled", None
            return "Caso Carta cerrado. No se publicó nada.", None, None, False
        if action == "r":
            data.update(phase="name", candidates=[])
        elif action in {"0", "1", "2"} and int(action) < len(data["candidates"]):
            offered = data["candidates"][int(action)]
            try:
                current = lookup_beers(catalog_url, name=offered["name"], beer_id=offered["beer_id"],
                                       limit=1, include_deleted=False)
                if not current or any(asdict(current[0])[key] != value for key, value in offered.items() if key != "match"):
                    raise CandidateLookupError("Changed identity")
                snapshot = IdentitySnapshot(name=current[0].name, brewery=current[0].brewery, style=current[0].style)
            except (ValueError, OSError):
                # Invalidate the offered set; require a fresh search and human confirmation.
                data.update(phase="name", candidates=[])
                data["navigation"] = reconcile_paths(proposal, nav).model_dump(mode="json")
                state.history, draft.prompt_message_id = data, None
                text, markup, asset, prompt = render(db, draft)
                return "El registro cambió o no se pudo verificar. Busca de nuevo.\n" + text, markup, asset, prompt
            raw = proposal.model_dump(mode="json")
            raw.update(revision=proposal.revision + 1, change_summary="Identidad de cerveza confirmada por el operador")
            raw["beers"] = [{"kind": "existing", "id": str(proposal.beers[0].id), "beer_id": current[0].beer_id,
                             "snapshot": snapshot.model_dump(mode="json"),
                             "expected_fingerprint": identity_fingerprint(snapshot, beer_id=current[0].beer_id),
                             "confirmation": {"method": "human_confirmation", "reference": f"telegram-update:{uid}"}}]
            proposal = Proposal22.model_validate(raw)
            _store(db, draft, state, proposal)
            data.update(phase="confirmed", candidates=[])
        else:
            return STALE, None, None, False
    elif data["phase"] == "confirmed":
        return render(db, draft)
    elif data["phase"] == "name" and payload.get("text") and draft.prompt_message_id is not None \
            and payload.get("reply_to") == draft.prompt_message_id:
        try:
            results = lookup_beers(catalog_url, name=payload["text"], limit=3, include_deleted=False)
            # Incomplete catalog identities cannot satisfy the existing V2.2 identity contract.
            for result in results:
                IdentitySnapshot(name=result.name, brewery=result.brewery, style=result.style)
        except (ValueError, OSError):
            return "No se pudo consultar el catálogo. Responde de nuevo o usa /cancelar.", None, None, False
        data.update(phase="choose" if results else "name", candidates=[asdict(r) for r in results])
    else:
        if data["phase"] == "choose":
            return "Elige una cerveza con los botones. /continuar muestra las opciones y /cancelar cierra el caso.", None, None, False
        return "Usa /continuar para ver el caso o responde al mensaje que pide el nombre. /cancelar cierra el caso.", None, None, False
    data["navigation"] = reconcile_paths(proposal, nav).model_dump(mode="json")
    state.history, draft.prompt_message_id = data, None
    result = render(db, draft)
    if data["phase"] == "name" and not callback:
        return ("No encontré coincidencias. Prueba otro nombre.\n" + result[0], *result[1:])
    return result


def obsolete_keyboards(db, draft):
    """Only known, sent bot messages for this Carta case; no message/history deletion."""
    state = db.get(Interview, draft.id)
    if draft.state not in INACTIVE and state.history["phase"] != "confirmed":
        return []
    case = state.history["navigation"]["case_id"].replace("-", "")
    prefixes = ("c22:" + case + ":", "b22:" + case + ":")
    messages = []
    for reply in db.scalars(select(Reply).where(Reply.draft_id == draft.id, Reply.chat_id == draft.chat_id, Reply.state == "sent",
                                               Reply.message_id.is_not(None), Reply.markup.is_not(None))):
        if not isinstance(reply.markup, dict):
            continue  # SQLite JSON null is not SQL NULL; ordinary text replies have no keyboard.
        rows = reply.markup.get("inline_keyboard", [])
        buttons = [button for row in rows for button in row]
        if buttons and all(button.get("callback_data", "").startswith(prefixes) for button in buttons):
            messages.append(reply.message_id)
    return messages
