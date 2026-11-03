"""Bounded outbound transport and deterministic, allowlisted notification text."""
from dataclasses import dataclass, field
from datetime import timezone
import http.client
import json
import math
import queue
import re
import socket
import ssl
import threading
import unicodedata

from pydantic import SecretStr

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
TOTAL_TIMEOUT = 30
MAX_RESPONSE_BYTES = 32 * 1024


class IncidentConfigurationError(RuntimeError):
    def __init__(self):
        super().__init__("Incidents enabled but dedicated token or destination configuration is missing or invalid")


@dataclass(frozen=True)
class IncidentConfig:
    token: SecretStr
    chat_id: SecretStr
    max_attempts: int


def incident_config(settings):
    if not settings.telegram_incidents_enabled:
        return None
    token = settings.telegram_incidents_bot_token
    chat = settings.telegram_incidents_chat_id
    if not token or not chat or not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", token.get_secret_value()) \
            or not re.fullmatch(r"-?[0-9]{1,20}", chat.get_secret_value()) or int(chat.get_secret_value()) == 0:
        raise IncidentConfigurationError()
    return IncidentConfig(token, chat, settings.telegram_incidents_max_attempts)


@dataclass(frozen=True)
class DeliveryResult:
    code: str
    message_id: int | None = None
    permanent: bool = False
    stop_worker: bool = False
    retry_after: int | None = None

    def __post_init__(self):
        allowed = {"sent", "invalid_rate_limit", "rate_limited", "bot_unauthorized", "destination_forbidden",
                   "destination_changed", "payload_rejected", "telegram_unavailable", "protocol_rejected",
                   "delivery_unknown", "invalid_report_content"}
        if self.code not in allowed or self.code == "sent" and (type(self.message_id) is not int or not 0 < self.message_id < 2**63):
            raise ValueError("Invalid sanitized delivery result")
        if self.retry_after is not None and (type(self.retry_after) is not int or not 0 <= self.retry_after <= 31_536_000):
            raise ValueError("Invalid delivery delay")


def _failure(status, data):
    if status == 429:
        retry = data.get("parameters", {}).get("retry_after") if isinstance(data.get("parameters"), dict) else None
        if type(retry) is not int or not 0 <= retry <= 31_536_000:
            # Do not risk retrying earlier than an uninterpretable flood delay.
            return DeliveryResult("invalid_rate_limit", permanent=True, stop_worker=True)
        return DeliveryResult("rate_limited", retry_after=retry)
    if status in {401, 404}:
        return DeliveryResult("bot_unauthorized", permanent=True, stop_worker=True)
    if status == 403:
        return DeliveryResult("destination_forbidden", permanent=True, stop_worker=True)
    if status == 400:
        parameters = data.get("parameters")
        if isinstance(parameters, dict) and "migrate_to_chat_id" in parameters:
            return DeliveryResult("destination_changed", permanent=True, stop_worker=True)
        return DeliveryResult("payload_rejected", permanent=True)
    if status >= 500 or status in {408, 425}:
        return DeliveryResult("telegram_unavailable")
    return DeliveryResult("protocol_rejected", permanent=True)


