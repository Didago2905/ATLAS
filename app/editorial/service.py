"""Finite draft conversation. No imports of Beer, live engine or publication APIs."""
from datetime import datetime, timezone
import re
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.editorial.models import Cursor, Update, Asset, Draft, Version, Reply, Interview
from app.editorial import interview, carta_identity, commercial_interview
from app.editorial import draft_lifecycle
from app.editorial import commercial_approval_flow
from app.editorial.draft_lifecycle import INACTIVE
from app.editorial.proposal import Proposal, validate_proposal
from app.editorial.telegram import DownloadLimit, TransportError
from app.core.bot_observability import event

OPERATIONS = {
    "new": ("Nueva cerveza", "beer.create"),
    "art": ("Arte para una cerveza existente", "artwork.submit"),
    "fix": ("Corregir información de una cerveza", "beer.edit"),
    "board": ("Tabla del Tap List para el Museo", "artwork.submit"),
    "event": ("Evento o promoción (preparación)", "event.prepare"),
}
PROMPT = ("Responde a este mensaje con una sola imagen. Preferimos un documento para conservar la calidad. "
          "También puedes enviar una foto; se identificará como comprimida por Telegram. "
          "El borrador no publica ni cambia el catálogo.")


def integer(value, positive=False):
    return type(value) is int and -(2**63) < value < 2**63 and (not positive or value > 0)


def project_update(raw, auth):
    """Persist only supported inputs from authorized humans; never whole group updates."""
    if not isinstance(raw, dict) or not integer(raw.get("update_id"), True):
        raise ValueError("Invalid update envelope")
    callback = raw.get("callback_query")
    message = callback.get("message") if isinstance(callback, dict) else raw.get("message")
    if not isinstance(message, dict):
        return {"ignore": True}
    actor = callback.get("from") if isinstance(callback, dict) else message.get("from")
    chat = message.get("chat")
    if not isinstance(actor, dict) or actor.get("is_bot") is not False or not isinstance(chat, dict) \
            or chat.get("type") not in {"group", "supergroup"} or message.get("sender_chat") \
            or not auth.allows(chat.get("id"), actor.get("id")):
        return {"ignore": True}
    value = {"chat": chat["id"], "user": actor["id"]}
    if isinstance(callback, dict):
        data = callback.get("data")
        if not isinstance(data, str) or not re.fullmatch(r"(?:(?:op|start):[a-f0-9]{32}:[0-9]{1,9}:(?:new|art|fix|board|event)|i:[a-f0-9]{32}:[0-9]{1,9}:(?:[0-9]{1,2}|back|skip|summary|edit|resume)|c22:[a-f0-9]{32}:[0-9]{1,9}:[0-9]{1,9}:(?:[0-2]|r|x)|b22:[a-f0-9]{32}:[0-9]{1,9}:[0-9]{1,9}:(?:[kscubvdxfh]|e(?:[0-9]|1[0-2]))|r22:(?:[a-f0-9]{32}:[0-9]{1,9}|list:[0-9]{1,6})|a22:(?:[a-f0-9]{32}:[0-9]{1,9}:review|[a-f0-9]{32}:(?:confirm|p[0-9]{1,3})))", data):
            return {"ignore": True}
        value["callback"] = data
        callback_id = callback.get("id")
        if isinstance(callback_id, str) and 0 < len(callback_id) <= 128:
            value["callback_id"] = callback_id
        return value
    if any(message.get(key) for key in ("forward_origin", "forward_date", "via_bot")):
        value["invalid_attachment"] = "Envía el archivo directamente como respuesta al bot, sin reenviarlo. Tu borrador sigue aquí."
        return value
    text = message.get("text", "")
    if isinstance(text,str) and (recovery := re.fullmatch(r'/recuperar22(?:@[A-Za-z0-9_]{5,32})? ([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',text.strip())):
        value.update(command='/recuperar22',request_id=recovery.group(1))
        return value
    if isinstance(text, str) and re.fullmatch(r"/(?:obra|vista|cancelar|entrevista|continuar|resumen|corregir|carta22|nueva22|editar22|rapido22|borradores22|aplicar22|recibo22)(?:@[A-Za-z0-9_]{5,32})?", text.strip()):
        value["command"] = text.strip().split("@")[0]
        return value
    reply = message.get("reply_to_message")
    if isinstance(reply, dict) and integer(reply.get("message_id"), True):
        value["reply_to"] = reply["message_id"]
        if isinstance(text, str) and 0 < len(text) <= 800:
            value["text"] = text
    if message.get("media_group_id"):
        value["invalid_attachment"] = "Recibí un álbum. Responde con una sola imagen para elegir la obra; tu borrador sigue aquí."
        return value
    document, photos = message.get("document"), message.get("photo")
    if document and photos:
        value["invalid_attachment"] = "Envía una sola imagen como respuesta al bot."
        return value
    photo = isinstance(photos, list) and 0 < len(photos) <= 20
    if photo:
        photos = [p for p in photos if isinstance(p, dict) and integer(p.get("width"), True) and integer(p.get("height"), True)]
        document = max(photos, key=lambda p: p["width"] * p["height"]) if photos else None
    if isinstance(document, dict):
        file_id = document.get("file_id")
        if isinstance(file_id, str) and 0 < len(file_id) <= 512:
            value.update(file_id=file_id, photo=bool(photo))
            if integer(document.get("file_size"), True):
                value["file_size"] = document["file_size"]
    return value


