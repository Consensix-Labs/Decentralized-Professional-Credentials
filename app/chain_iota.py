"""
IOTA chain backend -- publish, deploy, and interact with credential_registry on IOTA Rebased.

Uses pure HTTP requests against the IOTA JSON-RPC API. No TypeScript SDK or
CLI shelling -- this is an honest demonstration of what Python-only IOTA
development looks like today, and a key developer-experience finding for the
research paper.

The signing flow follows IOTA's intent-signing scheme:
  1. unsafe_* APIs build an unsigned transaction (returns base64 tx_bytes)
  2. We prepend the 3-byte intent prefix [0, 0, 0] to the raw tx_bytes
  3. Blake2b-256 hash the intent message to get a 32-byte digest
  4. Ed25519 sign the digest
  5. Encode the signature as base64(flag || sig || pk) where flag=0x00
  6. Submit via iota_executeTransactionBlock

Connection details and key material come from environment variables.
"""

import base64
import hashlib
import os
from pathlib import Path

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# IOTA Move contract source directory, relative to this file.
# Inside the Docker container, both CLI and contracts live under /app/.
MOVE_PACKAGE_PATH = Path(__file__).parent / "contracts" / "iota"

# Well-known object IDs on the IOTA network
CLOCK_OBJECT_ID = "0x0000000000000000000000000000000000000000000000000000000000000006"

# Intent bytes for transaction signing: [scope=TransactionData, version=V0, app_id=Iota]
_INTENT_BYTES = bytes([0, 0, 0])

# Ed25519 signature scheme flag for IOTA
_ED25519_FLAG = 0x00

# Gas budget for transactions (in NANOS). Generous for a local testnet.
_DEFAULT_GAS_BUDGET = "100000000"


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _rpc_url():
    """Get the IOTA full node RPC URL from environment."""
    url = os.environ.get("IOTA_RPC_URL")
    if not url:
        raise RuntimeError("IOTA_RPC_URL environment variable not set")
    return url


