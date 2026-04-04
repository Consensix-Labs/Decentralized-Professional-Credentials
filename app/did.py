"""
DID module -- did:key generation and resolution.

A did:key encodes a public key directly in the identifier, so resolving it
requires no network calls. We use Ed25519 keys, which produce compact DIDs
and are widely supported across both EVM and IOTA ecosystems.

Format: did:key:z6Mk<base58-encoded-public-key>
The "z6Mk" prefix identifies Ed25519 keys per the did:key specification.
"""

import base64
import json
import base58
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


# Multicodec prefix for Ed25519 public keys (0xed01)
_ED25519_MULTICODEC_PREFIX = b"\xed\x01"


def generate_keypair():
    """Generate a new Ed25519 keypair and return (did, private_key_bytes).

    The DID is a fully formed did:key string. The private key bytes are
    the raw 32-byte Ed25519 seed, suitable for storage or passing to
    load_private_key().
    """
    private_key = Ed25519PrivateKey.generate()
    did = _public_key_to_did(private_key.public_key())
    private_bytes = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    return did, private_bytes


def load_private_key(private_bytes):
    """Reconstruct an Ed25519 private key from raw 32-byte seed."""
    return Ed25519PrivateKey.from_private_bytes(private_bytes)


def did_to_public_key(did):
    """Extract the Ed25519 public key from a did:key string.

    Used by verifiers to validate credential signatures without any
    network calls -- the public key is embedded in the DID itself.
    """
    if not did.startswith("did:key:z"):
        raise ValueError(f"Unsupported DID format: {did}")

    # Strip the "did:key:" prefix, decode the multibase (z = base58btc)
    multibase_value = did[len("did:key:z"):]
    decoded = base58.b58decode(multibase_value)

    # Strip the multicodec prefix
    if not decoded.startswith(_ED25519_MULTICODEC_PREFIX):
        raise ValueError(f"Not an Ed25519 did:key: {did}")

    raw_public = decoded[len(_ED25519_MULTICODEC_PREFIX):]
    return Ed25519PublicKey.from_public_bytes(raw_public)


def private_key_to_did(private_key):
    """Derive the did:key from an Ed25519 private key."""
    return _public_key_to_did(private_key.public_key())


def get_kid(did):
    """Return the key ID (kid) for JWT headers.

    Per did:key convention, the kid is the DID with a fragment referencing
    the key itself: did:key:z6Mk...#z6Mk...
    """
    key_id = did.split(":")[-1]
    return f"{did}#{key_id}"


def _public_key_to_did(public_key):
    """Convert an Ed25519 public key to a did:key string."""
    raw_public = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    multicodec_bytes = _ED25519_MULTICODEC_PREFIX + raw_public
    multibase_encoded = "z" + base58.b58encode(multicodec_bytes).decode("ascii")
    return f"did:key:{multibase_encoded}"


def save_keypair(directory, name, did, private_bytes):
    """Save a keypair to disk as a JSON file.

    Stores the DID and the base64-encoded private key in a simple JSON
    format. This is for PoC convenience -- a production system would use
    proper key management.
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)

    data = {
        "did": did,
        "privateKey": base64.b64encode(private_bytes).decode("ascii"),
    }

    filepath = path / f"{name}.json"
    filepath.write_text(json.dumps(data, indent=2) + "\n")
    return filepath


def load_keypair(filepath):
    """Load a keypair from a JSON file. Returns (did, private_key)."""
    data = json.loads(Path(filepath).read_text())
    private_bytes = base64.b64decode(data["privateKey"])
    return data["did"], load_private_key(private_bytes)
