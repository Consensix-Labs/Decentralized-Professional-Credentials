/**
 * API client for the Decentralized Professional Credentials backend.
 *
 * All endpoints return parsed JSON on success or throw an error with
 * the server's detail message on failure.
 */

const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.detail || `Request failed (${res.status})`;
    throw new Error(message);
  }

  return res.json();
}

// -- Keys --

export function fetchKeys() {
  return request("/keys");
}

export function generateKey(name) {
  return request("/keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

// -- Credential types --

export function fetchCredentialTypes() {
  return request("/credential-types");
}

// -- Credentials --

export function fetchCredentials() {
  return request("/credentials");
}

export function issueCredential({ credentialType, issuerKeyName, holderDid, claims, validUntil }) {
  return request("/credentials/issue", {
    method: "POST",
    body: JSON.stringify({
      credential_type: credentialType,
      issuer_key_name: issuerKeyName,
      holder_did: holderDid,
      claims,
      valid_until: validUntil || null,
    }),
  });
}

export function registerCredential(credentialFilename, chain) {
  return request("/credentials/register", {
    method: "POST",
    body: JSON.stringify({
      credential_filename: credentialFilename,
      chain,
    }),
  });
}

export function revokeCredential(credentialHash, chain) {
  return request("/credentials/revoke", {
    method: "POST",
    body: JSON.stringify({
      credential_hash: credentialHash,
      chain,
    }),
  });
}

export function verifyCredential(token, chain) {
  return request("/credentials/verify", {
    method: "POST",
    body: JSON.stringify({ token, chain }),
  });
}

export function fetchCredentialStatuses(chain) {
  return request(`/credentials/status?chain=${chain}`);
}