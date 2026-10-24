"""Encrypt the YouTube refresh token for the current Windows user."""
import base64
import ctypes
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]


def _crypt(data, decrypt=False):
    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    crypt = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if decrypt:
        ok = crypt(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output))
    else:
        ok = crypt(ctypes.byref(source), 'StreamVault YouTube', None, None, None, 0, ctypes.byref(output))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def protect(token):
    return base64.b64encode(_crypt(token.encode('utf-8'))).decode('ascii')


def unprotect(encrypted):
    return _crypt(base64.b64decode(encrypted), True).decode('utf-8')
