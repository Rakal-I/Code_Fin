"""Authentificateur logiciel (équivalent de Face ID pour les tests) : signe comme un iPhone, en ES256."""
from __future__ import annotations

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


class FakeAuthenticator:
    def __init__(self, origin: str = "http://testserver", rp_id: str = "testserver"):
        self.origin, self.rp_id = origin, rp_id
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.user_handle: bytes | None = None
        self.sign_count = 0

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin}).encode()

    def _rp_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode()).digest()

    def create(self, options: dict) -> dict:
        """navigator.credentials.create : options telles que renvoyées par le serveur (JSON)."""
        self.user_handle = options["user"]["id"]
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
        auth_data = (self._rp_hash() + bytes([0x45]) + struct.pack(">I", 0) + bytes(16)
                     + struct.pack(">H", len(self.credential_id)) + self.credential_id + cose)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"])
        return {"id": bytes_to_base64url(self.credential_id), "rawId": bytes_to_base64url(self.credential_id),
                "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": bytes_to_base64url(client_data),
                             "attestationObject": bytes_to_base64url(attestation), "transports": ["internal"]}}

    def get(self, options: dict, user_verified: bool = True) -> dict:
        """navigator.credentials.get : signature du défi (Face ID réussi si user_verified)."""
        self.sign_count += 1
        flags = 0x05 if user_verified else 0x01
        auth_data = self._rp_hash() + bytes([flags]) + struct.pack(">I", self.sign_count)
        client_data = self._client_data("webauthn.get", options["challenge"])
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": bytes_to_base64url(self.credential_id), "rawId": bytes_to_base64url(self.credential_id),
                "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": bytes_to_base64url(client_data),
                             "authenticatorData": bytes_to_base64url(auth_data),
                             "signature": bytes_to_base64url(signature), "userHandle": self.user_handle}}
