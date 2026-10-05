import { ConnectButton } from "@rainbow-me/rainbowkit";

/** Props of {@link LayerCard}. */
interface LayerCardProps {
  /** Layer name, shown as the card title. */
  readonly title: string;
  /** What the layer will do, in one or two sentences. */
  readonly description: string;
}

/**
 * Placeholder card for one architectural layer until its features are built.
 *
 * @returns The rendered card.
 */
function LayerCard({ title, description }: LayerCardProps) {
  return (
    <section className="layer-card">
      <h2>{title}</h2>
      <p>{description}</p>
      <span className="badge">Coming soon</span>
    </section>
  );
}

/**
 * Application shell: wallet connection plus one placeholder per architectural layer.
 *
 * @returns The root UI of the dApp.
 */
export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Climate Change IEEE</h1>
          <p className="tagline">
            River turbidity anomalies, extreme rainfall and private permit compliance.
          </p>
        </div>
        <ConnectButton />
      </header>

      <main className="layers">
        <LayerCard
          title="Public layer: satellite detection"
          description="Turbidity anomalies on Colombian rivers detected from Sentinel-2 imagery and correlated with extreme rainfall. Open data and open code, so anyone can reproduce them."
        />
        <LayerCard
          title="Private layer: ZK compliance"
          description="Mining operators prove that their discharges stayed within their permit with a zero-knowledge proof verified on-chain, without revealing their operational data."
        />
      </main>

      <footer className="app-footer">Hackathon scaffold · Sepolia testnet</footer>
    </div>
  );
}
