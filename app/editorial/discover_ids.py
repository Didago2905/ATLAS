"""Explicit, read-only Telegram identification. No settings, DB or worker imports."""
from dataclasses import dataclass
import getpass
import http.client
import re
import sys
import warnings

from pydantic import SecretStr
from app.editorial.telegram import TelegramTransport

COMMAND = "/identificar"
CODE_PATTERN = r"[A-Za-z0-9_-]{8,64}"
MESSAGES = {
    "webhook": "Hay un webhook activo. Detén el diagnóstico y revisa esa configuración; no se ha cambiado nada.",
    "missing": ("No hay una identificación coincidente. Mantén el worker detenido, envía el comando dirigido "
                "al bot con el código exacto desde tu cuenta personal en el grupo y vuelve a ejecutar. "
                "No descartes actualizaciones pendientes."),
    "ambiguous": ("Hay varias identificaciones coincidentes. Usa un código nuevo y envía un solo mensaje; "
                  "vuelve a ejecutar sin iniciar el worker."),
    "sender": ("Identificación rechazada. Envía un mensaje nuevo desde tu cuenta personal en un grupo, "
               "sin reenviarlo ni usar modo anónimo o identidad de canal."),
    "code": "El código debe tener entre 8 y 64 letras ASCII, números, guiones o guiones bajos, sin espacios.",
    "backlog": ("La ventana de actualizaciones está llena. No se puede confirmar una identificación única. "
                "Revisa el backlog por separado; este diagnóstico no lo avanza ni lo descarta."),
    "response": "La respuesta de Telegram no permite verificar la identificación. No se han mostrado datos de la respuesta.",
}


class DiscoveryError(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(MESSAGES[reason])


@dataclass(frozen=True)
class Identification:
    chat_id: int
    chat_type: str
    user_id: int


def numeric(value, *, positive):
    return type(value) is int and -(2**63) < value < 2**63 and (value > 0 if positive else value < 0)


def verify_bot(transport):
    # Fixed read methods only. Do not import configuration or request any mutations.
    bot = transport._request("getMe", {})
    if not isinstance(bot, dict) or bot.get("is_bot") is not True or not numeric(bot.get("id"), positive=True):
        raise DiscoveryError("response")
    username = bot.get("username")
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise DiscoveryError("response")
    webhook = transport._request("getWebhookInfo", {})
    if not isinstance(webhook, dict) or not isinstance(webhook.get("url"), str):
        raise DiscoveryError("response")
    if webhook["url"]:
        raise DiscoveryError("webhook")
    return username


def discover_ids(transport, username, code):
    if not isinstance(code, str) or not re.fullmatch(CODE_PATTERN, code):
        raise DiscoveryError("code")
    # No offset, allowed_updates, webhook changes or acknowledgement. Never page
    # by advancing an offset, even if the desired message lies beyond this window.
    updates = transport._request("getUpdates", {"timeout": 0, "limit": 100})
    if not isinstance(updates, list) or len(updates) > 100:
        raise DiscoveryError("response")
    if len(updates) == 100:
        raise DiscoveryError("backlog")
    command = f"{COMMAND}@{username}"
    expected = command + " " + code
    matches = []
    for update in updates:
        if not isinstance(update, dict):
            raise DiscoveryError("response")
        # Channel posts and edited messages cannot identify the operator. Include
        # exact matching ones only to reject them, never to authorize a result.
        for kind in ("message", "edited_message", "channel_post", "edited_channel_post"):
            message = update.get(kind)
            if isinstance(message, dict) and message.get("text") == expected:
                matches.append((kind, message))
    if not matches:
        raise DiscoveryError("missing")
    if len(matches) != 1:
        raise DiscoveryError("ambiguous")
    kind, message = matches[0]
    actor, chat = message.get("from"), message.get("chat")
    if kind != "message" or not isinstance(actor, dict) or actor.get("is_bot") is not False \
            or not numeric(actor.get("id"), positive=True) or not isinstance(chat, dict) \
            or chat.get("type") not in {"group", "supergroup"} or not numeric(chat.get("id"), positive=False) \
            or any(key in message for key in ("sender_chat", "author_signature", "forward_origin", "forward_from",
                                             "forward_from_chat", "forward_sender_name", "forward_date", "via_bot")):
        raise DiscoveryError("sender")
    entities = message.get("entities")
    if not isinstance(entities, list) or not any(isinstance(entity, dict) and entity.get("type") == "bot_command"
            and type(entity.get("offset")) is int and entity["offset"] == 0
            and type(entity.get("length")) is int and entity["length"] == len(command) for entity in entities):
        raise DiscoveryError("sender")
    return Identification(chat["id"], chat["type"], actor["id"])


def quiet_connection(*args, **kwargs):
    connection = http.client.HTTPSConnection(*args, **kwargs)
    connection.set_debuglevel(0)  # Never inherit global HTTP wire debugging.
    return connection


def diagnostic_transport(token):
    return TelegramTransport(token, connection_factory=quiet_connection)


def main(*, transport_factory=diagnostic_transport):
    # Reject arguments without echoing them: even an accidentally pasted secret
    # must not be reproduced by argparse's usual unknown-argument error.
    if sys.argv[1:] in (["--help"], ["-h"]):
        print("Run interactively without arguments. Token is hidden; identification code is entered locally.")
        return 0
    if sys.argv[1:]:
        print("Este diagnóstico no acepta argumentos. Usa la entrada local interactiva.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty() or not sys.stderr.isatty():
        print("Se requiere una terminal local interactiva con entrada oculta; no uses pipes o redirecciones.", file=sys.stderr)
        return 2
    token = transport = None
    try:
        with warnings.catch_warnings():
            # Refuse getpass's echoing fallback instead of risking a visible token.
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = SecretStr(getpass.getpass("Token del bot Editorial (oculto): "))
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", token.get_secret_value()):
            print("El token no tiene un formato válido; no se ha mostrado ni guardado.", file=sys.stderr)
            return 2
        transport = transport_factory(token)
        username = verify_bot(transport)
        print("bot_username: @" + username, flush=True)
        code = input("Código temporal de identificación (8–64 caracteres): ")
        if not re.fullmatch(CODE_PATTERN, code):
            raise DiscoveryError("code")
        input("Envía /identificar dirigido al bot verificado, seguido de un espacio y el código exacto. "
              "Usa un mensaje nuevo desde tu cuenta personal en el grupo; después pulsa Enter: ")
        result = discover_ids(transport, username, code)
        print(f"chat_id: {result.chat_id}\nchat_type: {result.chat_type}\nuser_id: {result.user_id}")
        return 0
    except DiscoveryError as error:
        print(MESSAGES[error.reason], file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Diagnóstico cancelado; no se avanzó el offset.", file=sys.stderr)
        return 130
    except Exception:
        # Includes raw HTTP/library/factory errors and unavailable hidden input.
        print("No se pudo completar el diagnóstico de forma segura. Revisa la conexión y la entrada oculta; "
              "vuelve a ejecutar con el worker detenido. Detalles privados omitidos.", file=sys.stderr)
        return 2
    finally:
        # No os.environ mutation or child process creation anywhere in this tool.
        transport = token = None


if __name__ == "__main__":
    raise SystemExit(main())
