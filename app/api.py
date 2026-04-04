"""
REST API for Decentralized Professional Credentials.

A thin FastAPI layer over the existing CLI modules (credential, did, chain_evm,
chain_iota). Provides the same credential lifecycle operations as the CLI but
as HTTP endpoints for the web interface.

Designed to run alongside the CLI in the same Docker image -- both share the
same Python modules, credential store, and key directory.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import credential as cred
import did as did_module

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CREDENTIALS_DIR = Path(os.environ.get("CREDENTIALS_DIR", "./credentials"))
KEYS_DIR = Path(os.environ.get("KEYS_DIR", "./keys"))

app = FastAPI(
    title="Decentralized Professional Credentials API",
    version="0.1.0",
)

# Allow the web frontend (running on a different port) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class GenerateKeyRequest(BaseModel):
    name: str


class KeyInfo(BaseModel):
    name: str
    did: str


class IssueRequest(BaseModel):
    credential_type: str  # "employment", "certification", "endorsement"
    issuer_key_name: str  # name of the keypair file (without .json)
    holder_did: str
    claims: dict
    valid_until: str | None = None


class IssuedCredential(BaseModel):
    filename: str
    token: str
    hash: str
    summary: str


class RegisterRequest(BaseModel):
    credential_filename: str
    chain: str  # "evm" or "iota"


class RevokeRequest(BaseModel):
    credential_hash: str
    chain: str


class VerifyRequest(BaseModel):
    token: str
    chain: str


class CredentialInfo(BaseModel):
    filename: str
    summary: str
    hash: str
    issuer: str
    holder: str
    credential_type: str
    valid_from: str | None = None
    valid_until: str | None = None


class CredentialTypeInfo(BaseModel):
    name: str
    internal_name: str
    required_fields: list[str]
    optional_fields: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_chain_backend(chain: str):
    """Import the appropriate chain backend, raising HTTP 400 for invalid chain."""
    if chain == "evm":
        import chain_evm
        return chain_evm
    elif chain == "iota":
        import chain_iota
        return chain_iota
    else:
        raise HTTPException(status_code=400, detail=f"Unknown chain: {chain}")


def _resolve_private_key(chain: str) -> str:
    """Read the issuer private key from chain-specific environment variables."""
    envvar_map = {
        "evm": "EVM_ISSUER_PRIVATE_KEY",
        "iota": "IOTA_ISSUER_PRIVATE_KEY",
    }
    envvar = envvar_map.get(chain, "")
    value = os.environ.get(envvar)
    if not value:
        raise HTTPException(
            status_code=500,
            detail=f"{envvar} not set in environment",
        )
    return value


TYPE_MAP = {
    "employment": "EmploymentCredential",
    "certification": "CertificationCredential",
    "endorsement": "PeerEndorsement",
}


# ---------------------------------------------------------------------------
# Key management endpoints
# ---------------------------------------------------------------------------

@app.get("/api/keys", response_model=list[KeyInfo])
def list_keys():
    """List all available keypairs."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    keys = []
    for filepath in sorted(KEYS_DIR.glob("*.json")):
        try:
            data = json.loads(filepath.read_text())
            keys.append(KeyInfo(
                name=filepath.stem,
                did=data["did"],
            ))
        except (json.JSONDecodeError, KeyError):
            pass

    return keys


@app.post("/api/keys", response_model=KeyInfo)
def generate_key(req: GenerateKeyRequest):
    """Generate a new did:key keypair."""
    did, private_bytes = did_module.generate_keypair()
    did_module.save_keypair(str(KEYS_DIR), req.name, did, private_bytes)

    return KeyInfo(name=req.name, did=did)


# ---------------------------------------------------------------------------
# Credential type metadata
# ---------------------------------------------------------------------------

@app.get("/api/credential-types", response_model=list[CredentialTypeInfo])
def get_credential_types():
    """Return the available credential types and their field definitions."""
    result = []
    for cli_name, internal_name in TYPE_MAP.items():
        type_def = cred.CREDENTIAL_TYPES[internal_name]
        result.append(CredentialTypeInfo(
            name=cli_name,
            internal_name=internal_name,
            required_fields=type_def["required"],
            optional_fields=type_def.get("optional", []),
        ))
    return result


# ---------------------------------------------------------------------------
# Credential lifecycle endpoints
# ---------------------------------------------------------------------------

