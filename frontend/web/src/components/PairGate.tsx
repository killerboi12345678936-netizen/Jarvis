import { useState } from "react";
import { KeyRound, ShieldCheck } from "lucide-react";
import { apiPost, setDeviceToken } from "../lib/api";

type PairGateProps = {
  onPaired: () => void;
};

export function PairGate({ onPaired }: PairGateProps) {
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!token.trim() || busy) return;

    setBusy(true);
    setError(null);

    try {
      await apiPost("/api/auth/pair", { token: token.trim() });

      setDeviceToken(token.trim());
      onPaired();
    } catch (pairError) {
      setError(
        pairError instanceof Error
          ? pairError.message
          : "Pairing failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pair-gate">
      <div className="pair-card">
        <div className="pair-icon">
          <ShieldCheck size={30} />
        </div>

        <h1>Pair this device</h1>
        <p>
          Enter the device code shown in the Jarvis launcher window on
          your laptop (also stored in{" "}
          <code>data\device_token.txt</code>).
        </p>

        <div className="pair-input-row">
          <KeyRound size={17} />
          <input
            type="password"
            placeholder="Device code"
            value={token}
            onChange={(event) => setTokenInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void submit();
            }}
            autoFocus
          />
        </div>

        {error && <div className="pair-error">{error}</div>}

        <button
          className="voice-primary-button"
          onClick={() => void submit()}
          disabled={busy || !token.trim()}
        >
          {busy ? "Checking..." : "Connect to Jarvis"}
        </button>
      </div>
    </div>
  );
}
