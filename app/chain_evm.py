"""
EVM chain backend -- compile, deploy, and interact with CredentialRegistry.sol.

Uses py-solc-x for Solidity compilation and web3.py for blockchain interaction.
Connection details come from environment variables so the same code works
against a local Hardhat node, a testnet, or mainnet.
"""

import json
import os
from pathlib import Path

from solcx import compile_source, install_solc
from web3 import Web3

# Solidity compiler version matching the pragma in CredentialRegistry.sol
SOLC_VERSION = "0.8.28"

# Path to the contract source. Inside the Docker container, CLI files and
# contracts are both under /app/. When running directly, they're one level up.
CONTRACT_PATH = Path(__file__).parent / "contracts" / "evm" / "CredentialRegistry.sol"


def get_web3():
    """Connect to the EVM node using the EVM_RPC_URL environment variable."""
    rpc_url = os.environ.get("EVM_RPC_URL")
    if not rpc_url:
        raise RuntimeError("EVM_RPC_URL environment variable not set")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to EVM node at {rpc_url}")
    return w3


def compile_contract():
    """Compile CredentialRegistry.sol and return (abi, bytecode).

    Installs the Solidity compiler on first run if not already present.
    """
    install_solc(SOLC_VERSION)

    source = CONTRACT_PATH.read_text()
    compiled = compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
    )

    # compile_source returns a dict keyed by "<filename>:<ContractName>"
    contract_id, contract_data = next(
        (k, v) for k, v in compiled.items() if "CredentialRegistry" in k
    )

    return contract_data["abi"], contract_data["bin"]


def deploy_contract(private_key):
    """Compile and deploy the CredentialRegistry contract.

    Args:
        private_key: Hex-encoded private key of the deployer account.

    Returns:
        The deployed contract address as a string.
    """
    w3 = get_web3()
    account = w3.eth.account.from_key(private_key)
    abi, bytecode = compile_contract()

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 3_000_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        raise RuntimeError("Contract deployment failed")

    return receipt["contractAddress"]


def get_contract(contract_address=None):
    """Get a web3 contract instance for an already-deployed registry.

    Uses EVM_CONTRACT_ADDRESS from the environment if not provided explicitly.
    """
    w3 = get_web3()

    address = contract_address or os.environ.get("EVM_CONTRACT_ADDRESS")
    if not address:
        raise RuntimeError("No contract address provided or in EVM_CONTRACT_ADDRESS env var")

    abi, _ = compile_contract()
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def register_credential(private_key, credential_hash, issuer_did, expiration,
                         contract_address=None):
    """Register a credential hash on the EVM registry.

    Args:
        private_key: Hex-encoded private key of the issuer's EVM account.
        credential_hash: 0x-prefixed hex string (bytes32 SHA-256 hash).
        issuer_did: The issuer's did:key string.
        expiration: Unix timestamp (0 for no expiration).
        contract_address: Optional override for EVM_CONTRACT_ADDRESS env var.

    Returns:
        Transaction receipt dict.
    """
    w3 = get_web3()
    account = w3.eth.account.from_key(private_key)
    contract = get_contract(contract_address)

    tx = contract.functions.registerCredential(
        bytes.fromhex(credential_hash[2:]),  # strip 0x prefix for bytes32
        issuer_did,
        expiration,
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 300_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        raise RuntimeError(
            f"registerCredential failed (tx: {tx_hash.hex()})"
        )

    return receipt


def revoke_credential(private_key, credential_hash, contract_address=None):
    """Revoke a credential on the EVM registry.

    Args:
        private_key: Hex-encoded private key (must be the original registrant).
        credential_hash: 0x-prefixed hex string.
        contract_address: Optional override.

    Returns:
        Transaction receipt dict.
    """
    w3 = get_web3()
    account = w3.eth.account.from_key(private_key)
    contract = get_contract(contract_address)

    tx = contract.functions.revokeCredential(
        bytes.fromhex(credential_hash[2:]),
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt["status"] != 1:
        raise RuntimeError(
            f"revokeCredential failed (tx: {tx_hash.hex()})"
        )

    return receipt


def get_credential_status(credential_hash, contract_address=None):
    """Query the on-chain status of a credential.

    Returns a dict with: exists, issuer, issuedAt, expiration, revoked, revokedAt.
    """
    contract = get_contract(contract_address)

    result = contract.functions.getCredentialStatus(
        bytes.fromhex(credential_hash[2:]),
    ).call()

    return {
        "exists": result[0],
        "issuer": result[1],
        "issuedAt": result[2],
        "expiration": result[3],
        "revoked": result[4],
        "revokedAt": result[5],
    }


def is_credential_valid(credential_hash, contract_address=None):
    """Check if a credential is currently valid on-chain.

    Returns True only if registered, not revoked, and not expired.
    """
    contract = get_contract(contract_address)

    return contract.functions.isCredentialValid(
        bytes.fromhex(credential_hash[2:]),
    ).call()


def get_gas_used(receipt):
    """Extract gas usage from a transaction receipt for comparison metrics."""
    return {
        "gasUsed": receipt["gasUsed"],
        "effectiveGasPrice": receipt.get("effectiveGasPrice", 0),
        "totalCost": receipt["gasUsed"] * receipt.get("effectiveGasPrice", 0),
    }