class TelegramTransport:
    def __init__(self, config, *, connection_factory=http.client.HTTPSConnection):
        self.config = config
        self.connection_factory = connection_factory

    def send(self, text):
        # Fixed HTTPS host, no redirects, no caller-provided URLs or files.
        connection = self.connection_factory("api.telegram.org", timeout=CONNECT_TIMEOUT, context=ssl.create_default_context())
        expired = threading.Event()

        def abort():
            expired.set()
            try:
                if connection.sock:
                    connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

        # A daemon I/O thread also bounds DNS resolution for the caller; socket
        # timeouts alone do not bound getaddrinfo(). An expired attempt cannot
        # later reconnect and send after the worker has moved on.
        completed = queue.Queue(maxsize=1)

        def perform():
            try:
                result = self._send_connected(connection, text, expired)
            except Exception:
                result = DeliveryResult("delivery_unknown")
            completed.put(result)

        threading.Thread(target=perform, daemon=True, name="incident-https").start()
        try:
            return completed.get(timeout=TOTAL_TIMEOUT)
        except queue.Empty:
            abort()
            return DeliveryResult("delivery_unknown")

    def _send_connected(self, connection, text, expired):
        try:
            connection.connect()
            if expired.is_set():
                return DeliveryResult("delivery_unknown")
            connection.auto_open = 0
            connection.sock.settimeout(READ_TIMEOUT)
            body = json.dumps({"chat_id": self.config.chat_id.get_secret_value(), "text": text,
                               "link_preview_options": {"is_disabled": True}}, ensure_ascii=False).encode("utf-8")
            connection.request("POST", "/bot" + self.config.token.get_secret_value() + "/sendMessage",
                               body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if expired.is_set() or len(raw) > MAX_RESPONSE_BYTES:
                return DeliveryResult("delivery_unknown")
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            if response.status != 200:
                return _failure(response.status, data)
            if data.get("ok") is True and isinstance(data.get("result"), dict):
                message_id = data["result"].get("message_id")
                if type(message_id) is int and 0 < message_id < 2**63:
                    return DeliveryResult("sent", message_id=message_id)
            if data.get("ok") is False and type(data.get("error_code")) is int:
                return _failure(data["error_code"], data)
            return DeliveryResult("delivery_unknown")
        except (OSError, http.client.HTTPException):
            # Neither exception text nor response bodies are logged or returned.
            return DeliveryResult("delivery_unknown")
        finally:
            connection.close()


def clean(value, limit):
    if not isinstance(value, str):
        return ""
    value = "".join(" " if unicodedata.category(c) == "Cc" else "" if unicodedata.category(c).startswith("C") else c
                    for c in value[:4096])
    value = re.sub(r"(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+", "[enlace omitido]", value)
    value = re.sub(r"\b[0-9]+:[A-Za-z0-9_-]{20,}\b", "[dato omitido]", value)
    return " ".join(value.split())[:limit]


def diagnostic_summary(snapshot):
    if not isinstance(snapshot, dict):
        return "sin datos compatibles"
    parts = []
    route = snapshot.get("route")
    if isinstance(route, str) and re.fullmatch(r"/(?:museum|beer/[0-9]{1,12})?", route):
        parts.append("sección " + route)
    browser = snapshot.get("browser")
    if isinstance(browser, dict) and isinstance(browser.get("name"), str) and browser["name"] in {"Safari", "Chrome", "Firefox", "Edge", "Opera"}:
        name = browser["name"]
        version = browser.get("version")
        if isinstance(version, str) and re.fullmatch(r"[0-9.]{1,24}", version):
            name += " " + version
        parts.append(name)
    operating_system = snapshot.get("os")
    if isinstance(operating_system, str) and operating_system in {"iOS/iPadOS", "Android", "Windows", "macOS (iPadOS posible)", "Linux"}:
        parts.append(operating_system)
    viewport = snapshot.get("viewport")
    if isinstance(viewport, dict):
        dimensions = [viewport.get(key) for key in ["width", "height"]]
        if all(type(v) in {int, float} and math.isfinite(v) and 0 <= v <= 100_000 for v in dimensions):
            parts.append(f"ventana {dimensions[0]:.0f}×{dimensions[1]:.0f}")
    if type(snapshot.get("online")) is bool:
        parts.append("con conexión" if snapshot["online"] else "sin conexión (indicador)")
    return "; ".join(parts)[:600] or "sin datos compatibles"


@dataclass(frozen=True)
class NotificationContent:
    report_id: str
    created_at: object
    categories: list = field(repr=False)
    description: str = field(repr=False)
    diagnostic_consent: bool
    diagnostics: dict | None = field(repr=False)
    has_screenshot: bool


def format_notification(report):
    categories = {"Tap List", "Museo", "Información de cerveza", "Interacción / visualización", "Otro"}
    selected = [item for item in report.categories[:5] if isinstance(item, str) and item in categories]
    description = clean(report.description, 501)
    excerpt = description[:500]
    # The worker selects at most 501 source characters, so any extra character
    # already proves truncation even if sanitization shortens the excerpt.
    truncated = len(report.description) > 500 or len(description) > 500
    timestamp = report.created_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    lines = ["Nuevo reporte de ATLAS", "Reporte: " + clean(report.report_id, 36), "Fecha UTC: " + timestamp,
             "Categorías: " + (", ".join(selected) or "sin categoría compatible"), "", "Descripción:", excerpt]
    if truncated:
        lines.append("[Descripción truncada; texto completo en ATLAS]")
    if report.diagnostic_consent:
        lines.extend(["", "Diagnóstico autorizado: " + diagnostic_summary(report.diagnostics)])
    lines.extend(["", "Captura: " + ("sí, privada en ATLAS" if report.has_screenshot else "no")])
    return "\n".join(lines)[:3500]
