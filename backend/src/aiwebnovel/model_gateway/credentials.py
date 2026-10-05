"""Windows user-level DPAPI; unsupported platforms fail closed."""

import ctypes
import hashlib
import os
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

from aiwebnovel.model_gateway.errors import ModelCredentialUnavailable


class CredentialProtector(Protocol):
    def protect(self, value: bytes, scope: bytes) -> bytes: ...

    def unprotect(self, value: bytes, scope: bytes) -> bytes: ...


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def credential_scope(data_root: Path, profile_id: str) -> bytes:
    root = os.path.normcase(os.path.normpath(str(data_root)))
    return hashlib.sha256(f"AIWebNovel/model-key/v1\0{root}\0{profile_id}".encode()).digest()


class WindowsDPAPIProtector:
    def protect(self, value: bytes, scope: bytes) -> bytes:
        return self._transform(value, scope, decrypt=False)

    def unprotect(self, value: bytes, scope: bytes) -> bytes:
        return self._transform(value, scope, decrypt=True)

    @staticmethod
    def _transform(value: bytes, scope: bytes, *, decrypt: bool) -> bytes:
        if os.name != "nt":
            raise ModelCredentialUnavailable
        value_buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        scope_buffer = (ctypes.c_ubyte * len(scope)).from_buffer_copy(scope)
        source = _Blob(len(value), value_buffer)
        entropy = _Blob(len(scope), scope_buffer)
        target = _Blob()
        # No CRYPTPROTECT_LOCAL_MACHINE: only the current Windows user can decrypt.
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        operation.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        try:
            if not operation(
                ctypes.byref(source),
                None,
                ctypes.byref(entropy),
                None,
                None,
                1,
                ctypes.byref(target),
            ):
                raise ModelCredentialUnavailable
            return ctypes.string_at(target.data, target.size)
        finally:
            if target.data:
                kernel32.LocalFree(target.data)
            ctypes.memset(value_buffer, 0, len(value))
