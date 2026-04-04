"""
CLI entrypoint for Decentralized Professional Credentials.

Provides commands for the full credential lifecycle:
- Issuers create, sign, register, and revoke credentials.
- Holders list and present their credentials.
- Verifiers check credential authenticity and on-chain status.
- Utility commands for key generation and contract deployment.

Usage: python cli.py [OPTIONS] COMMAND [ARGS]
"""

import json
import os
from pathlib import Path

import click

import credential as cred
import did as did_module


# Where credentials are stored locally (holder's credential store)
CREDENTIALS_DIR = Path(os.environ.get("CREDENTIALS_DIR", "./credentials"))

# Where reports are written
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "./reports"))


def get_chain_backend(chain):
    """Import the appropriate chain backend module."""
    if chain == "evm":
        import chain_evm
        return chain_evm
    elif chain == "iota":
        import chain_iota
        return chain_iota
    else:
        raise click.ClickException(f"Unknown chain: {chain}")


# Environment variable names, keyed by chain, for the deployer/issuer private keys.
_DEPLOYER_KEY_ENVVARS = {
    "evm": "EVM_DEPLOYER_PRIVATE_KEY",
    "iota": "IOTA_DEPLOYER_PRIVATE_KEY",
}
_ISSUER_KEY_ENVVARS = {
    "evm": "EVM_ISSUER_PRIVATE_KEY",
    "iota": "IOTA_ISSUER_PRIVATE_KEY",
}


def _resolve_private_key(explicit_value, chain, envvar_map):
    """Return the private key from an explicit CLI flag or a chain-specific env var.

    Click can't pick a different envvar based on another option's value, so we
    handle the fallback ourselves.
    """
    if explicit_value:
        return explicit_value

    envvar = envvar_map.get(chain, "")
    value = os.environ.get(envvar)
    if not value:
        raise click.ClickException(
            f"No --private-key provided and {envvar} is not set"
        )
    return value


