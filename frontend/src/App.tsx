import { useEffect, useState } from "react";
import {
  Activity,
  ShieldCheck,
  Server,
  AlertTriangle,
  RefreshCw,
  Clock,
  Zap,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DEMO_KEY = "change-this-demo-key";
const REFRESH_INTERVAL = 10000;

type Summary = {
  tenant_id: string;
  records_returned: number;
  latest_metrics: Record<string, number>;
  records: Array<{
    observed_at: string;
    service: string;
    metric_name: string;
    metric_value: number;
    unit: string;
  }>;
};

type Anomaly = {
  tenant_id: string;
  status: string;
  anomaly: boolean;
  score: number;
  model_version: string;
  note: string;
};

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [anomaly, setAnomaly] = useState<Anomaly | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");

  async function load() {
    setLoading(true);
    setError("");

    try {
      const headers = {
        Authorization: `Bearer ${DEMO_KEY}`,
      };

      const [summaryResponse, anomalyResponse] = await Promise.all([
        fetch(`${API}/api/v1/dashboard/summary`, { headers }),
        fetch(`${API}/api/v1/anomalies/preview`, { headers }),
      ]);

      if (!summaryResponse.ok || !anomalyResponse.ok) {
        throw new Error("API request failed. Check the backend.");
      }

      const summaryData = await summaryResponse.json();
      const anomalyData = await anomalyResponse.json();

      setSummary(summaryData);
      setAnomaly(anomalyData);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect to API"
      );
    } finally {
      setLoading(false);
    }
  }

  // Initial load and automatic refresh every 10 seconds
  useEffect(() => {
    void load();

    const timer = setInterval(() => {
      void load();
    }, REFRESH_INTERVAL);

    return () => clearInterval(timer);
  }, []);

  return (
    <main className="shell">
      <header>
        <div className="brand">
          <span className="mark">
            <Activity />
          </span>
          <div>
            <b>CICADA</b>
            <small>SECURE AIOPS OBSERVABILITY</small>
          </div>
        </div>

        <span className="live">● DEMO ENVIRONMENT</span>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">CENTRAL SAAS / FLEET OVERVIEW</p>
          <h1>
            Operational intelligence.
            <br />
            <em>Privacy by architecture.</em>
          </h1>
          <p className="muted">
            Policy approved telemetry monitoring and ML‑based anomaly
            detection.
          </p>
        </div>

        <button onClick={() => void load()} disabled={loading}>
          <RefreshCw size={16} />
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      {error && <div className="error">{error}</div>}

      {/* ANOMALY ALERT */}
      {anomaly?.status === "scored" && (
        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">ML SECURITY MONITOR</p>
              <h2>Anomaly Detection</h2>
            </div>
            <AlertTriangle />
          </div>

          {anomaly.anomaly ? (
            <div className="error">
              <AlertTriangle />
              <div>
                <strong>Potential anomaly detected</strong>
                <p>
                  The ML model classified the evaluated input as an outlier.
                </p>
              </div>
            </div>
          ) : (
            <div>
              <ShieldCheck />
              <strong>No outlier detected</strong>
            </div>
          )}

          <p>Model: {anomaly.model_version}</p>
          <p>Anomaly score: {anomaly.score.toFixed(4)}</p>
          <small>{anomaly.note}</small>
        </section>
      )}

      <section className="grid">
        <article>
          <label>
            <Server /> TENANT
          </label>
          <strong>{summary?.tenant_id ?? "—"}</strong>
          <small>Authenticated demo identity</small>
        </article>

        <article>
          <label>
            <Activity /> INGESTED RECORDS
          </label>
          <strong>{summary?.records_returned ?? "—"}</strong>
          <small>Recent metadata records</small>
        </article>

        <article>
          <label>
            <ShieldCheck /> PRIVACY MODEL
          </label>
          <strong>Allowlist</strong>
          <small>Explicit outbound projection</small>
        </article>

        <article>
          <label>
            <Zap /> DETECTOR
          </label>
          <strong>{anomaly?.status ?? "—"}</strong>
          <small>
            {anomaly?.anomaly == null
              ? "Waiting for model result"
              : anomaly.anomaly
                ? "Potential outlier detected"
                : "No outlier detected"}
          </small>
        </article>
      </section>

      <section className="panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow">TELEMETRY</p>
            <h2>Latest approved metadata</h2>
          </div>
          <span>Tenant‑scoped view</span>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>TIME</th>
                <th>SERVICE</th>
                <th>METRIC</th>
                <th>VALUE</th>
              </tr>
            </thead>

            <tbody>
              {summary?.records.map((record, index) => (
                <tr key={`${record.metric_name}-${index}`}>
                  <td>{new Date(record.observed_at).toLocaleTimeString()}</td>
                  <td>{record.service}</td>
                  <td>{record.metric_name}</td>
                  <td>{record.metric_value} {record.unit}</td>
                </tr>
              ))}

              {!summary?.records.length && (
                <tr>
                  <td colSpan={4} className="empty">
                    No metadata received. Run the customer agent.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel privacy">
        <ShieldCheck />
        <div>
          <b>Customer data boundary</b>
          <p>
            The demo agent sends approved metric summaries only. Raw message
            text and arbitrary attributes are excluded from the outbound
            object.
          </p>
        </div>
      </section>

      <footer>
        <Clock size={14} />
        Last updated: {lastUpdated || "Waiting..."}
        <br />
        AUTOMATIC REFRESH: 10 SECONDS
        <br />
        HACKATHON PROTOTYPE · NOT PRODUCTION‑HARDENED
      </footer>
    </main>
  );
}
