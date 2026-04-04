import { useState } from "react";
import {
  Anchor,
  Box,
  Group,
  Image,
  SegmentedControl,
  Tabs,
  Text,
  Title,
  Badge,
} from "@mantine/core";
import {
  IconCertificate,
  IconWallet,
  IconShieldCheck,
} from "@tabler/icons-react";

import IssueView from "./views/IssueView";
import CredentialsView from "./views/CredentialsView";
import VerifyView from "./views/VerifyView";

export default function App() {
  const [activeTab, setActiveTab] = useState("issue");
  const [chain, setChain] = useState("evm");

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>

      {/* Header */}
      <header
        style={{
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "8px",
          borderBottom: "2px solid var(--mantine-color-brand-1)",
        }}
      >
        <Group gap="sm" style={{ rowGap: 4 }} wrap="wrap">
          <Title order={4} c="brand.9" data-testid="app-title">
            Decentralized Professional Credentials
          </Title>
          <Badge variant="light" color="brand" size="sm">
            Research Demo
          </Badge>
        </Group>

        <SegmentedControl
          data-testid="chain-selector"
          value={chain}
          onChange={setChain}
          data={[
            { label: "EVM", value: "evm" },
            { label: "IOTA", value: "iota" },
          ]}
          size="sm"
          color="brand"
        />
      </header>

      {/* Main content */}
      <main style={{ flex: 1, padding: "var(--mantine-spacing-lg)" }}>
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List mb="lg">
            <Tabs.Tab
              value="issue"
              leftSection={<IconCertificate size={18} />}
              data-testid="tab-issue"
            >
              Issue
            </Tabs.Tab>
            <Tabs.Tab
              value="credentials"
              leftSection={<IconWallet size={18} />}
              data-testid="tab-credentials"
            >
              Credentials
            </Tabs.Tab>
            <Tabs.Tab
              value="verify"
              leftSection={<IconShieldCheck size={18} />}
              data-testid="tab-verify"
            >
              Verify
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="issue">
            <IssueView />
          </Tabs.Panel>
          <Tabs.Panel value="credentials">
            <CredentialsView chain={chain} />
          </Tabs.Panel>
          <Tabs.Panel value="verify">
            <VerifyView chain={chain} />
          </Tabs.Panel>
        </Tabs>
      </main>

      {/* Footer */}
      <footer
        style={{
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderTop: "1px solid var(--mantine-color-brand-1)",
        }}
        data-testid="footer"
      >
        <Anchor
          href="https://consensixlabs.com"
          target="_blank"
          underline="never"
          data-testid="footer-link"
        >
          <Group gap={6}>
            <Text size="sm" c="dimmed">Built by</Text>
            <Image src="/logo.svg" h={20} w="auto" alt="Consensix Labs logo" />
            <Text
              size="sm"
              c="brand.9"
              fw={600}
              style={{
                fontFamily: "'Roboto Condensed', sans-serif",
                letterSpacing: "-0.05em",
              }}
            >
              Consensix Labs
            </Text>
          </Group>
        </Anchor>
      </footer>
    </div>
  );
}