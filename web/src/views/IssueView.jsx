import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Code,
  CopyButton,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
  ActionIcon,
  Tooltip,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconCopy,
} from "@tabler/icons-react";

import {
  fetchKeys,
  fetchCredentialTypes,
  issueCredential,
} from "../api/client";
import CreatableSelect from "../components/CreatableSelect";

/**
 * Human-readable labels for the camelCase claim field names from the API.
 * Falls back to splitting on camelCase boundaries if not listed here.
 */
const FIELD_LABELS = {
  employerName: "Employer Name",
  role: "Role / Title",
  startDate: "Start Date",
  endDate: "End Date",
  department: "Department",
  employmentType: "Employment Type",
  certificationName: "Certification Name",
  certifyingBody: "Certifying Body",
  dateAwarded: "Date Awarded",
  level: "Level",
  endorserName: "Endorser Name",
  relationship: "Relationship",
  skills: "Skills (comma-separated)",
  statement: "Statement",
  context: "Context",
};

function labelFor(field) {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  // Split camelCase into words
  return field.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

/**
 * Fields that should render as multiline text areas.
 */
function isMultilineField(field) {
  return field === "statement";
}

/**
 * Fields whose names contain "date" or "Date" use a calendar picker.
 * Mantine 8 DateInput uses string values in YYYY-MM-DD format.
 */
function isDateField(field) {
  return field.toLowerCase().includes("date");
}

export default function IssueView() {
  const [keys, setKeys] = useState([]);
  const [credTypes, setCredTypes] = useState([]);
  const [loading, setLoading] = useState(false);

  // Form state
  const [selectedType, setSelectedType] = useState(null);
  const [issuerKey, setIssuerKey] = useState(null);
  const [holderDid, setHolderDid] = useState("");
  const [claims, setClaims] = useState({});
  const [validUntil, setValidUntil] = useState(null);

  // Result after successful issuance
  const [result, setResult] = useState(null);

  // Load keys and credential types on mount
  useEffect(() => {
    fetchKeys()
      .then(setKeys)
      .catch((err) =>
        notifications.show({
          title: "Failed to load keys",
          message: err.message,
          color: "red",
        })
      );

    fetchCredentialTypes()
      .then(setCredTypes)
      .catch((err) =>
        notifications.show({
          title: "Failed to load credential types",
          message: err.message,
          color: "red",
        })
      );
  }, []);

  // Reset claims form when credential type changes
  const activeType = credTypes.find((t) => t.name === selectedType);
  const allFields = activeType
    ? [...activeType.required_fields, ...activeType.optional_fields]
    : [];

  function handleTypeChange(val) {
    setSelectedType(val);
    setClaims({});
    setValidUntil(null);
    setResult(null);
  }

  function updateClaim(field, value) {
    setClaims((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit() {
    if (!selectedType || !issuerKey || !holderDid) return;

    setLoading(true);
    setResult(null);

    try {
      // Convert the skills field from comma-separated string to array
      const processedClaims = { ...claims };
      if (processedClaims.skills && typeof processedClaims.skills === "string") {
        processedClaims.skills = processedClaims.skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      }

      // Remove empty optional fields
      for (const key of Object.keys(processedClaims)) {
        if (processedClaims[key] === "") {
          delete processedClaims[key];
        }
      }

      const data = await issueCredential({
        credentialType: selectedType,
        issuerKeyName: issuerKey,
        holderDid,
        claims: processedClaims,
        validUntil: validUntil || null,
      });

      setResult(data);
    } catch (err) {
      notifications.show({
        title: "Issuance failed",
        message: err.message,
        color: "red",
      });
    } finally {
      setLoading(false);
    }
  }

  const keyOptions = keys.map((k) => ({
    value: k.name,
    label: `${k.name} (${k.did.slice(0, 20)}...)`,
  }));

  // Holder options use the DID as value (the API expects a DID string)
  const holderOptions = keys.map((k) => ({
    value: k.did,
    label: `${k.name} (${k.did.slice(0, 20)}...)`,
  }));

  const typeOptions = credTypes.map((t) => ({
    value: t.name,
    label: t.name.charAt(0).toUpperCase() + t.name.slice(1),
  }));

  return (
    <Stack gap="lg" maw={640}>
      <Title order={3}>Issue a Credential</Title>
      <Text c="dimmed" size="sm">
        Create and sign a new W3C Verifiable Credential. The signed JWT will be
        stored locally and can then be registered on-chain.
      </Text>

      <Select
        label="Credential Type"
        placeholder="Select type"
        data={typeOptions}
        value={selectedType}
        onChange={handleTypeChange}
        data-testid="select-credential-type"
      />

      <Select
        label="Issuer Keypair"
        placeholder="Select issuer"
        data={keyOptions}
        value={issuerKey}
        onChange={setIssuerKey}
        data-testid="select-issuer-key"
      />

      <CreatableSelect
        label="Holder DID"
        placeholder="Select or paste a DID"
        data={holderOptions}
        value={holderDid}
        onChange={setHolderDid}
        data-testid="select-holder-did"
      />

      {/* Dynamic claims fields based on selected credential type */}
      {activeType && (
        <Card withBorder p="md">
          <Title order={5} mb="sm">
            Claims
          </Title>
          <Stack gap="sm">
            {allFields.map((field) => {
              const required = activeType.required_fields.includes(field);
              const label = labelFor(field);

              if (isMultilineField(field)) {
                return (
                  <Textarea
                    key={field}
                    label={label}
                    required={required}
                    autosize
                    minRows={2}
                    maxRows={4}
                    value={claims[field] || ""}
                    onChange={(e) => updateClaim(field, e.currentTarget.value)}
                    data-testid={`input-claim-${field}`}
                  />
                );
              }

              if (isDateField(field)) {
                return (
                  <DateInput
                    key={field}
                    label={label}
                    required={required}
                    placeholder="Select date"
                    valueFormat="YYYY-MM-DD"
                    clearable
                    value={claims[field] || null}
                    onChange={(val) => updateClaim(field, val || "")}
                    data-testid={`input-claim-${field}`}
                  />
                );
              }

              return (
                <TextInput
                  key={field}
                  label={label}
                  required={required}
                  value={claims[field] || ""}
                  onChange={(e) => updateClaim(field, e.currentTarget.value)}
                  data-testid={`input-claim-${field}`}
                />
              );
            })}
          </Stack>
        </Card>
      )}

      {/* Expiration date -- relevant for certifications */}
      {selectedType === "certification" && (
        <DateInput
          label="Expiration Date (optional)"
          placeholder="Select date"
          valueFormat="YYYY-MM-DD"
          clearable
          value={validUntil}
          onChange={setValidUntil}
          data-testid="input-valid-until"
        />
      )}

      <Button
        onClick={handleSubmit}
        loading={loading}
        disabled={!selectedType || !issuerKey || !holderDid}
        data-testid="btn-issue"
      >
        Issue Credential
      </Button>

      {/* Issue result modal */}
      <Modal
        opened={!!result}
        onClose={() => setResult(null)}
        title="Credential Issued"
        centered
        size="xl"
        data-testid="issue-result"
      >
        {result && (
          <Alert
            variant="light"
            color="green"
            icon={<IconCheck size={20} />}
          >
            <Stack gap="sm">
              <Text size="sm">
                <Text span fw={600}>File:</Text> {result.filename}
              </Text>
              <Text size="sm">
                <Text span fw={600}>Hash:</Text>{" "}
                <Code>{result.hash}</Code>
              </Text>
              <Text size="sm">
                <Text span fw={600}>Summary:</Text> {result.summary}
              </Text>
              <Group gap="xs" align="center">
                <Text size="sm" fw={600}>Token:</Text>
                <CopyButton value={result.token}>
                  {({ copied, copy }) => (
                    <Tooltip label={copied ? "Copied" : "Copy JWT token"}>
                      <ActionIcon
                        variant="subtle"
                        color={copied ? "green" : "gray"}
                        onClick={copy}
                        size="sm"
                        data-testid="btn-copy-token"
                      >
                        {copied ? (
                          <IconCheck size={14} />
                        ) : (
                          <IconCopy size={14} />
                        )}
                      </ActionIcon>
                    </Tooltip>
                  )}
                </CopyButton>
              </Group>
            </Stack>
          </Alert>
        )}
      </Modal>
    </Stack>
  );
}