class EditorialService:
    def __init__(self, engine, auth, media, transport, download_limit, *, catalog_database_url=None,
                 isolated_execution_scope=None, execution_authorization_loader=None, production_execution_scope=None):
        self.engine, self.auth, self.media, self.transport = engine, auth, media, transport
        self.download_limit = download_limit
        self.catalog_database_url = catalog_database_url
        if isolated_execution_scope is not None and production_execution_scope is not None:
            raise ValueError('Conflicting execution scopes')
        self.isolated_execution_scope = isolated_execution_scope
        self.execution_scope = production_execution_scope or isolated_execution_scope
        self.execution_authorization_loader = execution_authorization_loader
        if self.execution_scope is not None:
            from app.editorial.commercial_execution import validate_scope
            validate_scope(self.execution_scope)
            if self.execution_scope.editorial_engine is not engine or not callable(execution_authorization_loader):
                raise ValueError('Invalid isolated execution boundary')
        self._summary_ids = set()  # Best-effort response deduplication; never persisted.
        self.readonly_offset = 0

    def _send_summary(self, uid, payload):
        if uid in self._summary_ids or not self.auth.allows(payload["chat"], payload["user"]):
            return
        with Session(self.engine) as db:
            draft = db.scalar(select(Draft).where(Draft.chat_id == payload["chat"], Draft.user_id == payload["user"]))
            proposal = interview.latest(db, draft) if draft else None
            if draft and carta_identity.owns(db, draft):
                if draft.state not in INACTIVE and db.get(Interview, draft.id).history.get("phase") == "commercial":
                    text = commercial_interview.summary(db, draft)
                else:
                    text = carta_identity.render(db, draft)[0]
            elif proposal:
                try:
                    text = interview.proposal_summary(proposal.payload)
                except ValueError:
                    text = "Esta versión de propuesta no es compatible o no es válida. El borrador se conserva sin cambios."
            else:
                text = "Aún no hay una propuesta V2.1. Usa /entrevista para prepararla. El borrador y sus imágenes se conservan."
                current = self._current(db, draft) if draft else None
                if current and current.operation:
                    text = "Operación del borrador: " + OPERATIONS[current.operation][0] + "\n" + text
        self._summary_ids.add(uid)
        self.readonly_offset = max(self.readonly_offset, uid + 1)
        if len(self._summary_ids) > 512:
            self._summary_ids = set(sorted(self._summary_ids)[-256:])
        try:
            self.transport.send_message(payload["chat"], text)
        except TransportError:
            pass  # Read-only commands have no durable outbox or automatic retry.

    def ingest(self, updates):
        if not isinstance(updates, list) or len(updates) > 20:
            raise ValueError("Invalid update batch")
        projected = [(raw["update_id"], project_update(raw, self.auth)) for raw in updates
                     if isinstance(raw, dict) and "update_id" in raw]
        if len(projected) != len(updates):
            raise ValueError("Invalid update batch")
        summaries = [(uid, payload) for uid, payload in projected if payload.get("command") == "/resumen"]
        projected = [(uid, payload) for uid, payload in projected if payload.get("command") != "/resumen"]
        if summaries:
            with Session(self.engine) as db:
                offset = db.get(Cursor, 1).next_offset
            for uid, payload in summaries:
                if uid >= offset:
                    self._send_summary(uid, payload)
        if not projected:
            return
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            cursor = db.get(Cursor, 1)
            for update_id, payload in sorted(projected, key=lambda item: item[0]):
                if update_id >= cursor.next_offset and db.get(Update, update_id) is None:
                    db.add(Update(id=update_id, payload=payload))
            if projected:
                cursor.next_offset = max(cursor.next_offset, max(uid for uid, _ in projected) + 1)
            db.commit()

    def _current(self, db, draft):
        return db.scalar(select(Version).where(Version.draft_id == draft.id, Version.revision == draft.revision))

    def _editable_with_v21(self, db, draft):
        if draft is None:
            return True
        state = db.get(Interview, draft.id)
        legacy_envelope = state and isinstance(state.history, dict) and state.history.get('flow') == 'legacy_with_saved' \
            and isinstance(state.history.get('steps'), list)
        if state and (state.step == "v2.2" or (not isinstance(state.history, list) and not legacy_envelope)):
            return False
        row = interview.latest(db, draft)
        if row is None:
            return True
        try:
            return isinstance(validate_proposal(row.payload), Proposal)
        except ValueError:
            return False

    def _preview(self, db, draft):
        if not self._editable_with_v21(db, draft):
            return "La edición de este contrato no está habilitada. Usa /resumen. El borrador se conserva.", None, None
        version = self._current(db, draft)
        if not version:
            return "Aún no hay una imagen. Usa /obra para adjuntarla.", None, None
        asset = db.get(Asset, version.asset_id)
        selected = OPERATIONS[version.operation][0] if version.operation else "Sin elegir"
        proposal = interview.latest(db, draft)
        if proposal:
            selected = OPERATIONS[proposal.payload["operation"]][0]
        source = "Foto comprimida por Telegram" if version.compressed_photo else "Documento recibido"
        text = (f"Borrador · versión {draft.revision}\n{source}\n"
                f"Archivo: {asset.extension.upper()}, {asset.byte_count} bytes\n"
                f"Vista previa: {asset.width} × {asset.height}\nOperación: {selected}\n"
                "Nada se ha publicado. No se cambian cervezas, precios ni los 16 slots.\n"
                "Elige la operación. Usa /obra para reemplazar la imagen o /cancelar para cerrar el borrador.")
        buttons = [[{"text": label, "callback_data": f"op:{draft.id}:{draft.revision}:{code}"}]
                   for code, (label, permission) in OPERATIONS.items()
                   if self.auth.allows(draft.chat_id, draft.user_id, permission)]
        return text, {"inline_keyboard": buttons}, asset.id

    def process_one(self):
        # No DB write lock held while downloading/decoding files.
        with Session(self.engine) as db:
            item = db.scalar(select(Update).where(Update.state == "pending").order_by(Update.id).limit(1))
            if item is None:
                return False
            uid, payload = item.id, item.payload
            draft = db.scalar(select(Draft).where(Draft.chat_id == payload.get("chat"), Draft.user_id == payload.get("user")))
            eligible_attachment = draft is not None and draft.state not in INACTIVE \
                and self._editable_with_v21(db, draft) \
                and payload.get("reply_to") is not None and payload["reply_to"] == draft.prompt_message_id
            expected_revision = draft.revision if draft else None
            carta_search = draft is not None and draft.state not in INACTIVE \
                and self.auth.allows(payload.get("chat"), payload.get("user")) \
                and carta_identity.owns(db, draft) and payload.get("text") \
                and draft.prompt_message_id is not None and payload.get("reply_to") == draft.prompt_message_id \
                and db.get(Interview, draft.id).history["phase"] == "name"
        if carta_search and (typing := getattr(self.transport, "send_typing", None)):
            try:
                typing(payload["chat"])  # One native action, outside the write transaction.
            except TransportError:
                pass  # Optional UX must never prevent the search.
        prepared, error, transient = None, None, False
        if payload.get("file_id") and eligible_attachment and self.auth.allows(payload.get("chat"), payload.get("user")):
            try:
                if payload.get("file_size", 0) > self.download_limit:
                    raise DownloadLimit()
                content = self.transport.download(payload["file_id"], self.download_limit)
                if len(content) > self.download_limit:
                    raise DownloadLimit()
                prepared = self.media.prepare(content)
            except DownloadLimit:
                error = (f"Esta descarga de Telegram admite hasta {self.download_limit / 1024 / 1024:g} MiB. "
                         "No es el límite general de imágenes de ATLAS. Responde con otro archivo; tu borrador sigue aquí.")
            except HTTPException:
                error = ("ATLAS no pudo validar la imagen: usa un archivo de un solo frame JPEG, PNG, WebP, TIFF, BMP o GIF, "
                         "de hasta 25 MiB y 50 megapíxeles. Responde con otro archivo; tu borrador sigue aquí.")
            except TransportError:
                transient = True
        cleanup_messages = []
        execution_candidate = None
        recovery_requested = False
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            item = db.get(Update, uid)
            if item.state != "pending":
                return True
            item.attempts += 1
            if payload.get("ignore") or not self.auth.allows(payload.get("chat"), payload.get("user")):
                item.state = "ignored"
                db.commit()
                return True
            if transient and item.attempts < 3:
                item.error_code = "download_unavailable"
                db.commit()
                return False
            if transient:
                error = "No pudimos descargar la imagen. Responde de nuevo con el archivo; tu borrador sigue aquí."
            draft = db.scalar(select(Draft).where(Draft.chat_id == payload["chat"], Draft.user_id == payload["user"]))
            text, markup, asset_id, prompt = "Usa /obra para preparar una imagen.", None, None, False
            command = payload.get("command")
            if carta_identity.owns(db, draft) and draft.state in INACTIVE and command in {
                    "/obra", "/entrevista", "/continuar", "/corregir", "/vista", "/cancelar"}:
                state = db.get(Interview, draft.id)
                # Keep the proposal revision floor; legacy save will append above it.
                # A new image revision boundary also invalidates pre-Carta op/start buttons.
                latest = interview.latest(db, draft, include_inactive=True)
                state.revision = latest.revision if latest else state.revision
                state.step = "legacy_pending"
                draft_lifecycle.set_legacy_steps(state, [])
                draft.revision += 1
                draft.prompt_message_id = None
            if command == '/recuperar22':
                from app.editorial.commercial_execution import _request, _authorized
                from app.editorial.production_execution import ProductionExecutionScope, validate_request
                try:
                    if self.execution_scope is None or draft is None:
                        raise ValueError('execution_disabled')
                    _, request = _request(db,draft.id,payload['request_id'])
                    if (request['chat'],request['operator']) != (payload['chat'],payload['user']):
                        raise ValueError('request_owner_mismatch')
                    _authorized(self.execution_authorization_loader,request,require_base=type(self.execution_scope) is ProductionExecutionScope)
                    if type(self.execution_scope) is ProductionExecutionScope:
                        validate_request(self.execution_scope,request)
                    execution_candidate = (draft.id,payload['request_id'])
                    recovery_requested = True
                    text, markup, asset_id, prompt = 'Recuperación solicitada; aplicación aún no verificada.',None,None,False
                except (ValueError,KeyError,TypeError):
                    text, markup, asset_id, prompt = 'No se puede recuperar esta solicitud: ejecución deshabilitada, autorización ausente o solicitud no vigente.',None,None,False
            elif command in {'/aplicar22','/recibo22'} or payload.get('callback','').startswith('a22:'):
                from app.editorial.production_execution import activation
                text, markup, asset_id, prompt = commercial_approval_flow.handle(
                    db,draft,payload,self.auth,self.catalog_database_url,update_id=uid,
                    isolated_execution_enabled='production' if activation(self.execution_scope) else self.execution_scope is not None,
                    production_activation=activation(self.execution_scope))
                if draft and payload.get('callback','').endswith(':confirm'):
                    execution_state = db.get(Interview,draft.id)
                    execution_history = execution_state.history if execution_state and isinstance(execution_state.history,dict) else {}
                    review = execution_history.get('application_review',{})
                    request = execution_history.get('execution_requests',{}).get(review.get('request_id'),{})
                    if request.get('response_update_id') == uid:
                        execution_candidate = (draft.id,review['request_id'])
            elif command == "/borradores22" or payload.get('callback', '').startswith('r22:list:'):
                offset = int(payload['callback'].split(':')[2]) if payload.get('callback') else 0
                text, markup, asset_id, prompt = draft_lifecycle.listing(db, draft, self.auth, offset=offset)
            elif payload.get('callback', '').startswith('r22:'):
                text, markup, asset_id, prompt = draft_lifecycle.reopen(db, draft, payload['callback'], self.auth)
            elif command == "/nueva22":
                if not self.auth.allows(payload["chat"], payload["user"], "beer.create"):
                    text = "No tienes permiso para proponer una cerveza nueva."
                elif draft and draft.state not in INACTIVE:
                    text = "Ya tienes un borrador activo. Usa /continuar o /cancelar."
                else:
                    draft, _ = carta_identity.begin(db, draft, payload["chat"], payload["user"])
                    text, markup, asset_id, prompt = commercial_interview.start(db, draft, mode="new")
            elif command in {"/editar22", "/rapido22"}:
                if not self.auth.allows(payload["chat"], payload["user"], "beer.edit"):
                    text = "No tienes permiso para proponer cambios comerciales."
                elif not carta_identity.owns(db, draft) or draft.state in INACTIVE:
                    text = "Primero confirma una cerveza con /carta22. Tu borrador se conserva."
                else:
                    try:
                        text, markup, asset_id, prompt = commercial_interview.start(
                            db, draft, mode="edit", catalog_url=self.catalog_database_url, quick=command == "/rapido22")
                    except (ValueError, OSError):
                        text = "No se pudo verificar la identidad y sus valores actuales. No se cambió la propuesta."
            elif command == "/carta22":
                if not self.catalog_database_url:
                    text = "La consulta de Carta V2.2 aún no está configurada. Tu borrador se conserva."
                else:
                    draft, result = carta_identity.begin(db, draft, payload["chat"], payload["user"])
                    text, markup, asset_id, prompt = result
            elif carta_identity.owns(db, draft) and draft.state not in INACTIVE:
                previous_phase = db.get(Interview, draft.id).history["phase"]
                if previous_phase == "commercial" and command != "/cancelar" and not self.auth.allows(
                        draft.chat_id, draft.user_id, commercial_interview.permission(db.get(Interview, draft.id))):
                    text = "No tienes permiso para modificar esta propuesta comercial. El borrador se conserva."
                else:
                    text, markup, asset_id, prompt = carta_identity.transition(
                        db, draft, payload, self.catalog_database_url, uid)
                if draft.state in INACTIVE or (previous_phase != "confirmed"
                                                  and db.get(Interview, draft.id).history["phase"] == "confirmed"):
                    cleanup_messages = carta_identity.obsolete_keyboards(db, draft)
            elif payload.get("callback", "").startswith(("c22:", "b22:")):
                text = carta_identity.STALE
            elif not self._editable_with_v21(db, draft):
                text = "La edición de este contrato no está habilitada. Usa /resumen. El borrador se conserva sin cambios."
            elif command == "/obra":
                if draft is None:
                    draft = Draft(id=uuid4().hex, chat_id=payload["chat"], user_id=payload["user"])
                    db.add(draft)
                    db.flush()
                if draft.state in INACTIVE:
                    draft.state = "draft"
                text, markup, prompt = PROMPT, {"force_reply": True, "input_field_placeholder": "Adjunta una imagen"}, True
            elif command in {"/entrevista", "/continuar", "/corregir"}:
                if draft is None:
                    draft = Draft(id=uuid4().hex, chat_id=payload["chat"], user_id=payload["user"])
                    db.add(draft)
                    db.flush()
                if command in {"/entrevista", "/continuar"} and draft.state in INACTIVE:
                    draft.state = "draft"
                current = self._current(db, draft)
                state = db.get(Interview, draft.id)
                if state and state.step == "legacy_pending":
                    state = None
                if state is None and current and current.operation and self.auth.allows(
                        draft.chat_id, draft.user_id, OPERATIONS[current.operation][1]):
                    state = interview.begin(db, draft, current.operation)
                if state:
                    if command == "/corregir":
                        text, markup, asset_id, prompt = interview.transition(db, draft, "edit")
                    elif state.step == "summary" and command in {"/continuar", "/entrevista"}:
                        text, markup, asset_id, prompt = interview.transition(db, draft, "resume")
                    else:
                        text, markup, asset_id, prompt = interview.render(db, draft)
                else:
                    text = "Elige la operación para iniciar la entrevista. Nada se publicará."
                    markup = {"inline_keyboard": [[{"text": label, "callback_data": f"start:{draft.id}:{draft.revision}:{code}"}]
                              for code, (label, permission) in OPERATIONS.items()
                              if self.auth.allows(draft.chat_id, draft.user_id, permission)]}
            elif command == "/cancelar" and draft:
                draft.state, draft.prompt_message_id = "cancelled", None
                text = "Borrador cerrado. No se publicó nada. Usa /obra para retomarlo."
            elif payload.get("callback") and (draft is None or draft.state in INACTIVE):
                text = "Ese botón ya no está vigente. Usa /continuar para retomar el borrador."
            elif draft and draft.state not in INACTIVE:
                if command == "/vista":
                    text, markup, asset_id = self._preview(db, draft)
                    if db.get(Interview, draft.id):
                        text += "\n/resumen muestra la propuesta; /continuar retoma la entrevista."
                elif payload.get("callback", "").startswith("i:"):
                    _, draft_id, revision, action = payload["callback"].split(":")
                    state = db.get(Interview, draft.id)
                    proposal = interview.latest(db, draft)
                    if not state or not proposal or draft_id != draft.id or int(revision) != state.revision \
                            or proposal.revision != state.revision or proposal.payload["revision"] != state.revision:
                        text = "Esa pregunta ya no está vigente. Usa /continuar."
                    elif not self.auth.allows(draft.chat_id, draft.user_id,
                                              OPERATIONS[interview.latest(db, draft).payload["operation"]][1]):
                        text = "No tienes permiso para preparar esa operación."
                    else:
                        choices = interview.options("operation", interview.Proposal.model_validate(interview.latest(db, draft).payload))
                        changing = state.step == "operation" and action.isdecimal() and int(action) < len(choices)
                        target = choices[int(action)][1] if changing else None
                        if state.step.startswith("confirm_operation:") and action == "0":
                            target = state.step.split(":")[1]
                        if target and not self.auth.allows(draft.chat_id, draft.user_id, OPERATIONS[target][1]):
                            text = "No tienes permiso para preparar esa operación."
                        else:
                            text, markup, asset_id, prompt = interview.transition(db, draft, action)
                elif payload.get("callback"):
                    _, draft_id, revision, operation = payload["callback"].split(":")
                    state = db.get(Interview, draft.id)
                    proposal = interview.latest(db, draft)
                    if (state and state.step != "legacy_pending") or proposal or draft_id != draft.id or int(revision) != draft.revision:
                        text = "Esa vista previa ya no está vigente. Usa /corregir para cambiar la operación o /continuar para retomar la entrevista."
                    elif not self.auth.allows(payload["chat"], payload["user"], OPERATIONS[operation][1]):
                        text = "No tienes permiso para preparar esa operación. Tu borrador sigue aquí."
                    else:
                        current = self._current(db, draft)
                        if current and current.operation != operation:
                            draft.revision += 1
                            db.add(Version(draft_id=draft.id, revision=draft.revision, asset_id=current.asset_id,
                                           compressed_photo=current.compressed_photo, operation=operation,
                                           created_at=datetime.now(timezone.utc).isoformat()))
                            draft.state = "classified"
                            db.flush()
                        if db.get(Interview, draft.id) or current is None or payload["callback"].startswith("start:"):
                            interview.begin(db, draft, operation)
                            text, markup, asset_id, prompt = interview.render(db, draft)
                        else:
                            text, markup, asset_id = self._preview(db, draft)
                elif payload.get("reply_to") != draft.prompt_message_id or draft.prompt_message_id is None:
                    text = "Usa /obra y responde al mensaje del bot para adjuntar la imagen correcta. Tu borrador sigue aquí."
                elif payload.get("invalid_attachment"):
                    text = payload["invalid_attachment"]
                elif error:
                    text = error
                elif prepared and draft.revision == expected_revision:
                    asset = db.scalar(select(Asset).where(Asset.digest == prepared["digest"]))
                    if asset is None:
                        asset = Asset(id=uuid4().hex, **prepared)
                        db.add(asset)
                        db.flush()
                    draft.revision += 1
                    draft.state = "draft"
                    db.add(Version(draft_id=draft.id, revision=draft.revision, asset_id=asset.id,
                                   compressed_photo=payload["photo"], operation=None,
                                   created_at=datetime.now(timezone.utc).isoformat()))
                    db.flush()
                    state = db.get(Interview, draft.id)
                    if state and state.step != "legacy_pending":
                        state.step = "asset"
                        interview.save(db, draft, state,
                                       interview.Proposal.model_validate(interview.latest(db, draft).payload),
                                       "Imagen recibida; pendiente de asignación explícita")
                        text, markup, asset_id, prompt = interview.render(db, draft)
                        asset_id = asset.id
                    else:
                        text, markup, asset_id = self._preview(db, draft)
                elif payload.get("text") and db.get(Interview, draft.id) \
                        and db.get(Interview, draft.id).step != "legacy_pending":
                    if self.auth.allows(draft.chat_id, draft.user_id,
                                        OPERATIONS[interview.latest(db, draft).payload["operation"]][1]):
                        text, markup, asset_id, prompt = interview.transition(db, draft, text=payload["text"])
                    else:
                        text = "No tienes permiso para preparar esa operación."
                else:
                    text = "Responde con una sola imagen. Tu borrador sigue aquí."
            db.add(Reply(update_id=uid, draft_id=draft.id if draft else None, chat_id=payload["chat"],
                         text=text, markup=markup, is_prompt=prompt, asset_id=asset_id))
            item.state, item.error_code = "done", None
            db.commit()
        if cleanup_messages and (remove := getattr(self.transport, "remove_inline_keyboard", None)):
            for message_id in cleanup_messages:
                try:
                    remove(payload["chat"], message_id)
                except TransportError:
                    pass  # Best effort after commit; stale buttons are still rejected.
        if payload.get("callback_id"):
            try:
                self.transport.answer_callback(payload["callback_id"])
            except TransportError:
                pass  # Callback acknowledgement cannot undo a committed draft.
        if execution_candidate and self.execution_scope is not None:
            from app.editorial.commercial_execution import execute_request, _load, _read_receipt
            # Editorial Session/transaction above have both ended before acquiring execution locks.
            try:
                result = execute_request(self.execution_scope,draft_id=execution_candidate[0],request_id=execution_candidate[1],
                                         authorization_loader=self.execution_authorization_loader)
                receipt = _read_receipt(self.execution_scope,_load(self.execution_scope,*execution_candidate)) if result=='applied' else None
                outcome = f"Aplicación verificada · recibo {receipt['application_id']} · UTC: {receipt['applied_at']}" if receipt else f'Solicitud: {result}. No se ha verificado una aplicación.'
            except (ValueError,OSError):
                outcome = 'No se pudo verificar la ejecución. Conserva el UUID; revisa el recibo antes de reintentar.'
            if recovery_requested:
                with Session(self.engine) as recovery_db:
                    response = recovery_db.scalar(select(Reply).where(Reply.update_id==uid,Reply.chat_id==payload['chat'],Reply.state=='pending'))
                    if response:
                        response.text = outcome
                    recovery_db.commit()
        return True

    def recover_replies(self):
        with Session(self.engine) as db:
            for reply in db.scalars(select(Reply).where(Reply.state == "sending")):
                reply.state = "uncertain"
            db.commit()

    def flush_one(self):
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            reply = db.scalar(select(Reply).where(Reply.state == "pending").order_by(Reply.id).limit(1))
            if reply is None:
                return False
            draft = db.get(Draft, reply.draft_id) if reply.draft_id else None
            if draft and not self.auth.allows(draft.chat_id, draft.user_id):
                reply.state = "suppressed"
                db.commit()
                return True
            rid, chat, text, markup, asset_id = reply.id, reply.chat_id, reply.text, reply.markup, reply.asset_id
            asset = db.get(Asset, asset_id) if asset_id else None
            digest = asset.digest if asset else None
            reply.state = "sending"
            db.commit()
        try:
            if digest:
                image = self.media.path(digest, ".preview.jpg").read_bytes()
                mid = self.transport.send_photo(chat, text, image, markup)
            else:
                mid = self.transport.send_message(chat, text, markup)
            if not integer(mid, True):
                raise TransportError()
        except (TransportError, OSError):
            with Session(self.engine) as db:
                db.get(Reply, rid).state = "uncertain"
                db.commit()
            event("editorial", "delivery_uncertain")
            return True
        with Session(self.engine) as db:
            reply = db.get(Reply, rid)
            reply.state, reply.message_id = "sent", mid
            if reply.is_prompt:
                draft = db.get(Draft, reply.draft_id)
                if draft.state not in INACTIVE:
                    draft.prompt_message_id = mid
            db.commit()
        event("editorial", "operation_ok")
        return True