@app.get("/api/credentials", response_model=list[CredentialInfo])
def list_credentials():
    """List all locally stored credentials with decoded details."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    credentials = []
    for filepath in sorted(CREDENTIALS_DIR.glob("*.jwt")):
        token = filepath.read_text().strip()
        try:
            payload = cred.verify_credential_signature(token)
            credential_hash = cred.hash_credential(token)
            credentials.append(CredentialInfo(
                filename=filepath.name,
                summary=cred.format_credential_summary(payload),
                hash=credential_hash,
                issuer=payload["issuer"],
                holder=payload["credentialSubject"]["id"],
                credential_type=payload["type"][1],
                valid_from=payload.get("validFrom"),
                valid_until=payload.get("validUntil"),
            ))
        except Exception:
            pass

    return credentials


@app.get("/api/credentials/status")
def get_all_credential_statuses(chain: str):
    """Check the on-chain status of all locally stored credentials.

    Returns a dict mapping each credential's hash to its on-chain status.
    Credentials that can't be decoded are silently skipped.
    """
    backend = _get_chain_backend(chain)
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    statuses = {}
    for filepath in sorted(CREDENTIALS_DIR.glob("*.jwt")):
        token = filepath.read_text().strip()
        try:
            cred.verify_credential_signature(token)
            credential_hash = cred.hash_credential(token)
            statuses[credential_hash] = backend.get_credential_status(credential_hash)
        except Exception:
            pass

    return statuses


@app.post("/api/credentials/issue", response_model=IssuedCredential)
def issue_credential(req: IssueRequest):
    """Create, sign, and store a Verifiable Credential."""
    internal_type = TYPE_MAP.get(req.credential_type)
    if not internal_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown credential type: {req.credential_type}. "
                   f"Valid types: {list(TYPE_MAP.keys())}",
        )

    # Load the issuer keypair
    key_path = KEYS_DIR / f"{req.issuer_key_name}.json"
    if not key_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Keypair not found: {req.issuer_key_name}",
        )
    issuer_did, private_key = did_module.load_keypair(str(key_path))

    # Build and sign the credential
    payload = cred.create_credential(
        credential_type=internal_type,
        issuer_did=issuer_did,
        holder_did=req.holder_did,
        claims=req.claims,
        valid_until=req.valid_until,
    )

    token = cred.sign_credential(payload, private_key)
    credential_hash = cred.hash_credential(token)
    summary = cred.format_credential_summary(payload)

    # Save to disk
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    short_hash = credential_hash[2:10]
    filename = f"{req.credential_type}_{short_hash}.jwt"
    (CREDENTIALS_DIR / filename).write_text(token)

    return IssuedCredential(
        filename=filename,
        token=token,
        hash=credential_hash,
        summary=summary,
    )


@app.post("/api/credentials/register")
def register_credential(req: RegisterRequest):
    """Register a credential hash on-chain."""
    backend = _get_chain_backend(req.chain)
    private_key = _resolve_private_key(req.chain)

    # Read the credential
    filepath = CREDENTIALS_DIR / req.credential_filename
    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Credential file not found: {req.credential_filename}",
        )

    token = filepath.read_text().strip()
    payload = cred.verify_credential_signature(token)

    issuer_did = payload["issuer"]
    expiration = cred.credential_expiration_timestamp(payload)
    credential_hash = cred.hash_credential(token)

    receipt = backend.register_credential(
        private_key=private_key,
        credential_hash=credential_hash,
        issuer_did=issuer_did,
        expiration=expiration,
    )

    cost_info = backend.get_gas_used(receipt)

    return {
        "hash": credential_hash,
        "chain": req.chain,
        "cost": cost_info["gasUsed"],
        "summary": cred.format_credential_summary(payload),
    }


@app.post("/api/credentials/revoke")
def revoke_credential(req: RevokeRequest):
    """Revoke a credential on-chain."""
    backend = _get_chain_backend(req.chain)
    private_key = _resolve_private_key(req.chain)

    receipt = backend.revoke_credential(
        private_key=private_key,
        credential_hash=req.credential_hash,
    )

    cost_info = backend.get_gas_used(receipt)

    return {
        "hash": req.credential_hash,
        "chain": req.chain,
        "cost": cost_info["gasUsed"],
    }


@app.post("/api/credentials/verify")
def verify_credential(req: VerifyRequest):
    """Verify a credential: check signature and on-chain status."""
    backend = _get_chain_backend(req.chain)

    # Step 1: Verify the JWT signature
    try:
        payload = cred.verify_credential_signature(req.token)
    except Exception as e:
        return {
            "signatureValid": False,
            "signatureError": str(e),
            "onChainStatus": None,
            "result": "INVALID_SIGNATURE",
        }

    # Step 2: Check on-chain status
    credential_hash = cred.hash_credential(req.token)
    status = backend.get_credential_status(credential_hash)

    if not status["exists"]:
        result = "UNVERIFIABLE"
    elif status["revoked"]:
        result = "REVOKED"
    elif status["expiration"] != 0:
        valid = backend.is_credential_valid(credential_hash)
        result = "VALID" if valid else "EXPIRED"
    else:
        result = "VALID"

    # Check issuer consistency
    issuer_match = status["issuer"] == payload["issuer"] if status["exists"] else None

    return {
        "signatureValid": True,
        "credential": {
            "summary": cred.format_credential_summary(payload),
            "issuer": payload["issuer"],
            "holder": payload["credentialSubject"]["id"],
            "type": payload["type"][1],
            "validFrom": payload.get("validFrom"),
            "validUntil": payload.get("validUntil"),
        },
        "hash": credential_hash,
        "onChainStatus": status,
        "issuerMatch": issuer_match,
        "result": result,
    }