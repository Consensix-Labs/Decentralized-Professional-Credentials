#!/usr/bin/env bash
#
# run_scenarios_evm.sh -- Run all credential scenarios end-to-end on EVM.
#
# Prerequisites:
#   - Ethereum Local Testing Starter Pack running (./eth.sh start)
#   - .env file configured (copy from .env.example)
#   - Docker and Docker Compose installed
#
# This script exercises the full credential lifecycle:
#   1. Employment credential -- issue, register, verify, revoke, verify again
#   2. Certification credential -- issue with expiration, register, verify
#   3. Peer endorsements -- three endorsers, register all, verify all
#
# Usage: ./run_scenarios_evm.sh

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

CHAIN="evm"

# Helper to run the CLI via Docker Compose
cred() {
    docker compose run --rm cred "$@"
}

section() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

step() {
    echo -e "${GREEN}→ $1${NC}"
}

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

section "Setup: Generating Keys"

# Remove stale credentials and keys from previous runs.
# These files are owned by root (created inside Docker), so we clean up
# via the container rather than from the host.
step "Cleaning up previous run artifacts..."
docker compose run --rm --entrypoint sh cred -c "rm -f /app/credentials/*.jwt /app/keys/*.json"

step "Generating issuer key (employer)..."
cred generate-key employer --output-dir /app/keys

step "Generating issuer key (certification body)..."
cred generate-key certbody --output-dir /app/keys

step "Generating endorser keys (3 peers)..."
cred generate-key endorser-bob --output-dir /app/keys
cred generate-key endorser-carol --output-dir /app/keys
cred generate-key endorser-dave --output-dir /app/keys

step "Generating holder key (Alice)..."
cred generate-key alice --output-dir /app/keys

# Extract Alice's DID for use in credential issuance
ALICE_DID=$(python3 -c "import json; print(json.load(open('keys/alice.json'))['did'])")
echo "  Alice's DID: ${ALICE_DID}"

section "Setup: Deploying Contract"

step "Deploying CredentialRegistry on ${CHAIN}..."
DEPLOY_OUTPUT=$(cred deploy --chain "${CHAIN}")
echo "${DEPLOY_OUTPUT}"

# Extract contract address from output
CONTRACT_ADDRESS=$(echo "${DEPLOY_OUTPUT}" | grep "Contract deployed at:" | awk '{print $NF}')

if [ -z "${CONTRACT_ADDRESS}" ]; then
    echo -e "${RED}ERROR: Failed to extract contract address${NC}"
    exit 1
fi

step "Contract address: ${CONTRACT_ADDRESS}"

# Update .env with the contract address for subsequent commands
if grep -q "^EVM_CONTRACT_ADDRESS=" .env; then
    sed -i "s/^EVM_CONTRACT_ADDRESS=.*/EVM_CONTRACT_ADDRESS=${CONTRACT_ADDRESS}/" .env
else
    echo "EVM_CONTRACT_ADDRESS=${CONTRACT_ADDRESS}" >> .env
fi

# ------------------------------------------------------------------------------
# Scenario 1: Employment Credential
# ------------------------------------------------------------------------------

section "Scenario 1: Employment Credential"

step "Issuing employment credential..."
cred issue \
    --type employment \
    --issuer-key /app/keys/employer.json \
    --holder-did "${ALICE_DID}" \
    --claims /app/samples/employment_claims.json

# Find the credential file that was just created
EMPLOYMENT_CRED=$(ls -t credentials/employment_*.jwt 2>/dev/null | head -1)

if [ -z "${EMPLOYMENT_CRED}" ]; then
    echo -e "${RED}ERROR: Employment credential file not found${NC}"
    exit 1
fi

step "Registering on-chain..."
cred register \
    --credential "/app/${EMPLOYMENT_CRED}" \
    --chain "${CHAIN}"

step "Verifying (should be VALID)..."
cred verify \
    --credential "/app/${EMPLOYMENT_CRED}" \
    --chain "${CHAIN}"

# Extract the credential hash for revocation
EMPLOYMENT_HASH=$(python3 -c "
import hashlib
token = open('${EMPLOYMENT_CRED}').read().strip()
h = hashlib.sha256(token.encode()).hexdigest()
print('0x' + h)
")

step "Revoking credential (employer terminates attestation)..."
cred revoke \
    --credential-hash "${EMPLOYMENT_HASH}" \
    --chain "${CHAIN}"

step "Verifying again (should be REVOKED)..."
cred verify \
    --credential "/app/${EMPLOYMENT_CRED}" \
    --chain "${CHAIN}"

# ------------------------------------------------------------------------------
# Scenario 2: Certification Credential (with expiration)
# ------------------------------------------------------------------------------

section "Scenario 2: Certification Credential"

step "Issuing certification credential (expires 2027-01-15)..."
cred issue \
    --type certification \
    --issuer-key /app/keys/certbody.json \
    --holder-did "${ALICE_DID}" \
    --claims /app/samples/certification_claims.json \
    --valid-until "2027-01-15T00:00:00Z"

CERT_CRED=$(ls -t credentials/certification_*.jwt 2>/dev/null | head -1)

if [ -z "${CERT_CRED}" ]; then
    echo -e "${RED}ERROR: Certification credential file not found${NC}"
    exit 1
fi

step "Registering on-chain..."
cred register \
    --credential "/app/${CERT_CRED}" \
    --chain "${CHAIN}"

step "Verifying (should be VALID -- not yet expired)..."
cred verify \
    --credential "/app/${CERT_CRED}" \
    --chain "${CHAIN}"

echo ""
echo -e "${YELLOW}  Note: Expiration is checked against the blockchain's block timestamp."
echo -e "  To demonstrate expiration, the contract would need to be tested with"
echo -e "  a credential whose validUntil is in the past, or by advancing the"
echo -e "  Hardhat node's time. See the research paper for discussion.${NC}"

# ------------------------------------------------------------------------------
# Scenario 3: Peer Endorsements
# ------------------------------------------------------------------------------

section "Scenario 3: Peer Endorsements"

ENDORSER_KEYS=("endorser-bob" "endorser-carol" "endorser-dave")
ENDORSER_INDICES=(0 1 2)

for i in "${ENDORSER_INDICES[@]}"; do
    ENDORSER_KEY="${ENDORSER_KEYS[$i]}"

    # Extract the individual endorsement claims from the array
    CLAIMS=$(python3 -c "import json; print(json.dumps(json.load(open('samples/endorsement_claims.json'))[$i]))")

    step "Issuing endorsement from ${ENDORSER_KEY}..."
    cred issue \
        --type endorsement \
        --issuer-key "/app/keys/${ENDORSER_KEY}.json" \
        --holder-did "${ALICE_DID}" \
        --claims "${CLAIMS}"
done

step "Registering all endorsements on-chain..."
for cred_file in credentials/endorsement_*.jwt; do
    cred register \
        --credential "/app/${cred_file}" \
        --chain "${CHAIN}"
done

step "Verifying all endorsements..."
for cred_file in credentials/endorsement_*.jwt; do
    echo ""
    cred verify \
        --credential "/app/${cred_file}" \
        --chain "${CHAIN}"
done

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------

section "Summary"

echo "All scenarios completed on ${CHAIN}."
echo ""
echo "Credentials issued: $(ls credentials/*.jwt 2>/dev/null | wc -l)"
echo "Keys generated: $(ls keys/*.json 2>/dev/null | wc -l)"
echo ""
echo "Credential files:"
cred list