def _rpc_call(method, params=None):
    """Make a JSON-RPC call to the IOTA full node.

    Returns the 'result' field on success, raises on error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }

    resp = requests.post(_rpc_url(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(
            f"RPC error in {method}: {data['error'].get('message', data['error'])}"
        )

    return data["result"]


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _decode_iota_privkey(privkey_bech32):
    """Decode an 'iotaprivkey1...' bech32-encoded private key.

    The keystore format is bech32 with HRP 'iotaprivkey'. The decoded payload
    is 33 bytes: 1-byte scheme flag (0x00 for Ed25519) followed by 32 bytes
    of raw private key seed.

    Returns an Ed25519PrivateKey object.
    """
    import bech32

    hrp, data_5bit = bech32.bech32_decode(privkey_bech32)
    if hrp != "iotaprivkey":
        raise ValueError(f"Unexpected HRP: {hrp} (expected 'iotaprivkey')")

    raw_bytes = bytes(bech32.convertbits(data_5bit, 5, 8, False))

    # First byte is the scheme flag (0x00 = Ed25519)
    if raw_bytes[0] != _ED25519_FLAG:
        raise ValueError(f"Unsupported key scheme flag: {raw_bytes[0]:#x}")

    seed = raw_bytes[1:33]
    return Ed25519PrivateKey.from_private_bytes(seed)


def _load_private_key(private_key_input):
    """Load an IOTA Ed25519 private key from various formats.

    Accepts:
      - 'iotaprivkey1...' bech32 string (from IOTA keystore)
      - Raw 32-byte hex string
      - 64-byte hex string (seed + public key, takes first 32 bytes)
    """
    if private_key_input.startswith("iotaprivkey"):
        return _decode_iota_privkey(private_key_input)

    # Hex-encoded: strip 0x prefix if present
    hex_key = private_key_input.removeprefix("0x")

    if len(hex_key) == 64:
        # 32 bytes hex
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_key))
    elif len(hex_key) == 128:
        # 64 bytes hex (seed + pubkey) -- take the seed
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_key[:64]))
    else:
        raise ValueError(
            f"Unrecognized private key format (length {len(hex_key)} hex chars)"
        )


def _get_public_key_bytes(private_key):
    """Extract the 32-byte raw Ed25519 public key."""
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _get_address(private_key):
    """Derive the IOTA address from an Ed25519 private key.

    IOTA addresses are the Blake2b-256 hash of the scheme flag byte (0x00 for
    Ed25519) followed by the 32-byte public key, making 33 bytes total.
    Returns a 0x-prefixed hex string.
    """
    pub_bytes = _get_public_key_bytes(private_key)
    # Prepend the Ed25519 scheme flag so derived addresses match the IOTA CLI/SDK
    flag_and_key = b"\x00" + pub_bytes
    address_bytes = hashlib.blake2b(flag_and_key, digest_size=32).digest()
    return "0x" + address_bytes.hex()


# ---------------------------------------------------------------------------
# Transaction signing
# ---------------------------------------------------------------------------

def _sign_transaction(tx_bytes_b64, private_key):
    """Sign an IOTA transaction using the intent-signing scheme.

    Args:
        tx_bytes_b64: Base64-encoded BCS transaction data from an unsafe_* call.
        private_key: Ed25519PrivateKey instance.

    Returns:
        Base64-encoded serialized signature (flag || sig || pk).
    """
    tx_bytes = base64.b64decode(tx_bytes_b64)

    # Prepend the 3-byte intent prefix to the raw transaction bytes
    intent_message = _INTENT_BYTES + tx_bytes

    # Blake2b-256 hash to get the 32-byte digest
    digest = hashlib.blake2b(intent_message, digest_size=32).digest()

    # Ed25519 sign the digest
    signature = private_key.sign(digest)

    # Serialized format: flag (1 byte) || signature (64 bytes) || public key (32 bytes)
    pub_bytes = _get_public_key_bytes(private_key)
    serialized = bytes([_ED25519_FLAG]) + signature + pub_bytes

    return base64.b64encode(serialized).decode("ascii")


def _execute_transaction(tx_bytes_b64, signature_b64):
    """Submit a signed transaction for execution.

    Returns the full transaction response including effects and events.
    """
    return _rpc_call("iota_executeTransactionBlock", [
        tx_bytes_b64,
        [signature_b64],
        {
            "showEffects": True,
            "showEvents": True,
            "showObjectChanges": True,
        },
        "WaitForLocalExecution",
    ])


def _sign_and_execute(tx_bytes_b64, private_key):
    """Sign a transaction and execute it. Returns the transaction response."""
    sig = _sign_transaction(tx_bytes_b64, private_key)
    return _execute_transaction(tx_bytes_b64, sig)


def _check_tx_success(response):
    """Verify a transaction executed successfully, raise with details if not."""
    effects = response.get("effects", {})
    status = effects.get("status", {})

    if status.get("status") != "success":
        error_msg = status.get("error", "unknown error")
        raise RuntimeError(f"Transaction failed: {error_msg}")


# ---------------------------------------------------------------------------
# Gas coin selection
# ---------------------------------------------------------------------------

def _get_gas_coin(address):
    """Find a gas coin owned by the given address.

    Returns the object ID of the coin with the highest balance.
    """
    result = _rpc_call("iotax_getCoins", [address])
    coins = result.get("data", [])

    if not coins:
        raise RuntimeError(f"No gas coins found for address {address}")

    # Pick the coin with the highest balance
    best = max(coins, key=lambda c: int(c["balance"]))
    return best["coinObjectId"]


# ---------------------------------------------------------------------------
# Package publishing (deploy)
# ---------------------------------------------------------------------------

def _compile_move_package(package_path):
    """Compile a Move package and return the list of base64-encoded module bytecodes.

    Uses 'iota move build' via the iota-tools Docker container. The compiled
    bytecode files are read from the build output directory.

    This is necessary because there's no Python Move compiler -- the build
    step must go through the IOTA toolchain. The scenario script handles this
    by running the build before calling deploy.

    Returns:
        List of base64-encoded module bytecode strings.
    """
    # The build output lives at <package>/build/<package_name>/bytecode_modules/
    build_dir = package_path / "build" / "credential_registry" / "bytecode_modules"

    if not build_dir.exists():
        raise RuntimeError(
            f"Compiled Move bytecode not found at {build_dir}. "
            f"Run 'iota move build' on the package first (the scenario script "
            f"handles this automatically)."
        )

    modules = []
    for bytecode_file in sorted(build_dir.glob("*.mv")):
        raw = bytecode_file.read_bytes()
        modules.append(base64.b64encode(raw).decode("ascii"))

    if not modules:
        raise RuntimeError(f"No .mv files found in {build_dir}")

    return modules


def deploy_contract(private_key_input):
    """Publish the Move package and return the shared Registry object ID.

    The init() function in credential_registry.move creates a shared Registry
    object during publication. We find it in the transaction effects.

    Args:
        private_key_input: IOTA private key (iotaprivkey1... or hex).

    Returns:
        A string formatted as "PACKAGE_ID:REGISTRY_ID" so both IDs can be
        extracted by the caller. The scenario script parses this to set
        environment variables for subsequent commands.
    """
    private_key = _load_private_key(private_key_input)
    sender = _get_address(private_key)
    gas_coin = _get_gas_coin(sender)

    modules = _compile_move_package(MOVE_PACKAGE_PATH)

    # IOTA framework dependency -- the package ID for the iota-framework
    # on a local test network. 0x2 is the standard framework address.
    dependencies = ["0x0000000000000000000000000000000000000000000000000000000000000001",
                    "0x0000000000000000000000000000000000000000000000000000000000000002"]

    result = _rpc_call("unsafe_publish", [
        sender,
        modules,
        dependencies,
        gas_coin,
        _DEFAULT_GAS_BUDGET,
    ])

    tx_bytes = result["txBytes"]
    response = _sign_and_execute(tx_bytes, private_key)
    _check_tx_success(response)

    # Extract the package ID and Registry object ID from object changes
    package_id = None
    registry_id = None

    for change in response.get("objectChanges", []):
        if change.get("type") == "published":
            package_id = change["packageId"]
        elif change.get("type") == "created":
            obj_type = change.get("objectType", "")
            if "Registry" in obj_type:
                registry_id = change["objectId"]

    if not package_id:
        raise RuntimeError("Could not find published package ID in transaction effects")
    if not registry_id:
        raise RuntimeError("Could not find shared Registry object ID in transaction effects")

    # Return both IDs separated by colon -- the scenario script will parse this
    return f"{package_id}:{registry_id}"


# ---------------------------------------------------------------------------
# Write operations (register, revoke)
# ---------------------------------------------------------------------------

def _get_registry_and_package():
    """Read the registry object ID and package ID from environment.

    IOTA_CONTRACT_ADDRESS is expected to be "PACKAGE_ID:REGISTRY_ID".
    """
    contract_address = os.environ.get("IOTA_CONTRACT_ADDRESS")
    if not contract_address:
        raise RuntimeError("IOTA_CONTRACT_ADDRESS environment variable not set")

    return _parse_contract_address(contract_address)


def _parse_contract_address(contract_address):
    """Split a 'PACKAGE_ID:REGISTRY_ID' string into its two parts."""
    parts = contract_address.split(":")
    if len(parts) != 2:
        raise RuntimeError(
            f"IOTA_CONTRACT_ADDRESS must be 'PACKAGE_ID:REGISTRY_ID', got: {contract_address}"
        )
    return parts[0], parts[1]


def _resolve_package_and_registry(contract_address=None):
    """Get package_id and registry_id from an explicit override or the environment."""
    if contract_address:
        return _parse_contract_address(contract_address)
    return _get_registry_and_package()


def register_credential(private_key, credential_hash, issuer_did, expiration,
                         contract_address=None):
    """Register a credential hash on the IOTA registry.

    Args:
        private_key: IOTA private key (iotaprivkey1... or hex).
        credential_hash: 0x-prefixed hex string (SHA-256 hash of JWT).
        issuer_did: The issuer's did:key string.
        expiration: Unix timestamp in seconds (0 for no expiration).
                    Converted to milliseconds for IOTA's Clock resolution.
        contract_address: Optional "PACKAGE_ID:REGISTRY_ID" override.

    Returns:
        Transaction response dict (used by get_gas_used).
    """
    pk = _load_private_key(private_key)
    sender = _get_address(pk)
    gas_coin = _get_gas_coin(sender)

    package_id, registry_id = _resolve_package_and_registry(contract_address)

    # Convert credential hash from 0x-hex to a list of integers (IOTA JSON format
    # for vector<u8> accepts an array of numbers)
    hash_bytes = list(bytes.fromhex(credential_hash[2:]))

    # Convert expiration from seconds to milliseconds for IOTA's Clock
    expiration_ms = str(expiration * 1000) if expiration else "0"

    result = _rpc_call("unsafe_moveCall", [
        sender,                                                 # signer
        package_id,                                             # package
        "credential_registry",                                  # module
        "register_credential",                                  # function
        [],                                                     # type arguments
        [registry_id, hash_bytes, issuer_did, expiration_ms, CLOCK_OBJECT_ID],  # arguments
        gas_coin,                                               # gas object
        _DEFAULT_GAS_BUDGET,                                    # gas budget
    ])

    tx_bytes = result["txBytes"]
    response = _sign_and_execute(tx_bytes, pk)
    _check_tx_success(response)

    return response


def revoke_credential(private_key, credential_hash, contract_address=None):
    """Revoke a credential on the IOTA registry.

    Args:
        private_key: IOTA private key (must be the original registrant).
        credential_hash: 0x-prefixed hex string.
        contract_address: Optional "PACKAGE_ID:REGISTRY_ID" override.

    Returns:
        Transaction response dict.
    """
    pk = _load_private_key(private_key)
    sender = _get_address(pk)
    gas_coin = _get_gas_coin(sender)

    package_id, registry_id = _resolve_package_and_registry(contract_address)

    hash_bytes = list(bytes.fromhex(credential_hash[2:]))

    result = _rpc_call("unsafe_moveCall", [
        sender,
        package_id,
        "credential_registry",
        "revoke_credential",
        [],
        [registry_id, hash_bytes, CLOCK_OBJECT_ID],
        gas_coin,
        _DEFAULT_GAS_BUDGET,
    ])

    tx_bytes = result["txBytes"]
    response = _sign_and_execute(tx_bytes, pk)
    _check_tx_success(response)

    return response


# ---------------------------------------------------------------------------
# Read operations (status, validity)
#
# Rather than calling Move view functions (which would require devInspect
# or dry-run -- both problematic from Python on v1.1.0), we read credential
# records directly from the Registry's Table using dynamic field lookups.
# This is actually the more natural approach for IOTA's object model.
# ---------------------------------------------------------------------------


def _get_table_id(registry_id):
    """Read the Registry object and extract its inner Table's object ID.

    The Registry struct has a `records` field which is a Table. The Table's
    own object ID is what we need for dynamic field lookups.
    """
    result = _rpc_call("iota_getObject", [
        registry_id,
        {"showContent": True},
    ])

    data = result.get("data")
    if not data:
        raise RuntimeError(f"Registry object {registry_id} not found")

    content = data.get("content", {})
    fields = content.get("fields", {})
    records = fields.get("records", {})
    records_fields = records.get("fields", {})
    table_id = records_fields.get("id", {}).get("id")

    if not table_id:
        raise RuntimeError("Could not extract Table ID from Registry object")

    return table_id


def _read_credential_record(registry_id, credential_hash):
    """Read a credential record directly from the on-chain Table via dynamic fields.

    IOTA Tables store entries as dynamic fields on the Table's inner object.
    We use iotax_getDynamicFieldObject to look up a specific entry by its key
    (the credential hash as vector<u8>).

    Returns the parsed CredentialRecord fields dict, or None if not found.
    """
    table_id = _get_table_id(registry_id)

    # The dynamic field key type for our Table<vector<u8>, CredentialRecord>
    # The key is the credential hash bytes
    hash_bytes = list(bytes.fromhex(credential_hash[2:]))

    try:
        result = _rpc_call("iotax_getDynamicFieldObject", [
            table_id,
            {
                "type": "vector<u8>",
                "value": hash_bytes,
            },
        ])
    except RuntimeError:
        return None

    data = result.get("data")
    if not data:
        return None

    content = data.get("content", {})
    fields = content.get("fields", {})

    # The dynamic field object wraps the value in a "value" field
    value = fields.get("value", {})
    if isinstance(value, dict):
        value_fields = value.get("fields", value)
    else:
        value_fields = value

    return value_fields


def get_credential_status(credential_hash, contract_address=None):
    """Query the on-chain status of a credential.

    Reads the credential record directly from the Registry's Table using
    dynamic field lookups. This avoids the devInspect/dryRun limitations
    and is actually the more natural approach for object-based blockchains.

    Returns a dict with: exists, issuer, issuedAt, expiration, revoked, revokedAt.
    """
    _, registry_id = _resolve_package_and_registry(contract_address)

    record = _read_credential_record(registry_id, credential_hash)

    if record is None:
        return {
            "exists": False,
            "issuer": "",
            "issuedAt": 0,
            "expiration": 0,
            "revoked": False,
            "revokedAt": 0,
        }

    # Parse the record fields. IOTA timestamps are in milliseconds;
    # convert to seconds for consistency with the EVM backend.
    issued_at_ms = int(record.get("issued_at", 0))
    expiration_ms = int(record.get("expiration", 0))
    revoked_at_ms = int(record.get("revoked_at", 0))

    return {
        "exists": True,
        "issuer": record.get("issuer", ""),
        "issuedAt": issued_at_ms // 1000 if issued_at_ms else 0,
        "expiration": expiration_ms // 1000 if expiration_ms else 0,
        "revoked": record.get("revoked", False),
        "revokedAt": revoked_at_ms // 1000 if revoked_at_ms else 0,
    }


def _get_network_timestamp_ms():
    """Fetch the current IOTA network timestamp from the Clock object (0x6).

    Returns the timestamp in milliseconds, matching the resolution used by
    the Move contract. This ensures expiration checks are consistent with
    on-chain behavior rather than depending on the local system clock.
    """
    result = _rpc_call("iota_getObject", [
        "0x6",
        {"showContent": True},
    ])
    fields = result["data"]["content"]["fields"]
    return int(fields["timestamp_ms"])


def is_credential_valid(credential_hash, contract_address=None):
    """Check if a credential is currently valid on-chain.

    Returns True only if registered, not revoked, and not expired.
    Expiration is checked against the IOTA network Clock, matching the
    on-chain contract behavior (not the local system clock).
    """
    status = get_credential_status(credential_hash, contract_address)

    if not status["exists"]:
        return False

    if status["revoked"]:
        return False

    if status["expiration"] != 0:
        # Expiration is stored in seconds; Clock is in milliseconds
        network_time_s = _get_network_timestamp_ms() // 1000
        if status["expiration"] <= network_time_s:
            return False

    return True


# ---------------------------------------------------------------------------
# Cost metrics (for comparison with EVM)
#
# IOTA doesn't use "gas" the way EVM does -- costs are charged directly in
# NANOS (the smallest IOTA denomination) as computation + storage - rebate.
# The function name get_gas_used is kept for interface compatibility with
# the EVM backend and main.py's chain-agnostic calling convention.
# ---------------------------------------------------------------------------

def get_gas_used(response):
    """Extract transaction cost from an IOTA transaction response.

    IOTA reports costs in NANOS, broken into computation cost, storage cost,
    and storage rebate. The 'gasUsed' key is named for interface compatibility
    with the EVM backend.
    """
    effects = response.get("effects", {})
    gas_used = effects.get("gasUsed", {})

    computation = int(gas_used.get("computationCost", 0))
    storage = int(gas_used.get("storageCost", 0))
    rebate = int(gas_used.get("storageRebate", 0))

    return {
        "gasUsed": computation + storage - rebate,
        "computationCost": computation,
        "storageCost": storage,
        "storageRebate": rebate,
        "totalCost": computation + storage - rebate,
    }