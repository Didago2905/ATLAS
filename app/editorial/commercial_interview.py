"""Proposal-only commercial interview, using existing patches and navigation."""
from hashlib import sha256
import json
from uuid import uuid4

from app.editorial import interview
from app.editorial import draft_lifecycle
from app.editorial.candidate_lookup import read_commercial_beer
from app.editorial.models import Interview
from app.editorial.navigation_v22 import (
    NavigationState, CallbackContext, assert_callback, callback_context, correct_proposal, navigate, reconcile_paths,
)
from app.editorial.patches import (
    BEER_FIELDS, PRICE_KEYS, CommercialPatch, apply_commercial_patch, correct_patch_field, patch_intentions,
)
from app.editorial.proposal import ProposedBeer
from app.editorial.proposal_v22 import Proposal22, IdentitySnapshot, assert_identity_current, proposal_issues, assess_readiness

FIELDS = (*BEER_FIELDS, *("prices." + key for key in PRICE_KEYS))
CLEARABLE = frozenset(FIELDS) - {"name", "brewery", "style"}
LABELS = dict(zip(FIELDS, ("Nombre", "Cervecería", "Estilo", "Origen", "Color", "Descripción", "ABV (%)", "IBU",
                          "Taster", "Pinta chica", "Pinta grande", "Jarra chica", "Jarra grande")))
STALE = "Ese botón ya no está vigente. Usa /continuar. No se cambió la propuesta."


def permission(state):
    return "beer.create" if state.history["commercial"]["mode"] == "new" else "beer.edit"


def _load(db, draft):
    state = db.get(Interview, draft.id)
    return state, Proposal22.model_validate(interview.latest(db, draft).payload), NavigationState.model_validate(state.history["navigation"])


