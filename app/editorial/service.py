"""Finite draft conversation. No imports of Beer, live engine or publication APIs."""
from datetime import datetime, timezone
import re
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.editorial.models import Cursor, Update, Asset, Draft, Version, Reply
from app.editorial.telegram import DownloadLimit, TransportError

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
        if not isinstance(data, str) or not re.fullmatch(r"op:[a-f0-9]{32}:[0-9]{1,9}:(?:new|art|fix|board|event)", data):
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
    if isinstance(text, str) and re.fullmatch(r"/(?:obra|vista|cancelar)(?:@[A-Za-z0-9_]{5,32})?", text.strip()):
        value["command"] = text.strip().split("@")[0]
        return value
    reply = message.get("reply_to_message")
    if isinstance(reply, dict) and integer(reply.get("message_id"), True):
        value["reply_to"] = reply["message_id"]
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
    def __init__(self, engine, auth, media, transport, download_limit):
        self.engine, self.auth, self.media, self.transport = engine, auth, media, transport
        self.download_limit = download_limit

    def ingest(self, updates):
        if not isinstance(updates, list) or len(updates) > 20:
            raise ValueError("Invalid update batch")
        projected = [(raw["update_id"], project_update(raw, self.auth)) for raw in updates
                     if isinstance(raw, dict) and "update_id" in raw]
        if len(projected) != len(updates):
            raise ValueError("Invalid update batch")
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

    def _preview(self, db, draft):
        version = self._current(db, draft)
        if not version:
            return "Aún no hay una imagen. Usa /obra para adjuntarla.", None, None
        asset = db.get(Asset, version.asset_id)
        selected = OPERATIONS[version.operation][0] if version.operation else "Sin elegir"
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
            eligible_attachment = draft is not None and draft.state != "cancelled" \
                and payload.get("reply_to") is not None and payload["reply_to"] == draft.prompt_message_id
            expected_revision = draft.revision if draft else None
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
            if command == "/obra":
                if draft is None:
                    draft = Draft(id=uuid4().hex, chat_id=payload["chat"], user_id=payload["user"])
                    db.add(draft)
                    db.flush()
                if draft.state == "cancelled":
                    draft.state = "draft"
                text, markup, prompt = PROMPT, {"force_reply": True, "input_field_placeholder": "Adjunta una imagen"}, True
            elif command == "/cancelar" and draft:
                draft.state, draft.prompt_message_id = "cancelled", None
                text = "Borrador cerrado. No se publicó nada. Usa /obra para retomarlo."
            elif draft and draft.state != "cancelled":
                if command == "/vista":
                    text, markup, asset_id = self._preview(db, draft)
                elif payload.get("callback"):
                    _, draft_id, revision, operation = payload["callback"].split(":")
                    if draft_id != draft.id or int(revision) != draft.revision:
                        text = "Esa vista previa ya no está vigente. Usa /vista para ver tu borrador actual."
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
                    text, markup, asset_id = self._preview(db, draft)
                else:
                    text = "Responde con una sola imagen. Tu borrador sigue aquí."
            db.add(Reply(update_id=uid, draft_id=draft.id if draft else None, chat_id=payload["chat"],
                         text=text, markup=markup, is_prompt=prompt, asset_id=asset_id))
            item.state, item.error_code = "done", None
            db.commit()
        if payload.get("callback_id"):
            try:
                self.transport.answer_callback(payload["callback_id"])
            except TransportError:
                pass  # Callback acknowledgement cannot undo a committed draft.
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
            return True
        with Session(self.engine) as db:
            reply = db.get(Reply, rid)
            reply.state, reply.message_id = "sent", mid
            if reply.is_prompt:
                draft = db.get(Draft, reply.draft_id)
                if draft.state != "cancelled":
                    draft.prompt_message_id = mid
            db.commit()
        return True
