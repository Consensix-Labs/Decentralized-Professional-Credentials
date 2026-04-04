# Decentralized Professional Credentials

A chain-agnostic protocol for W3C Verifiable Credentials with proof-of-concept implementations on Ethereum and IOTA. Issuers create signed credentials off-chain following the W3C VC Data Model v2.0. Credential hashes are anchored on-chain for tamper-proof verification and transparent revocation. Holders control their credentials. Verifiers check authenticity by validating the issuer's signature and confirming on-chain status.

For a full discussion of the concept, architecture, and results, see the [research paper](https://consensixlabs.com/research/decentralized-professional-credentials/Decentralized-Professional-Credentials.pdf).

## Prerequisites

- Docker and Docker Compose
- [Ethereum Local Testing Starter Pack](https://github.com/Consensix-Labs/Ethereum-Local-Testing-Starter-Pack) (for EVM scenarios)
- [IOTA Local Testing Starter Pack](https://github.com/Consensix-Labs/IOTA-Local-Testing-Starter-Pack) (for IOTA scenarios)

## Quick start

### 1. Configure the environment

```bash
cp .env.example .env
```

Edit `.env` to set the IOTA starter pack path (only needed for IOTA scenarios):

```
IOTA_STARTER_PACK_DIR=/path/to/IOTA-Local-Testing-Starter-Pack
```

The remaining defaults (RPC URLs, pre-funded account keys) work with both starter packs out of the box.

### 2. Build

```bash
docker compose build
```

### 3. Run automated scenarios

**EVM:**

```bash
cd /path/to/Ethereum-Local-Testing-Starter-Pack && ./eth.sh start
cd /path/to/decentralized-professional-credentials
./run_scenarios_evm.sh
```

**IOTA:**

```bash
cd /path/to/IOTA-Local-Testing-Starter-Pack && ./iota.sh start
cd /path/to/decentralized-professional-credentials
./run_scenarios_iota.sh
```

Each script generates fresh keys, deploys the contract, and runs three scenarios end-to-end:

1. **Employment credential** -- issue, register, verify, revoke, verify again (shows REVOKED)
2. **Certification credential** -- issue with expiration, register, verify
3. **Peer endorsements** -- three peers endorse the same holder, register all, verify all

## Web interface

A web UI demonstrates the credential lifecycle interactively. It runs alongside the FastAPI backend as a separate Docker Compose profile.

```bash
docker compose --profile ui up api web
```

Access at `http://localhost:3000`. The interface provides three views:

- **Issue** -- create and sign credentials with dynamic claim forms
- **Credentials** -- holder's wallet with on-chain status badges, register/revoke actions
- **Verify** -- paste a JWT to check signature and on-chain status

A chain selector in the header controls which blockchain is used for all on-chain operations. Keys must be generated beforehand via the CLI or scenario scripts.

## Manual CLI usage

Generate keys, deploy the contract, and use individual commands:

```bash
# Generate keypairs
docker compose run --rm cred generate-key employer
docker compose run --rm cred generate-key alice

# Deploy the contract
docker compose run --rm cred deploy --chain evm

# Copy the contract address to .env:
#   EVM_CONTRACT_ADDRESS=0x...

# Issue a credential
docker compose run --rm cred issue \
  --type employment \
  --issuer-key /app/keys/employer.json \
  --holder-did "did:key:z6Mk..." \
  --claims /app/samples/employment_claims.json

# Register on-chain
docker compose run --rm cred register \
  --credential /app/credentials/employment_XXXXXXXX.jwt \
  --chain evm

# Verify
docker compose run --rm cred verify \
  --credential /app/credentials/employment_XXXXXXXX.jwt \
  --chain evm
```

For IOTA, replace `--chain evm` with `--chain iota` and use `IOTA_CONTRACT_ADDRESS` in `.env`.

## Credential types

| Type | Issued by | Expires | Example |
|------|-----------|---------|---------|
| Employment | Employer | No | "Alice was Senior Engineer at Acme Corp, 2022-2024" |
| Certification | Certification body | Yes | "Alice holds AWS Solutions Architect - Professional" |
| Peer Endorsement | Individual | No | "Bob endorses Alice for distributed systems expertise" |

## CLI commands

| Command | Description |
|---------|-------------|
| `generate-key <n>` | Generate a new did:key keypair |
| `deploy --chain <evm\|iota>` | Deploy the CredentialRegistry contract |
| `issue --type <type> ...` | Create and sign a Verifiable Credential |
| `register --credential <file> --chain <chain>` | Anchor a credential hash on-chain |
| `revoke --credential-hash <hash> --chain <chain>` | Revoke a credential on-chain |
| `verify --credential <file> --chain <chain>` | Check signature and on-chain status |
| `status --credential-hash <hash> --chain <chain>` | Query on-chain status by hash |
| `list` | List locally stored credentials |

## Project structure

```
decentralized-professional-credentials/
├── compose.yml                                # Docker Compose (CLI + UI profile)
├── Dockerfile                                 # Python container (shared by CLI and API)
├── .env.example                               # Environment configuration template
├── run_scenarios_evm.sh                       # End-to-end EVM scenario script
├── run_scenarios_iota.sh                      # End-to-end IOTA scenario script
├── app/
│   ├── cli.py                                 # CLI entrypoint (Click)
│   ├── api.py                                 # REST API entrypoint (FastAPI)
│   ├── credential.py                          # W3C VC v2.0 creation and JWT signing
│   ├── did.py                                 # did:key generation and resolution
│   ├── chain_evm.py                           # EVM backend (web3.py + py-solc-x)
│   ├── chain_iota.py                          # IOTA backend (pure JSON-RPC)
│   └── requirements.txt                       # Python dependencies
├── web/
│   ├── Dockerfile                             # Multi-stage build (Node 22 + nginx)
│   ├── nginx.conf                             # Serves app + proxies /api/ to backend
│   ├── src/                                   # React + Mantine 8 frontend
│   └── package.json                           # Frontend dependencies
├── contracts/
│   ├── evm/
│   │   └── CredentialRegistry.sol             # Solidity contract (0.8.28)
│   └── iota/
│       ├── Move.toml                          # Move package manifest (v1.1.0)
│       ├── sources/
│       │   └── credential_registry.move       # Move contract
│       └── tests/
│           └── credential_registry_tests.move # Move unit tests (6 tests)
├── samples/                                   # Sample credential claims (JSON)
├── credentials/                               # Generated credential JWTs (gitignored)
├── keys/                                      # Generated keypairs (gitignored)
└── reports/                                   # Generated reports (gitignored)
```

## Environment variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `EVM_RPC_URL` | For EVM | Ethereum JSON-RPC endpoint |
| `EVM_DEPLOYER_PRIVATE_KEY` | For EVM | Deployer account private key (hex) |
| `EVM_ISSUER_PRIVATE_KEY` | For EVM | Issuer account private key for register/revoke |
| `EVM_CONTRACT_ADDRESS` | For EVM | Deployed contract address (set after deploy) |
| `IOTA_RPC_URL` | For IOTA | IOTA full node JSON-RPC endpoint |
| `IOTA_DEPLOYER_PRIVATE_KEY` | For IOTA | Deployer account private key (iotaprivkey1...) |
| `IOTA_ISSUER_PRIVATE_KEY` | For IOTA | Issuer account private key for register/revoke |
| `IOTA_CONTRACT_ADDRESS` | For IOTA | Deployed contract address (PACKAGE_ID:REGISTRY_ID) |
| `IOTA_STARTER_PACK_DIR` | For IOTA | Path to the IOTA Local Testing Starter Pack |

## Running Move contract tests

```bash
cd /path/to/IOTA-Local-Testing-Starter-Pack
docker compose run --rm \
    -v /path/to/decentralized-professional-credentials-protocol/contracts/iota:/tmp/contract \
    iota-tools \
    sh -c "cd /tmp/contract && iota move test"
```

## About

Developed by [Consensix Labs](https://consensixlabs.com). Part of the Consensix Labs research series on practical blockchain applications. The code is provided for research and educational purposes.