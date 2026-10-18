import "@rainbow-me/rainbowkit/styles.css";
import "./index.css";

import { darkTheme, RainbowKitProvider, type Theme } from "@rainbow-me/rainbowkit";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WagmiProvider } from "wagmi";

import { App } from "./App.tsx";
import { BRAND_NAME } from "./features/hero/ui/content.ts";
import { wagmiConfig } from "./wagmi.ts";

const queryClient = new QueryClient();

// RainbowKit's dialogs in the app's colors and type (styles/tokens.css).
const darkWallet = darkTheme({
  accentColor: "#22d3ee",
  accentColorForeground: "#04101f",
  borderRadius: "medium",
  overlayBlur: "small",
});
const walletTheme: Theme = {
  ...darkWallet,
  fonts: { body: '"Inter Tight Variable", system-ui, -apple-system, "Segoe UI", sans-serif' },
};

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("index.html is missing the #root element.");
}

createRoot(rootElement).render(
  <StrictMode>
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider theme={walletTheme} appInfo={{ appName: BRAND_NAME }}>
          <App />
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  </StrictMode>,
);
