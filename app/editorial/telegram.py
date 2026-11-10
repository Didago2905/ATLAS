"""Dedicated mockable HTTPS transport. Never log URLs, payloads or exception text."""
import http.client
import json
import re
import ssl
import time
from uuid import uuid4


class TransportError(RuntimeError):
    def __init__(self):
        super().__init__("Editorial Telegram transport unavailable")


class DownloadLimit(RuntimeError):
    pass


class TelegramTransport:
    def __init__(self, token, *, connection_factory=http.client.HTTPSConnection):
        self.token = token
        self.connection_factory = connection_factory

    def _connection(self):
        return self.connection_factory("api.telegram.org", timeout=35, context=ssl.create_default_context())

    def _request(self, method, payload):
        connection = self._connection()
        try:
            connection.request("POST", "/bot" + self.token.get_secret_value() + "/" + method,
                               body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            if response.status != 200 or len(raw) > 1024 * 1024:
                raise TransportError()
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("ok") is not True:
                raise TransportError()
            return data["result"]
        except Exception:
            raise TransportError() from None
        finally:
            connection.close()

    def get_updates(self, offset):
        result = self._request("getUpdates", {"offset": offset, "timeout": 20, "limit": 20,
                                               "allowed_updates": ["message", "callback_query"]})
        if not isinstance(result, list) or len(result) > 20:
            raise TransportError()
        return result

    def send_message(self, chat_id, text, markup=None):
        payload = {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}}
        if markup:
            payload["reply_markup"] = markup
        result = self._request("sendMessage", payload)
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if type(message_id) is not int or message_id <= 0:
            raise TransportError()
        return message_id

    def answer_callback(self, callback_id):
        self._request("answerCallbackQuery", {"callback_query_id": callback_id})

    def send_typing(self, chat_id):
        self._request("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    def remove_inline_keyboard(self, chat_id, message_id):
        self._request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                 "reply_markup": {"inline_keyboard": []}})

    def send_photo(self, chat_id, text, image, markup=None):
        boundary = uuid4().hex
        fields = {"chat_id": str(chat_id), "caption": text}
        if markup:
            fields["reply_markup"] = json.dumps(markup)
        body = bytearray()
        for name, value in fields.items():
            body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
        body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="preview.jpg"\r\n'
                     'Content-Type: image/jpeg\r\n\r\n').encode())
        body.extend(image)
        body.extend(f'\r\n--{boundary}--\r\n'.encode())
        connection = self._connection()
        try:
            connection.request("POST", "/bot" + self.token.get_secret_value() + "/sendPhoto", body=bytes(body),
                               headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
            response = connection.getresponse()
            raw = response.read(64 * 1024 + 1)
            if response.status != 200 or len(raw) > 64 * 1024:
                raise TransportError()
            data = json.loads(raw)
            message_id = data.get("result", {}).get("message_id")
            if data.get("ok") is not True or type(message_id) is not int or message_id <= 0:
                raise TransportError()
            return message_id
        except Exception:
            raise TransportError() from None
        finally:
            connection.close()

    def download(self, file_id, limit):
        info = self._request("getFile", {"file_id": file_id})
        if not isinstance(info, dict):
            raise TransportError()
        size = info.get("file_size")
        if type(size) is int and size > limit:
            raise DownloadLimit()
        path = info.get("file_path")
        if not isinstance(path, str) or len(path) > 512 or not re.fullmatch(r"[A-Za-z0-9_./-]+", path) \
                or path.startswith("/") or ".." in path.split("/"):
            raise TransportError()
        connection = self._connection()
        try:
            connection.request("GET", "/file/bot" + self.token.get_secret_value() + "/" + path)
            response = connection.getresponse()
            if response.status != 200:
                raise TransportError()
            declared = response.getheader("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) > limit):
                raise DownloadLimit()
            content = bytearray()
            deadline = time.monotonic() + 60
            while True:
                if time.monotonic() > deadline:
                    raise TransportError()
                chunk = response.read(min(64 * 1024, limit + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > limit:
                    raise DownloadLimit()
            return bytes(content)
        except DownloadLimit:
            raise
        except Exception:
            raise TransportError() from None
        finally:
            connection.close()
