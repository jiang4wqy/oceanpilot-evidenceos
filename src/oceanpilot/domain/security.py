import re
from collections.abc import Mapping, Sequence, Set

from pydantic import BaseModel

from oceanpilot.domain.errors import SensitiveDataRejected

_AUTHORIZATION_PATTERN = re.compile(
    r"\b(?:bearer\s+\S+|authorization\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_ASSIGNMENT_PATTERN = re.compile(
    r"(?<![$A-Za-z0-9_.-])(?:"
    r"(?P<quote>['\"])(?P<quoted_key>[^'\"]+)(?P=quote)"
    r"|(?P<plain_key>[$A-Za-z_][$A-Za-z0-9_.-]*))"
    r"\s*[:=](?=\s*\S)"
)
_CAMEL_CASE_BOUNDARY_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_KEY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_SENSITIVE_KEY_TOKENS = frozenset(
    {"authorization", "bearer", "cvc", "cvv", "key", "passwd", "password", "secret", "token"}
)
_SENSITIVE_COMPACT_KEYS = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "authtoken",
        "clientsecret",
        "privatekey",
        "secretkey",
        "userpassword",
    }
)
_SAFE_METADATA_SUFFIXES = frozenset({"count", "length", "present", "status", "type"})
_CARD_CANDIDATE_PATTERN = re.compile(
    r"(?<!\d)(?<!\d[ \t\u00a0-])(?:\d[ \t\u00a0-]?){12,18}\d(?!\d)(?![ \t\u00a0-]\d)"
)
_UUID_IDENTIFIER_FIELDS = frozenset(
    {
        "case_id",
        "evidence_id",
        "diagnosis_id",
        "current_diagnosis_id",
        "hypothesis_id",
        "event_id",
        "request_id",
        "trace_id",
        "correlation_id",
    }
)
# Fields holding a list/tuple of UUID4 identifiers (not scalars). Their elements
# are key-less when scanned, so the scalar allowlist above can't reach them; a
# uuid whose digits happen to pass Luhn would otherwise be a false positive.
# Each element must still be an exact UUID4 (embedded/prefixed values are not
# trusted), preserving the same policy as the scalar identifier fields.
_UUID_IDENTIFIER_LIST_FIELDS = frozenset({"evidence_refs"})
_UUID4_IDENTIFIER_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_CONTENT_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def _passes_luhn(candidate: str) -> bool:
    digits = [int(character) for character in candidate if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _is_sensitive_key(value: str) -> bool:
    normalized = _CAMEL_CASE_BOUNDARY_PATTERN.sub("_", value)
    tokens = tuple(token.lower() for token in _KEY_TOKEN_PATTERN.findall(normalized))
    if not tokens or tokens[-1] in _SAFE_METADATA_SUFFIXES:
        return False
    singular_tokens = tuple(
        token[:-1] if token.endswith("s") and token[:-1] in _SENSITIVE_KEY_TOKENS else token
        for token in tokens
    )
    compact_key = "".join(tokens)
    if compact_key.endswith("s"):
        compact_key = compact_key[:-1]
    return bool(_SENSITIVE_KEY_TOKENS.intersection(singular_tokens)) or (
        compact_key in _SENSITIVE_COMPACT_KEYS
    )


def _is_trusted_derived_value(key: object, value: object) -> bool:
    if not isinstance(key, str) or not isinstance(value, str):
        return False
    return (
        key in _UUID_IDENTIFIER_FIELDS and _UUID4_IDENTIFIER_PATTERN.fullmatch(value) is not None
    ) or (key == "content_hash" and _CONTENT_HASH_PATTERN.fullmatch(value) is not None)


def _is_trusted_identifier_list(key: object, value: object) -> bool:
    if not isinstance(key, str) or key not in _UUID_IDENTIFIER_LIST_FIELDS:
        return False
    if not isinstance(value, (Sequence, Set)) or isinstance(value, (str, bytes, bytearray)):
        return False
    return all(
        isinstance(item, str) and _UUID4_IDENTIFIER_PATTERN.fullmatch(item) is not None
        for item in value
    )


def _contains_sensitive_value(value: object, visited: set[int]) -> bool:
    if isinstance(value, str):
        return _contains_sensitive_data(value)

    if isinstance(value, BaseModel):
        return _contains_sensitive_value(value.model_dump(mode="python"), visited)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in visited:
            return False
        visited.add(identity)
        for key, item in value.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                return True
            if _contains_sensitive_value(key, visited):
                return True
            if _is_trusted_derived_value(key, item) or _is_trusted_identifier_list(key, item):
                continue
            if _contains_sensitive_value(item, visited):
                return True
        return False

    if isinstance(value, (Sequence, Set)) and not isinstance(value, (bytes, bytearray)):
        identity = id(value)
        if identity in visited:
            return False
        visited.add(identity)
        return any(_contains_sensitive_value(item, visited) for item in value)

    return False


def _contains_sensitive_data(value: str) -> bool:
    if _AUTHORIZATION_PATTERN.search(value):
        return True
    for match in _ASSIGNMENT_PATTERN.finditer(value):
        key = match.group("quoted_key") or match.group("plain_key")
        if _is_sensitive_key(key):
            return True
    return any(_passes_luhn(match.group()) for match in _CARD_CANDIDATE_PATTERN.finditer(value))


def assert_no_sensitive_data(value: object) -> None:
    if _contains_sensitive_value(value, set()):
        raise SensitiveDataRejected