# ---------------------------------------------------------------------------
# Top-level CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Decentralized Professional Credentials -- CLI tool.

    Issue, register, verify, and revoke W3C Verifiable Credentials
    anchored on EVM or IOTA blockchains.
    """
    pass


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

@cli.command("generate-key")
@click.argument("name")
@click.option("--output-dir", default="./keys", help="Directory to store the keypair.")
def generate_key(name, output_dir):
    """Generate a new did:key keypair and save it to disk."""
    did, private_bytes = did_module.generate_keypair()
    filepath = did_module.save_keypair(output_dir, name, did, private_bytes)

    click.echo(f"Generated keypair: {name}")
    click.echo(f"  DID:  {did}")
    click.echo(f"  Saved to: {filepath}")


# ---------------------------------------------------------------------------
# Contract deployment
# ---------------------------------------------------------------------------

@cli.command("deploy")
@click.option("--chain", type=click.Choice(["evm", "iota"]), required=True,
              help="Which blockchain to deploy to.")
@click.option("--private-key", default=None,
              help="Deployer account private key. Falls back to EVM_DEPLOYER_PRIVATE_KEY or IOTA_DEPLOYER_PRIVATE_KEY.")
def deploy(chain, private_key):
    """Deploy the CredentialRegistry contract."""
    private_key = _resolve_private_key(private_key, chain, _DEPLOYER_KEY_ENVVARS)
    backend = get_chain_backend(chain)

    click.echo(f"Deploying CredentialRegistry on {chain}...")
    address = backend.deploy_contract(private_key)
    click.echo(f"Contract deployed at: {address}")

    env_var = "EVM_CONTRACT_ADDRESS" if chain == "evm" else "IOTA_CONTRACT_ADDRESS"
    click.echo(f"\nAdd to your .env file:")
    click.echo(f"  {env_var}={address}")


# ---------------------------------------------------------------------------
# Credential issuance
# ---------------------------------------------------------------------------

@cli.command("issue")
@click.option("--type", "credential_type",
              type=click.Choice(["employment", "certification", "endorsement"]),
              required=True, help="Type of credential to issue.")
@click.option("--issuer-key", required=True,
              help="Path to the issuer's keypair JSON file.")
@click.option("--holder-did", required=True,
              help="The holder/subject's did:key.")
@click.option("--claims", required=True,
              help="JSON string or path to JSON file with credentialSubject fields.")
@click.option("--valid-until", default=None,
              help="Expiration date (ISO 8601). Omit for no expiration.")
@click.option("--output-dir", default=None,
              help="Directory to save the credential. Defaults to CREDENTIALS_DIR.")
def issue(credential_type, issuer_key, holder_did, claims, valid_until, output_dir):
    """Create and sign a Verifiable Credential."""
    # Map CLI type names to internal type names
    type_map = {
        "employment": "EmploymentCredential",
        "certification": "CertificationCredential",
        "endorsement": "PeerEndorsement",
    }
    internal_type = type_map[credential_type]

    # Load issuer keypair
    issuer_did, private_key = did_module.load_keypair(issuer_key)
    click.echo(f"Issuer: {issuer_did}")

    # Parse claims from JSON string or file
    if os.path.isfile(claims):
        claims_data = json.loads(Path(claims).read_text())
    else:
        claims_data = json.loads(claims)

    # Build the credential payload
    payload = cred.create_credential(
        credential_type=internal_type,
        issuer_did=issuer_did,
        holder_did=holder_did,
        claims=claims_data,
        valid_until=valid_until,
    )

    click.echo(f"Credential: {cred.format_credential_summary(payload)}")

    # Sign it
    token = cred.sign_credential(payload, private_key)
    credential_hash = cred.hash_credential(token)

    click.echo(f"Hash: {credential_hash}")

    # Save to disk
    save_dir = Path(output_dir) if output_dir else CREDENTIALS_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    # Filename from type and a short hash prefix for uniqueness
    short_hash = credential_hash[2:10]
    filename = f"{credential_type}_{short_hash}.jwt"
    filepath = save_dir / filename
    filepath.write_text(token)

    click.echo(f"Saved to: {filepath}")


# ---------------------------------------------------------------------------
# On-chain registration
# ---------------------------------------------------------------------------

@cli.command("register")
@click.option("--credential", "credential_path", required=True,
              help="Path to the signed JWT credential file.")
@click.option("--chain", type=click.Choice(["evm", "iota"]), required=True,
              help="Which blockchain to register on.")
@click.option("--private-key", default=None,
              help="Issuer's blockchain account private key. Falls back to EVM_ISSUER_PRIVATE_KEY or IOTA_ISSUER_PRIVATE_KEY.")
def register(credential_path, chain, private_key):
    """Register a credential hash on-chain."""
    private_key = _resolve_private_key(private_key, chain, _ISSUER_KEY_ENVVARS)
    backend = get_chain_backend(chain)

    # Read the signed JWT
    token = Path(credential_path).read_text().strip()

    # Decode to get issuer DID and expiration
    payload = cred.verify_credential_signature(token)
    issuer_did = payload["issuer"]
    expiration = cred.credential_expiration_timestamp(payload)
    credential_hash = cred.hash_credential(token)

    click.echo(f"Credential: {cred.format_credential_summary(payload)}")
    click.echo(f"Hash: {credential_hash}")
    click.echo(f"Issuer DID: {issuer_did}")
    click.echo(f"Expiration: {expiration if expiration else 'none'}")
    click.echo(f"Registering on {chain}...")

    receipt = backend.register_credential(
        private_key=private_key,
        credential_hash=credential_hash,
        issuer_did=issuer_did,
        expiration=expiration,
    )

    cost_info = backend.get_gas_used(receipt)
    cost_label = "Gas used" if chain == "evm" else "Cost (NANOS)"
    click.echo(f"Registered. {cost_label}: {cost_info['gasUsed']}")


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

@cli.command("revoke")
@click.option("--credential-hash", required=True,
              help="0x-prefixed SHA-256 hash of the credential to revoke.")
@click.option("--chain", type=click.Choice(["evm", "iota"]), required=True,
              help="Which blockchain the credential is registered on.")
@click.option("--private-key", default=None,
              help="Issuer's blockchain account private key. Falls back to EVM_ISSUER_PRIVATE_KEY or IOTA_ISSUER_PRIVATE_KEY.")
def revoke(credential_hash, chain, private_key):
    """Revoke a credential on-chain."""
    private_key = _resolve_private_key(private_key, chain, _ISSUER_KEY_ENVVARS)
    backend = get_chain_backend(chain)

    click.echo(f"Revoking credential {credential_hash} on {chain}...")

    receipt = backend.revoke_credential(
        private_key=private_key,
        credential_hash=credential_hash,
    )

    cost_info = backend.get_gas_used(receipt)
    cost_label = "Gas used" if chain == "evm" else "Cost (NANOS)"
    click.echo(f"Revoked. {cost_label}: {cost_info['gasUsed']}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@cli.command("verify")
@click.option("--credential", "credential_path", required=True,
              help="Path to the signed JWT credential file.")
@click.option("--chain", type=click.Choice(["evm", "iota"]), required=True,
              help="Which blockchain to check for on-chain status.")
def verify(credential_path, chain):
    """Verify a credential: check signature and on-chain status."""
    backend = get_chain_backend(chain)

    token = Path(credential_path).read_text().strip()

    # Step 1: Verify the JWT signature
    click.echo("Checking signature...")
    try:
        payload = cred.verify_credential_signature(token)
        click.echo("  Signature: VALID")
    except Exception as e:
        click.echo(f"  Signature: INVALID ({e})")
        return

    click.echo(f"  Credential: {cred.format_credential_summary(payload)}")
    click.echo(f"  Issuer: {payload['issuer']}")
    click.echo(f"  Holder: {payload['credentialSubject']['id']}")

    # Step 2: Check on-chain status
    credential_hash = cred.hash_credential(token)
    click.echo(f"\nChecking on-chain status ({chain})...")
    click.echo(f"  Hash: {credential_hash}")

    status = backend.get_credential_status(credential_hash)

    if not status["exists"]:
        click.echo("  Status: NOT REGISTERED")
        click.echo("\n  Result: UNVERIFIABLE (credential not found on-chain)")
        return

    click.echo(f"  Registered: yes (at block timestamp {status['issuedAt']})")
    click.echo(f"  Issuer (on-chain): {status['issuer']}")

    # Check issuer consistency
    if status["issuer"] != payload["issuer"]:
        click.echo("  WARNING: On-chain issuer does not match JWT issuer!")

    if status["revoked"]:
        click.echo(f"  Revoked: yes (at block timestamp {status['revokedAt']})")
        click.echo("\n  Result: REVOKED")
        return

    if status["expiration"] != 0:
        click.echo(f"  Expiration: {status['expiration']}")
        # We can't easily compare with current block timestamp from a view call,
        # so use the convenience function
        valid = backend.is_credential_valid(credential_hash)
        if not valid:
            click.echo("\n  Result: EXPIRED")
            return

    click.echo("\n  Result: VALID")


# ---------------------------------------------------------------------------
# Status check (by hash, without needing the credential file)
# ---------------------------------------------------------------------------

@cli.command("status")
@click.option("--credential-hash", required=True,
              help="0x-prefixed SHA-256 hash of the credential.")
@click.option("--chain", type=click.Choice(["evm", "iota"]), required=True,
              help="Which blockchain to query.")
def status(credential_hash, chain):
    """Check the on-chain status of a credential by its hash."""
    backend = get_chain_backend(chain)

    result = backend.get_credential_status(credential_hash)

    if not result["exists"]:
        click.echo("Credential not found on-chain.")
        return

    click.echo(f"Issuer: {result['issuer']}")
    click.echo(f"Registered at: {result['issuedAt']}")
    click.echo(f"Expiration: {result['expiration'] if result['expiration'] else 'none'}")
    click.echo(f"Revoked: {result['revoked']}")
    if result["revoked"]:
        click.echo(f"Revoked at: {result['revokedAt']}")

    valid = backend.is_credential_valid(credential_hash)
    click.echo(f"Currently valid: {valid}")


# ---------------------------------------------------------------------------
# Holder operations
# ---------------------------------------------------------------------------

@cli.command("list")
@click.option("--credentials-dir", default=None,
              help="Directory containing credential JWT files.")
def list_credentials(credentials_dir):
    """List all locally stored credentials."""
    cred_dir = Path(credentials_dir) if credentials_dir else CREDENTIALS_DIR

    if not cred_dir.exists():
        click.echo("No credentials directory found.")
        return

    jwt_files = sorted(cred_dir.glob("*.jwt"))
    if not jwt_files:
        click.echo("No credentials found.")
        return

    for filepath in jwt_files:
        token = filepath.read_text().strip()
        try:
            payload = cred.verify_credential_signature(token)
            credential_hash = cred.hash_credential(token)
            summary = cred.format_credential_summary(payload)
            click.echo(f"  {filepath.name}")
            click.echo(f"    {summary}")
            click.echo(f"    Hash: {credential_hash}")
        except Exception as e:
            click.echo(f"  {filepath.name} -- error: {e}")
        click.echo()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()