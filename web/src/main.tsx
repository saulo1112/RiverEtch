import "@rainbow-me/rainbowkit/styles.css";
import "./index.css";

import { RainbowKitProvider } from "@rainbow-me/rainbowkit";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WagmiProvider } from "wagmi";

import { App } from "./App.tsx";
import { wagmiConfig } from "./wagmi.ts";

const queryClient = new QueryClient();

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("index.html is missing the #root element.");
}

createRoot(rootElement).render(
  <StrictMode>
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider>
          <App />
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  </StrictMode>,
);