def start(db, draft, *, mode, catalog_url=None, quick=False):
    from app.editorial.carta_identity import _store
    state, proposal, nav = _load(db, draft)
    if quick and (mode != "edit" or proposal.beers[0].kind != "existing"):
        raise ValueError("Quick editing requires a confirmed SQL beer")
    if state.history.get("phase") == "commercial":
        return render(db, draft)
    beer = proposal.beers[0]
    if mode == "edit":
        if beer.kind != "existing" or state.history["phase"] != "confirmed":
            raise ValueError("Confirmed identity required")
        baseline = read_commercial_beer(catalog_url, beer.beer_id)
        assert_identity_current(beer, IdentitySnapshot(**{k: baseline[k] for k in ("name", "brewery", "style")}), beer_id=beer.beer_id)
    elif mode == "new":
        baseline = {}
    else:
        raise ValueError("Unsupported mode")
    # JSON-safe bounded private source snapshot; never logged or sent wholesale.
    encoded = json.dumps(baseline, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if len(encoded) > 64 * 1024:
        raise ValueError("Oversized commercial snapshot")
    raw = proposal.model_dump(mode="json")
    raw.update(readiness="incomplete", preparation=None)
    if mode == "new":
        raw["beers"] = [{"kind": "new", "id": str(beer.id)}]
    raw["actions"] = [{"kind": "beer_create" if mode == "new" else "commercial_change", "id": str(uuid4()),
                       "beer_identity_id": str(beer.id)}]
    updated, nav = correct_proposal(proposal, nav, callback_context(nav), Proposal22.model_validate(raw))
    updated = draft_lifecycle.revision_after_history(db, draft, updated)
    nav = reconcile_paths(updated, nav)
    nav = navigate(updated, nav, callback_context(nav), action="correct",
                   target="summary" if quick else f"commercial/{updated.actions[0].id}/{FIELDS[0]}")
    state.history = {**state.history, "phase": "commercial", "navigation": nav.model_dump(mode="json"),
                     "commercial": {"mode": mode, "baseline": baseline, "baseline_sha256": sha256(encoded.encode()).hexdigest(),
                                    "index": 0, "awaiting": False, "review": bool(quick), "quick": bool(quick)}}
    draft.prompt_message_id = None
    _store(db, draft, state, updated)
    return render(db, draft)


def _value(values, path):
    return (values.get("prices") or {}).get(path.split(".")[1]) if path.startswith("prices.") else values.get(path)


def _show(value, limit=80):
    return "sin indicar" if value is None else str(value).replace("\n", " ").replace("\r", " ")[:limit]


def summary(db, draft, *, changes_only=False):
    state, proposal, _ = _load(db, draft)
    data = state.history["commercial"]
    patch = proposal.actions[0].patch
    intents = dict(patch_intentions(patch))
    projected = apply_commercial_patch(data["baseline"], patch, allow_clear=CLEARABLE)
    lines = [f"Propuesta comercial V2.2 · revisión {proposal.revision}",
             "Nueva cerveza · no disponible; sin activación Tap." if data["mode"] == "new" else "Edición de identidad SQL confirmada."]
    shown = 0
    for field in FIELDS:
        intent = intents.get(field)
        if changes_only:
            old, new = _value(data["baseline"], field), _value(projected, field)
            changed = old != new
            if field.startswith("prices."):
                key = field.split(".")[1]
                changed = changed or ((key in (data["baseline"].get("prices") or {})) != (key in (projected.get("prices") or {})))
            if not intent or intent.op not in {"set", "clear"} or not changed:
                continue
        before = _show(_value(data["baseline"], field))
        after = _show(_value(projected, field))
        if intent and intent.op == "set":
            result = f"{before} → {after}"
        elif intent and intent.op == "clear":
            result = f"{before} → borrar"
        elif intent and intent.op == "unknown":
            result = f"sin información; conservar {before}"
        else:
            result = f"conservar {before}"
        lines.append(LABELS[field] + ": " + result)
        shown += 1
    missing = [LABELS[k] for k in ("name", "brewery", "style") if _value(projected, k) is None]
    if changes_only and shown == 0:
        lines.append("No hay cambios efectivos propuestos.")
    elif missing:
        lines.append("Falta: " + ", ".join(missing))
    elif proposal_issues(proposal):
        lines.append("Sin cambios comerciales propuestos." if data["mode"] == "edit" else "Propuesta incompleta.")
    else:
        lines.append("Campos válidos para revisión; esto no es aprobación.")
    lines.append("Guardada solo en Editorial. No se publicó ni activó nada. Los textos largos se abrevian aquí.")
    return "\n".join(lines)


def render(db, draft):
    state, proposal, nav = _load(db, draft)
    data = state.history["commercial"]
    field = FIELDS[data["index"]]

    def button(text, action):
        return [{"text": text, "callback_data": f"b22:{proposal.case_id.hex}:{nav.interaction_version}:{proposal.revision}:{action}"}]

    if data["review"]:
        buttons = [button(("Editar: " if data.get("quick") else "Corregir: ") + LABELS[key], "e" + str(i)) for i, key in enumerate(FIELDS)]
        buttons.insert(0, button("Finalizar y conservar", "f"))
        if data.get("quick"):
            buttons.append(button("Ver solo cambios" if data.get("full_summary") else "Ver resumen completo", "h"))
        buttons.append(button("Cancelar caso", "x"))
        return summary(db, draft, changes_only=bool(data.get("quick") and not data.get("full_summary"))), {"inline_keyboard": buttons}, None, False
    if data["awaiting"]:
        return (LABELS[field] + ": responde a este mensaje con el nuevo valor. "
                "Números sin unidades ni separadores de miles; se acepta coma decimal. "
                "Usa /corregir para volver al resumen o /cancelar para salir.",
                {"force_reply": True, "input_field_placeholder": LABELS[field]}, None, True)
    projected = apply_commercial_patch(data["baseline"], proposal.actions[0].patch, allow_clear=CLEARABLE)
    intent = dict(patch_intentions(proposal.actions[0].patch)).get(field)
    changed = intent and intent.op in {"set", "clear"}
    buttons = [button("Conservar propuesta" if changed else "Conservar actual / omitir", "k"),
               button("Escribir nuevo valor", "s"), button("Sin información (no cambia)", "u")]
    if field in CLEARABLE:
        buttons.append(button("Borrar valor", "c"))
    if changed:
        buttons.append(button("Descartar cambio; volver al original", "d"))
    buttons.extend([button("Atrás", "b"), button("Ver resumen", "v"), button("Cancelar caso", "x")])
    title = "Edición rápida · " + LABELS[field] if data.get("quick") else f"{data['index'] + 1}/{len(FIELDS)} · {LABELS[field]}"
    return (f"{title}\nValor propuesto: {_show(_value(projected, field), 160)}",
            {"inline_keyboard": buttons}, None, False)


def transition(db, draft, payload):
    from app.editorial.carta_identity import _store
    state, proposal, nav = _load(db, draft)
    data = dict(state.history["commercial"])
    field = FIELDS[data["index"]]
    patch = proposal.actions[0].patch
    answer = None
    callback = payload.get("callback", "")
    if payload.get("command") == "/cancelar":
        draft_lifecycle.close(db, draft, status="cancelled")
        return "Caso comercial cerrado. Sus propuestas se conservan; no se publicó nada.", None, None, False
    if payload.get("command") in {"/vista", "/corregir"}:
        data.update(review=True, awaiting=False)
    elif payload.get("command") == "/continuar":
        return render(db, draft)
    elif callback:
        parts = callback.split(":")
        try:
            if len(parts) != 5 or parts[0] != "b22" or state.revision != proposal.revision:
                raise ValueError()
            assert_callback(proposal, nav, CallbackContext(case_id=parts[1], interaction_version=int(parts[2]), content_revision=int(parts[3])))
        except (ValueError, TypeError):
            return STALE, None, None, False
        action = parts[4]
        if action == "x":
            draft_lifecycle.close(db, draft, status="cancelled")
            return "Caso comercial cerrado. Sus propuestas se conservan; no se publicó nada.", None, None, False
        if action == "f" and data["review"]:
            draft_lifecycle.close(db, draft, status="saved")
            return "Propuesta conservada como borrador sin aprobación. No se publicó nada. Usa /borradores22 para recuperarla o /nueva22 para iniciar otra.", None, None, False
        if action == "h" and data["review"] and data.get("quick"):
            data['full_summary'] = not data.get('full_summary', False)
        elif action.startswith("e") and action[1:].isdecimal() and 0 <= int(action[1:]) < len(FIELDS) and data["review"]:
            data.update(index=int(action[1:]), review=False, awaiting=False, full_summary=False)
        elif data["review"] or data["awaiting"]:
            return STALE, None, None, False
        elif action == "s":
            data["awaiting"] = True
        elif action == "b":
            if data.get("quick"):
                data["review"] = True
            else:
                data["index"] = max(0, data["index"] - 1)
        elif action == "v":
            data["review"] = True
        elif action in {"k", "u", "c"}:
            answer = {"op": {"k": "keep", "u": "unknown", "c": "clear"}[action]}
        elif action == "d":
            raw = patch.model_dump(mode="json")
            if field.startswith("prices."):
                raw["prices"].pop(field.split(".")[1], None)
            else:
                raw.pop(field, None)
            patch = CommercialPatch.model_validate(raw)
            if data.get("quick"):
                data.update(review=True, full_summary=False)
        else:
            return STALE, None, None, False
    elif data["awaiting"] and payload.get("text") and draft.prompt_message_id is not None and payload.get("reply_to") == draft.prompt_message_id:
        value = payload["text"].strip()
        if field in {"abv", "ibu"} or field.startswith("prices."):
            try:
                value = float(value.replace(",", "."))
            except ValueError:
                return "Usa un número válido. Responde de nuevo al mismo mensaje.", None, None, False
        answer = {"op": "set", "value": value}
    else:
        return "Usa los botones o responde al mensaje que pide el valor. /continuar retoma; /cancelar cierra.", None, None, False
    if answer:
        try:
            patch = correct_patch_field(patch, field, answer, allow_clear=CLEARABLE)
            if answer["op"] in {"keep", "unknown"} and field not in dict(patch_intentions(patch)):
                raw = patch.model_dump(mode="json")
                if field.startswith("prices."):
                    raw["prices"][field.split(".")[1]] = answer
                else:
                    raw[field] = answer
                patch = CommercialPatch.model_validate(raw)
        except ValueError:
            return "Valor inválido. Nombre/cervecería: 1–255; estilo: 1–100; origen: 1–255; color: 1–80; descripción: 1–800. ABV: 0–100; IBU: 0–2000; precios: 0–1000000, finitos. No se borran campos obligatorios.", None, None, False
        data.update(index=data["index"] if data.get("quick") else min(data["index"] + 1, len(FIELDS) - 1), awaiting=False,
                    review=bool(data.get("quick") or data["index"] == len(FIELDS) - 1), full_summary=False)
    raw = proposal.model_dump(mode="json")
    raw.update(readiness="incomplete", preparation=None)
    raw["actions"][0]["patch"] = patch.model_dump(mode="json")
    if data["mode"] == "new":
        raw["beers"][0]["candidate"] = ProposedBeer.model_validate(apply_commercial_patch({}, patch, allow_clear=CLEARABLE)).model_dump(mode="json")
    updated, next_nav = correct_proposal(proposal, nav, callback_context(nav), Proposal22.model_validate(raw))
    if updated.revision != proposal.revision:
        updated = draft_lifecycle.revision_after_history(db, draft, updated)
        next_nav = reconcile_paths(updated, next_nav)
    updated = assess_readiness(updated)
    target = "summary" if data["review"] else f"commercial/{updated.actions[0].id}/{FIELDS[data['index']]}"
    next_nav = navigate(updated, next_nav, callback_context(next_nav), action="correct", target=target)
    state.history = {**state.history, "commercial": data, "navigation": next_nav.model_dump(mode="json")}
    draft.prompt_message_id = None
    if updated.revision != proposal.revision:
        _store(db, draft, state, updated)
    return render(db, draft)
