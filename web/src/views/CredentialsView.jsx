import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconCheck,
  IconLink,
  IconX,
} from "@tabler/icons-react";

import {
  fetchCredentials,
  fetchCredentialStatuses,
  registerCredential,
  revokeCredential,
} from "../api/client";

/**
 * Maps credential type internal names to a shorter display label.
 */
const TYPE_LABELS = {
  EmploymentCredential: "Employment",
  CertificationCredential: "Certification",
  PeerEndorsement: "Endorsement",
};

/**
 * Derive a status badge from the on-chain status object.
 * Returns null if status hasn't been fetched yet.
 */
function statusBadge(status) {
  if (!status) return null;
  if (!status.exists) {
    return <Badge variant="light" color="gray" size="sm">Not registered</Badge>;
  }
  if (status.revoked) {
    return <Badge variant="light" color="red" size="sm">Revoked</Badge>;
  }
  return <Badge variant="light" color="green" size="sm">Registered</Badge>;
}

export default function CredentialsView({ chain }) {
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  // On-chain status map: credential hash -> status object
  const [statuses, setStatuses] = useState({});
  const [statusesLoading, setStatusesLoading] = useState(false);
  // Track which credential is currently being processed (register or revoke)
  const [processing, setProcessing] = useState(null);

  function loadCredentials() {
    setLoading(true);
    fetchCredentials()
      .then(setCredentials)
      .catch((err) =>
        notifications.show({
          title: "Failed to load credentials",
          message: err.message,
          color: "red",
        })
      )
      .finally(() => setLoading(false));
  }

  // Fetch on-chain statuses for all credentials on the selected chain
  function loadStatuses() {
    setStatusesLoading(true);
    fetchCredentialStatuses(chain)
      .then(setStatuses)
      .catch(() => {
        // Silently ignore -- statuses are supplementary info.
        // The chain backend might not be running.
        setStatuses({});
      })
      .finally(() => setStatusesLoading(false));
  }

  useEffect(() => {
    loadCredentials();
  }, []);

  // Re-fetch statuses when credentials load or chain changes
  useEffect(() => {
    if (credentials.length > 0) {
      loadStatuses();
    }
  }, [credentials, chain]);

  async function handleRegister(cred) {
    setProcessing(cred.filename);
    try {
      const result = await registerCredential(cred.filename, chain);
      notifications.show({
        title: "Registered on-chain",
        message: `Hash: ${result.hash.slice(0, 18)}... | Cost: ${result.cost} ${chain === "iota" ? "NANOS" : "gas"}`,
        color: "green",
        icon: <IconCheck size={18} />,
      });
      // Refresh statuses to reflect the new registration
      loadStatuses();
    } catch (err) {
      notifications.show({
        title: "Registration failed",
        message: err.message,
        color: "red",
      });
    } finally {
      setProcessing(null);
    }
  }

  async function handleRevoke(cred) {
    setProcessing(cred.filename);
    try {
      const result = await revokeCredential(cred.hash, chain);
      notifications.show({
        title: "Revoked on-chain",
        message: `Hash: ${result.hash.slice(0, 18)}... | Cost: ${result.cost} ${chain === "iota" ? "NANOS" : "gas"}`,
        color: "orange",
        icon: <IconCheck size={18} />,
      });
      // Refresh statuses to reflect the revocation
      loadStatuses();
    } catch (err) {
      notifications.show({
        title: "Revocation failed",
        message: err.message,
        color: "red",
      });
    } finally {
      setProcessing(null);
    }
  }

  if (loading) {
    return (
      <Stack align="center" py="xl">
        <Loader color="brand" />
        <Text c="dimmed" size="sm">Loading credentials...</Text>
      </Stack>
    );
  }

  if (credentials.length === 0) {
    return (
      <Alert
        variant="light"
        color="brand"
        title="No credentials"
        icon={<IconAlertCircle size={18} />}
        data-testid="no-credentials"
      >
        No credentials have been issued yet. Use the Issue tab to create one.
      </Alert>
    );
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <div>
          <Title order={3}>Credential Wallet</Title>
          <Text c="dimmed" size="sm">
            {credentials.length} credential{credentials.length !== 1 && "s"} stored locally.
            On-chain operations will use the{" "}
            <Badge variant="light" color="brand" size="sm">
              {chain.toUpperCase()}
            </Badge>{" "}
            chain.
          </Text>
        </div>
        <Button variant="subtle" onClick={loadCredentials} size="xs" data-testid="btn-refresh">
          Refresh
        </Button>
      </Group>

      {credentials.map((cred) => {
        const isProcessing = processing === cred.filename;
        const typeLabel = TYPE_LABELS[cred.credential_type] || cred.credential_type;
        const onChainStatus = statuses[cred.hash] || null;

        return (
          <Card
            key={cred.filename}
            withBorder
            p="md"
            data-testid={`credential-card-${cred.filename}`}
          >
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                <Group gap="xs">
                  <Badge variant="filled" color="brand" size="sm">
                    {typeLabel}
                  </Badge>
                  {statusesLoading
                    ? <Badge variant="light" color="gray" size="sm">Checking...</Badge>
                    : statusBadge(onChainStatus)
                  }
                  <Text size="xs" c="dimmed" truncate>
                    {cred.filename}
                  </Text>
                </Group>

                <Text size="sm" fw={500}>
                  {cred.summary}
                </Text>

                <Group gap="lg">
                  <Text size="xs" c="dimmed">
                    <Text span fw={600}>Issuer:</Text>{" "}
                    <Code>{cred.issuer.slice(0, 24)}...</Code>
                  </Text>
                  <Text size="xs" c="dimmed">
                    <Text span fw={600}>Holder:</Text>{" "}
                    <Code>{cred.holder.slice(0, 24)}...</Code>
                  </Text>
                </Group>

                <Text size="xs" c="dimmed">
                  <Text span fw={600}>Hash:</Text>{" "}
                  <Code>{cred.hash}</Code>
                </Text>
              </Stack>

              <Stack gap="xs">
                {(!onChainStatus || !onChainStatus.exists) && (
                  <Button
                    size="xs"
                    variant="light"
                    leftSection={<IconLink size={14} />}
                    loading={isProcessing}
                    onClick={() => handleRegister(cred)}
                    data-testid={`btn-register-${cred.filename}`}
                  >
                    Register
                  </Button>
                )}
                {onChainStatus?.exists && !onChainStatus?.revoked && (
                  <Button
                    size="xs"
                    variant="light"
                    color="red"
                    leftSection={<IconX size={14} />}
                    loading={isProcessing}
                    onClick={() => handleRevoke(cred)}
                    data-testid={`btn-revoke-${cred.filename}`}
                  >
                    Revoke
                  </Button>
                )}
              </Stack>
            </Group>
          </Card>
        );
      })}
    </Stack>
  );
}