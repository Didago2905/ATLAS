"""Dedicated, opt-in Windows Credential Manager storage. No reads on import."""
import argparse
import ctypes
from ctypes import wintypes
import getpass
import os
import re
import sys

from pydantic import SecretStr

TARGET = "ATLAS/Incidents/BotToken"


class CredentialUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Dedicated Incidents credential unavailable")


class Credential(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


def _api():
    if os.name != "nt":
        raise CredentialUnavailable()
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    return api


def read_token():
    api = _api()
    result = ctypes.POINTER(Credential)()
    if not api.CredReadW(TARGET, 1, 0, ctypes.byref(result)):
        raise CredentialUnavailable()
    try:
        if not 0 < result.contents.CredentialBlobSize <= 1024:
            raise CredentialUnavailable()
        value = ctypes.string_at(result.contents.CredentialBlob, result.contents.CredentialBlobSize).decode("utf-16-le")
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", value):
            raise CredentialUnavailable()
        return SecretStr(value)
    finally:
        api.CredFree(result)


def enroll_token(value):
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", value):
        raise CredentialUnavailable()
    api = _api()
    encoded = value.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = Credential(Type=1, TargetName=TARGET, CredentialBlobSize=len(encoded),
                            CredentialBlob=buffer, Persist=2, UserName="ATLAS_Incidents_Bot")
    try:
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise CredentialUnavailable()
    finally:
        ctypes.memset(buffer, 0, len(buffer))


def main():
    parser = argparse.ArgumentParser(description="One-time dedicated Incidents credential enrollment")
    parser.add_argument("action", choices=["enroll"])
    parser.parse_args()
    if not sys.stdin.isatty():
        print("Enrollment requires a local interactive terminal with hidden input")
        return 2
    value = None
    try:
        value = getpass.getpass("Dedicated Incidents bot token (hidden): ")
        enroll_token(value)
        print("Dedicated credential stored for this Windows user; delivery was not enabled")
        return 0
    except Exception:
        print("Credential enrollment failed; private details suppressed")
        return 2
    finally:
        value = None


if __name__ == "__main__":
    raise SystemExit(main())
