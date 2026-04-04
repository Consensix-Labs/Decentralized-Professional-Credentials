#!/usr/bin/env bash
#
# run_scenarios_iota.sh -- Run all credential scenarios end-to-end on IOTA.
#
# Prerequisites:
#   - IOTA Local Testing Starter Pack running (./iota.sh start)
#   - IOTA_STARTER_PACK_DIR set in .env (path to the starter pack directory)
#   - .env file configured with IOTA variables (copy from .env.example)
#   - Docker and Docker Compose installed
#
# This script exercises the full credential lifecycle on IOTA Rebased:
#   1. Employment credential -- issue, register, verify, revoke, verify again
#   2. Certification credential -- issue with expiration, register, verify
#   3. Peer endorsements -- three endorsers, register all, verify all
#
# Before running the CLI, the script compiles the Move package using the
# starter pack's iota-tools container. This is necessary because there is
# no Python Move compiler -- the build step requires the IOTA toolchain.
#
# Usage: ./run_scenarios_iota.sh

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

CHAIN="iota"

# Load .env so we can read IOTA_STARTER_PACK_DIR and other config
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Validate the starter pack directory
if [ -z "${IOTA_STARTER_PACK_DIR:-}" ]; then
    echo -e "${RED}ERROR: IOTA_STARTER_PACK_DIR is not set.${NC}"
    echo "Set it in your .env file to the path of your IOTA Local Testing Starter Pack, e.g.:"
    echo "  IOTA_STARTER_PACK_DIR=/home/user/IOTA-Local-Testing-Starter-Pack"
    exit 1
fi

if [ ! -f "${IOTA_STARTER_PACK_DIR}/compose.yml" ]; then
    echo -e "${RED}ERROR: No compose.yml found in IOTA_STARTER_PACK_DIR: ${IOTA_STARTER_PACK_DIR}${NC}"
    exit 1
fi

# Pre-funded test account from the IOTA Local Testing Starter Pack keystore.
# This key is used for deploying the contract and registering/revoking credentials.
IOTA_PRIVATE_KEY="iotaprivkey1qq8g3ngnmxywcf5y3spfr9n5qxun783g822suhh0zrq5uhgjzf2hjyfmp9j"

# Absolute path to the contract source -- needed for the volume mount
CONTRACT_DIR="$(cd "$(pwd)/contracts/iota" && pwd)"

# Helper to run the CLI via Docker Compose
cred() {
    docker compose run --rm cred "$@"
}

# Helper to run iota-tools via the starter pack's Docker Compose
iota_tools() {
    docker compose -f "${IOTA_STARTER_PACK_DIR}/compose.yml" run --rm \
        -v "${CONTRACT_DIR}:/tmp/contract" \
        iota-tools \
        sh -c "cd /tmp/contract && $*"
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
# Step 0: Compile the Move package
# ------------------------------------------------------------------------------

section "Step 0: Compiling Move Package"

step "Building credential_registry Move package via starter pack iota-tools..."

# Compile the Move package. The IOTA framework dependency is fetched from
# GitHub on each run since the container is ephemeral (--rm). This takes
# ~30-60s on the first build; subsequent builds within the same container
# would be cached, but --rm prevents that. A future starter pack improvement
# could add a named volume for /root/.move to persist the cache.
iota_tools "iota move build"

if [ ! -d "contracts/iota/build/credential_registry/bytecode_modules" ]; then
    echo -e "${RED}ERROR: Move build failed -- no bytecode output found${NC}"
    exit 1
fi

echo "  Build output:"
ls -la contracts/iota/build/credential_registry/bytecode_modules/

# ------------------------------------------------------------------------------
# Step 1: Clean slate
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

# ------------------------------------------------------------------------------
# Step 2: Deploy the contract
# ------------------------------------------------------------------------------

section "Setup: Deploying Contract"

step "Deploying CredentialRegistry on ${CHAIN}..."
DEPLOY_OUTPUT=$(cred deploy --chain "${CHAIN}" --private-key "${IOTA_PRIVATE_KEY}")
echo "${DEPLOY_OUTPUT}"

# Extract contract address (PACKAGE_ID:REGISTRY_ID format) from output
CONTRACT_ADDRESS=$(echo "${DEPLOY_OUTPUT}" | grep "Contract deployed at:" | awk '{print $NF}')

if [ -z "${CONTRACT_ADDRESS}" ]; then
    echo -e "${RED}ERROR: Failed to extract contract address${NC}"
    exit 1
fi

step "Contract address: ${CONTRACT_ADDRESS}"

# Update .env with the contract address for subsequent commands
if grep -q "^IOTA_CONTRACT_ADDRESS=" .env; then
    sed -i "s|^IOTA_CONTRACT_ADDRESS=.*|IOTA_CONTRACT_ADDRESS=${CONTRACT_ADDRESS}|" .env
else
    echo "IOTA_CONTRACT_ADDRESS=${CONTRACT_ADDRESS}" >> .env
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
    --chain "${CHAIN}" \
    --private-key "${IOTA_PRIVATE_KEY}"

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
    --chain "${CHAIN}" \
    --private-key "${IOTA_PRIVATE_KEY}"

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
    --chain "${CHAIN}" \
    --private-key "${IOTA_PRIVATE_KEY}"

step "Verifying (should be VALID -- not yet expired)..."
cred verify \
    --credential "/app/${CERT_CRED}" \
    --chain "${CHAIN}"

echo ""
echo -e "${YELLOW}  Note: Expiration is checked against the IOTA Clock timestamp."
echo -e "  Unlike EVM, IOTA uses millisecond-precision timestamps from the"
echo -e "  network Clock object. See the research paper for discussion.${NC}"

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
        --chain "${CHAIN}" \
        --private-key "${IOTA_PRIVATE_KEY}"
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