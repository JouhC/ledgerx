# token_cipher.py
import json
import os
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken

class TokenCipher:
    """
    Simple AEAD wrapper around Fernet with key rotation.
    Env var: LEDGERX_KMS_KEYS='{"current":"v1","keys":{"v1":"<fernet_key_b64>","v0":"<old_key>"}}'
    """

    def __init__(self, env_var: str = "LEDGERX_KMS_KEYS") -> None:
        raw = os.getenv(env_var)
        if not raw:
            raise RuntimeError(f"{env_var} not set")
        cfg = json.loads(raw)
        self.current_kid: str = cfg["current"]
        self._fernets = {
            kid: Fernet(key.encode() if isinstance(key, str) else key)
            for kid, key in cfg["keys"].items()
        }
        if self.current_kid not in self._fernets:
            raise RuntimeError(f"current kid {self.current_kid} missing in keys")

    def encrypt(self, plaintext: bytes) -> Tuple[str, bytes]:
        """
        Returns (kid, ciphertext). Store both in DB.
        """
        f = self._fernets[self.current_kid]
        ct = f.encrypt(plaintext)  # includes nonce & timestamp, AEAD protected
        return self.current_kid, ct

    def decrypt(self, kid: Optional[str], ciphertext: bytes) -> bytes:
        """
        Decrypts using the specified key; if kid is None or not found,
        tries all known keys (handy for legacy rows).
        """
        # Preferred: use the kid
        if kid and kid in self._fernets:
            return self._fernets[kid].decrypt(ciphertext)
        # Fallback: try all keys (for legacy rows without kid)
        last_err = None
        for f in self._fernets.values():
            try:
                return f.decrypt(ciphertext)
            except InvalidToken as e:
                last_err = e
        raise InvalidToken("All keys failed") from last_err

    def needs_rotation(self, kid: Optional[str]) -> bool:
        return kid != self.current_kid

    def rotate(self, ciphertext: bytes) -> Tuple[str, bytes]:
        """
        Decrypt with any key, re-encrypt with current key. Return (new_kid, new_ct).
        """
        pt = self.decrypt(kid=None, ciphertext=ciphertext)
        return self.encrypt(pt)
