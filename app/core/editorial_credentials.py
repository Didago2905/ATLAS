"""Dedicated Editorial Credential Manager target; no environment or network use."""
import ctypes
import getpass
import re
import sys
import warnings
from pydantic import SecretStr
# Reuse only the Windows ABI definitions. Never call Incidents read/enroll helpers.
from app.core.incidents_credentials import Credential, _api

TARGET = "ATLAS/Editorial/BotToken"


class EditorialCredentialUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Dedicated Editorial credential unavailable")


def read_token():
    result = ctypes.POINTER(Credential)()
    api = None
    try:
        api = _api()
        if not api.CredReadW(TARGET, 1, 0, ctypes.byref(result)):
            raise EditorialCredentialUnavailable()
        if not 0 < result.contents.CredentialBlobSize <= 1024:
            raise EditorialCredentialUnavailable()
        value = ctypes.string_at(result.contents.CredentialBlob, result.contents.CredentialBlobSize).decode("utf-16-le")
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", value):
            raise EditorialCredentialUnavailable()
        return SecretStr(value)
    except Exception:
        raise EditorialCredentialUnavailable() from None
    finally:
        if result and api:
            api.CredFree(result)


def enroll_token(value):
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", value):
        raise EditorialCredentialUnavailable()
    encoded = value.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    try:
        api = _api()
        credential = Credential(Type=1, TargetName=TARGET, CredentialBlobSize=len(encoded),
                                CredentialBlob=buffer, Persist=2, UserName="ATLAS Editorial")
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise EditorialCredentialUnavailable()
    except Exception:
        raise EditorialCredentialUnavailable() from None
    finally:
        ctypes.memset(buffer, 0, len(buffer))


def main():
    if sys.argv[1:] != ["enroll"]:
        print("Use: python -B -m app.core.editorial_credentials enroll")
        return 2
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("Editorial enrollment requires a local interactive terminal with hidden input")
        return 2
    value = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("Dedicated Editorial bot token (hidden): ")
        enroll_token(value)
        print("Dedicated Editorial credential stored for this Windows account; worker remains disabled")
        return 0
    except (Exception, KeyboardInterrupt):
        print("Editorial enrollment stopped; private details suppressed")
        return 2
    finally:
        value = None


if __name__ == "__main__":
    raise SystemExit(main())
