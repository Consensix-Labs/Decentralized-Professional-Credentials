"""
Credential module -- W3C Verifiable Credentials v2.0 as JWTs.

Creates, signs, verifies, and hashes credentials following the VC Data Model
v2.0 (W3C Recommendation, May 2025) secured with VC-JOSE-COSE (JWT envelope).

Key design decisions:
- The full credential IS the JWT payload (no "vc" wrapper -- that was v1.1).
- validFrom/validUntil are credential validity; JWT iat/exp are signature validity.
- Flat credentialSubject fields enable future per-field selective disclosure.
- SHA-256 of the complete signed JWT is the on-chain anchor hash.
"""

import hashlib
import json
import time
from datetime import datetime, timezone

import jwt  # PyJWT

from did import get_kid, did_to_public_key, private_key_to_did


# --- Credential type definitions ---
# Each type maps to a set of expected fields in credentialSubject.
# Used for validation when creating credentials.

CREDENTIAL_TYPES = {
    "EmploymentCredential": {
        "required": ["employerName", "role", "startDate", "endDate"],
        "optional": ["department", "employmentType"],
    },
    "CertificationCredential": {
        "required": ["certificationName", "certifyingBody", "dateAwarded"],
        "optional": ["level"],
    },
    "PeerEndorsement": {
        "required": ["endorserName", "relationship", "skills", "statement"],
        "optional": ["context"],
    },
}


def create_credential(credential_type, issuer_did, holder_did, claims,
                       valid_from=None, valid_until=None):
    """Build a VC v2.0 payload (unsigned).

    Args:
        credential_type: One of the keys in CREDENTIAL_TYPES.
        issuer_did: The issuer's did:key string.
        holder_did: The holder/subject's did:key string.
        claims: Dict of credentialSubject fields (excluding "id").
        valid_from: ISO 8601 datetime string, or None for current time.
        valid_until: ISO 8601 datetime string, or None for no expiration.

    Returns:
        Dict representing the VC payload ready to be signed as a JWT.
    """
    if credential_type not in CREDENTIAL_TYPES:
        raise ValueError(
            f"Unknown credential type: {credential_type}. "
            f"Supported: {list(CREDENTIAL_TYPES.keys())}"
        )

    type_def = CREDENTIAL_TYPES[credential_type]
    missing = [f for f in type_def["required"] if f not in claims]
    if missing:
        raise ValueError(
            f"Missing required fields for {credential_type}: {missing}"
        )

    if valid_from is None:
        valid_from = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build the credentialSubject with holder ID first, then claims
    subject = {"id": holder_did}
    subject.update(claims)

    payload = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "type": ["VerifiableCredential", credential_type],
        "issuer": issuer_did,
        "validFrom": valid_from,
        "credentialSubject": subject,
    }

    if valid_until is not None:
        payload["validUntil"] = valid_until

    return payload


def sign_credential(payload, private_key):
    """Sign a VC payload as a JWT using the issuer's Ed25519 key.

    The JWT header includes:
    - alg: EdDSA (Ed25519)
    - typ: vc+ld+jwt (per VC-JOSE-COSE spec)
    - kid: did:key fragment pointing to the signing key

    Returns the compact JWT string (header.payload.signature).
    """
    issuer_did = payload["issuer"]

    # Verify the private key matches the claimed issuer DID
    derived_did = private_key_to_did(private_key)
    if derived_did != issuer_did:
        raise ValueError(
            f"Private key does not match issuer DID. "
            f"Key produces {derived_did}, payload claims {issuer_did}"
        )

    headers = {
        "alg": "EdDSA",
        "typ": "vc+ld+jwt",
        "kid": get_kid(issuer_did),
    }

    # PyJWT expects the signing key in the right format
    token = jwt.encode(
        payload,
        private_key,
        algorithm="EdDSA",
        headers=headers,
    )

    return token


def verify_credential_signature(token):
    """Verify the JWT signature and decode the payload.

    Extracts the issuer DID from the JWT header's kid, resolves it to
    a public key (no network call needed for did:key), and verifies
    the signature.

    Returns the decoded payload dict if valid, raises on failure.
    """
    # Decode header without verification to get the kid
    unverified_header = jwt.get_unverified_header(token)

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid' claim")

    # Extract DID from kid (format: did:key:z6Mk...#z6Mk...)
    issuer_did = kid.split("#")[0]

    # Resolve did:key to public key -- pure computation, no network
    public_key = did_to_public_key(issuer_did)

    # Verify signature and decode
    payload = jwt.decode(
        token,
        public_key,
        algorithms=["EdDSA"],
        options={
            # We handle validity checking ourselves via on-chain status
            "verify_exp": False,
            "verify_iat": False,
        },
    )

    return payload


def hash_credential(token):
    """Compute the SHA-256 hash of a signed JWT credential.

    This hash is what gets anchored on-chain. Hashing the complete signed
    JWT (not just the payload) means every credential has a unique hash
    even if two issuers create identical claims -- the different signatures
    produce different hashes.

    Returns the hash as a bytes32-compatible hex string (0x-prefixed).
    """
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return "0x" + digest.hex()


def credential_expiration_timestamp(payload):
    """Extract the expiration as a Unix timestamp for on-chain registration.

    Returns 0 if the credential has no validUntil (no expiration).
    """
    valid_until = payload.get("validUntil")
    if valid_until is None:
        return 0

    dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
    return int(dt.timestamp())


def format_credential_summary(payload):
    """Human-readable one-line summary of a credential for CLI output."""
    cred_type = payload["type"][1]  # second element is the specific type
    issuer = payload["issuer"]
    subject = payload["credentialSubject"]

    if cred_type == "EmploymentCredential":
        return (
            f"Employment: {subject.get('role', '?')} at "
            f"{subject.get('employerName', '?')} "
            f"({subject.get('startDate', '?')} to {subject.get('endDate', '?')})"
        )
    elif cred_type == "CertificationCredential":
        return (
            f"Certification: {subject.get('certificationName', '?')} "
            f"from {subject.get('certifyingBody', '?')}"
        )
    elif cred_type == "PeerEndorsement":
        skills = ", ".join(subject.get("skills", []))
        return (
            f"Endorsement: {subject.get('endorserName', '?')} endorses "
            f"[{skills}]"
        )
    else:
        return f"{cred_type} issued by {issuer}"
