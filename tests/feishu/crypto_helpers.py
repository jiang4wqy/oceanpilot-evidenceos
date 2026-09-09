"""Synthetic sender-side envelopes matching Feishu's documented AES wire format."""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def encrypted_body(payload, encrypt_key, *, plaintext=None):
    raw = json.dumps(payload, ensure_ascii=False).encode() if plaintext is None else plaintext
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    iv = os.urandom(16)
    sender = Cipher(algorithms.AES(hashlib.sha256(encrypt_key.encode()).digest()), modes.CBC(iv))
    encryptor = sender.encryptor()
    cipher = encryptor.update(padded) + encryptor.finalize()
    return json.dumps({"encrypt": base64.b64encode(iv + cipher).decode()}).encode()
