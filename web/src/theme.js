/**
 * Mantine 8 theme overrides.
 *
 * Uses Consensix Labs brand palette:
 *   - Dark navy (#1a2478) as primary
 *   - Accent blue (#2635aa) for interactive elements
 *   - Light blue-grey (#f0f2fa) for backgrounds
 */
import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "brand",
  colors: {
    // 10-shade palette anchored on the Consensix navy/blue
    brand: [
      "#f0f2fa", // 0 - lightest background
      "#d0d5f0", // 1
      "#b0b7dc", // 2
      "#8e98c8", // 3
      "#6e7ab4", // 4
      "#4f5da0", // 5
      "#3a4a96", // 6
      "#2635aa", // 7 - accent blue
      "#1f2d8e", // 8
      "#1a2478", // 9 - dark navy
    ],
  },
  fontFamily:
    "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  headings: {
    fontFamily:
      "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    fontWeight: "600",
  },
  defaultRadius: "sm",
});
