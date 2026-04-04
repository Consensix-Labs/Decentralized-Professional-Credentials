import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Code,
  Group,
  Modal,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconShieldCheck,
  IconShieldX,
  IconAlertTriangle,
  IconQuestionMark,
} from "@tabler/icons-react";

import { verifyCredential } from "../api/client";

/**
 * Visual treatment for each verification result status.
 */
const RESULT_CONFIG = {
  VALID: {
    color: "green",
    icon: IconShieldCheck,
    label: "Valid",
    description: "Signature is valid and the credential is registered on-chain.",
  },
  REVOKED: {
    color: "red",
    icon: IconShieldX,
    label: "Revoked",
    description: "The credential has been revoked by the issuer.",
  },
  EXPIRED: {
    color: "orange",
    icon: IconAlertTriangle,
    label: "Expired",
    description: "The credential has passed its expiration date.",
  },
  UNVERIFIABLE: {
    color: "yellow",
    icon: IconQuestionMark,
    label: "Unverifiable",
    description:
      "Signature is valid but the credential hash was not found on-chain.",
  },
  INVALID_SIGNATURE: {
    color: "red",
    icon: IconShieldX,
    label: "Invalid Signature",
    description: "The JWT signature could not be verified.",
  },
};

/**
 * Format an ISO timestamp or Unix timestamp (seconds) for display.
 * Uses the browser's locale for consistent output across all date fields.
 */
function formatTimestamp(value) {
  if (!value) return null;
  // Unix timestamp (number) -- convert seconds to milliseconds
  if (typeof value === "number") {
    return new Date(value * 1000).toLocaleString();
  }
  // ISO string
  return new Date(value).toLocaleString();
}

export default function VerifyView({ chain }) {
  const [tokenInput, setTokenInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  // Verify requires the raw JWT token. The credentials list endpoint doesn't
  // return tokens, so users paste the JWT (copyable from the Issue result).
  // A future /api/credentials/{filename}/token endpoint would enable a
  // "select from stored" dropdown.

  async function handleVerify() {
    const token = tokenInput.trim();
    if (!token) return;

    setLoading(true);
    setResult(null);

    try {
      const data = await verifyCredential(token, chain);
      setResult(data);
    } catch (err) {
      notifications.show({
        title: "Verification failed",
        message: err.message,
        color: "red",
      });
    } finally {
      setLoading(false);
    }
  }

  const resultConfig = result ? RESULT_CONFIG[result.result] : null;

  return (
    <Stack gap="lg" maw={720}>
      <Title order={3}>Verify a Credential</Title>
      <Text c="dimmed" size="sm">
        Paste a JWT token to verify its signature and check its on-chain status
        on the{" "}
        <Badge variant="light" color="brand" size="sm">
          {chain.toUpperCase()}
        </Badge>{" "}
        chain.
      </Text>

      <Textarea
        label="JWT Token"
        placeholder="eyJhbGciOi..."
        minRows={4}
        maxRows={8}
        autosize
        value={tokenInput}
        onChange={(e) => {
          setTokenInput(e.currentTarget.value);
          setResult(null);
        }}
        data-testid="input-verify-token"
      />

      <Button
        onClick={handleVerify}
        loading={loading}
        disabled={!tokenInput.trim()}
        data-testid="btn-verify"
      >
        Verify Credential
      </Button>

      {/* Verification result modal */}
      <Modal
        opened={!!result}
        onClose={() => setResult(null)}
        title="Verification Result"
        centered
        size="xl"
        data-testid="verify-result"
      >
        {result && resultConfig && (
          <Stack gap="md">
            {/* Status banner with colored background */}
            <Alert
              variant="light"
              color={resultConfig.color}
              icon={<resultConfig.icon size={20} />}
              title={resultConfig.label}
            >
              <Text size="sm">{resultConfig.description}</Text>
            </Alert>

            {/* Signature info */}
            <Group gap="xs">
              <Text size="sm" fw={600}>Signature:</Text>
              <Badge
                color={result.signatureValid ? "green" : "red"}
                variant="light"
                size="sm"
              >
                {result.signatureValid ? "Valid" : "Invalid"}
              </Badge>
            </Group>

            {/* Credential details (only if signature was valid) */}
            {result.credential && (
              <>
                <div>
                  <Text size="sm" fw={600} mb={4}>
                    Credential Details
                  </Text>
                  <Stack gap={4}>
                    <Text size="sm">
                      <Text span fw={600}>Summary:</Text>{" "}
                      {result.credential.summary}
                    </Text>
                    <Text size="sm">
                      <Text span fw={600}>Type:</Text>{" "}
                      {result.credential.type}
                    </Text>
                    <Text size="sm">
                      <Text span fw={600}>Issuer:</Text>{" "}
                      <Code>{result.credential.issuer}</Code>
                    </Text>
                    <Text size="sm">
                      <Text span fw={600}>Holder:</Text>{" "}
                      <Code>{result.credential.holder}</Code>
                    </Text>
                    <Text size="sm">
                      <Text span fw={600}>Valid From:</Text>{" "}
                      {formatTimestamp(result.credential.validFrom) || "N/A"}
                    </Text>
                    <Text size="sm">
                      <Text span fw={600}>Valid Until:</Text>{" "}
                      {formatTimestamp(result.credential.validUntil) || "No expiration"}
                    </Text>
                  </Stack>
                </div>

                <div>
                  <Text size="sm" fw={600} mb={4}>
                    On-Chain Status
                  </Text>
                  <Text size="sm">
                    <Text span fw={600}>Hash:</Text>{" "}
                    <Code>{result.hash}</Code>
                  </Text>

                  {result.onChainStatus ? (
                    <Stack gap={4} mt={8}>
                      <Text size="sm">
                        <Text span fw={600}>Registered:</Text>{" "}
                        {result.onChainStatus.exists ? "Yes" : "No"}
                      </Text>
                      {result.onChainStatus.exists && (
                        <>
                          <Text size="sm">
                            <Text span fw={600}>On-chain Issuer:</Text>{" "}
                            <Code>{result.onChainStatus.issuer}</Code>
                          </Text>
                          <Group gap="xs">
                            <Text size="sm" fw={600}>Issuer Match:</Text>
                            <Badge
                              color={result.issuerMatch ? "green" : "red"}
                              variant="light"
                              size="sm"
                            >
                              {result.issuerMatch ? "Yes" : "Mismatch"}
                            </Badge>
                          </Group>
                          <Text size="sm">
                            <Text span fw={600}>Issued At:</Text>{" "}
                            {formatTimestamp(result.onChainStatus.issuedAt)}
                          </Text>
                          <Text size="sm">
                            <Text span fw={600}>Revoked:</Text>{" "}
                            {result.onChainStatus.revoked ? "Yes" : "No"}
                          </Text>
                        </>
                      )}
                    </Stack>
                  ) : (
                    <Text size="sm" c="dimmed" mt={4}>
                      On-chain status not available.
                    </Text>
                  )}
                </div>
              </>
            )}

            {/* Signature error (if invalid) */}
            {result.signatureError && (
              <Alert color="red" variant="light" title="Signature Error">
                <Text size="sm">{result.signatureError}</Text>
              </Alert>
            )}
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}