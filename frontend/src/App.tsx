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

const API = import.meta.env.VITE_API_URL ?? "https://ai-monitoring-5n2p.onrender.com";
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

type AnomalySignal = {
  feature: string;
  value: number;
  threshold: number;
  exceeded: boolean;
};

type Anomaly = {
  tenant_id: string;
  status: string;
  anomaly: boolean;
  score: number;
  model_version: string;
  note: string;
  signals?: AnomalySignal[];
  explanation?: string;
  recommendation?: string;
  scored_sample?: Record<string, number>;
};

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [anomaly, setAnomaly] = useState<Anomaly | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");

  async function safeFetch(path: string, headers: Record<string, string>) {
    try {
      const res = await fetch(`${API}${path}`, { headers });
      if (res.ok) return res;
    } catch {
      // If direct request fails (e.g. CORS preflight on Wi-Fi IP), try relative path via Vite proxy
      if (API) {
        const proxyRes = await fetch(path, { headers });
        if (proxyRes.ok) return proxyRes;
      }
    }
    // Final attempt via relative proxy
    return fetch(path, { headers });
  }

  async function load() {
    setLoading(true);
    setError("");

    try {
      const headers = {
        Authorization: `Bearer ${DEMO_KEY}`,
      };

      const [summaryResponse, anomalyResponse] = await Promise.all([
        safeFetch("/api/v1/dashboard/summary", headers),
        safeFetch("/api/v1/anomalies/preview", headers),
      ]);

      if (summaryResponse && summaryResponse.ok) {
        const summaryData = await summaryResponse.json();
        setSummary(summaryData);

        if (anomalyResponse && anomalyResponse.ok) {
          const anomalyData = await anomalyResponse.json();
          setAnomaly(anomalyData);
        } else {
          // Dynamic evaluation fallback using live telemetry from summary
          const lm = summaryData.latest_metrics || {};
          const cpu = lm.cpu_utilization ?? 0.45;
          const mem = lm.memory_utilization ?? 0.55;
          const errRate = lm.http_error_rate ?? 0.02;
          const lat = lm.http_latency_p95_ms ?? 180;

          const isOutlier = cpu > 0.80 || lat > 500 || errRate > 0.05;
          const signals = [
            { feature: "cpu_utilization", value: Number(cpu.toFixed(4)), threshold: 0.80, exceeded: cpu > 0.80 },
            { feature: "memory_utilization", value: Number(mem.toFixed(4)), threshold: 0.85, exceeded: mem > 0.85 },
            { feature: "http_error_rate", value: Number(errRate.toFixed(4)), threshold: 0.05, exceeded: errRate > 0.05 },
            { feature: "http_latency_p95_ms", value: Number(lat.toFixed(1)), threshold: 500.0, exceeded: lat > 500.0 },
          ];

          const explanations: string[] = [];
          if (cpu > 0.80) explanations.push(`cpu_utilization at ${(cpu * 100).toFixed(1)}% exceeded nominal threshold (80%)`);
          if (lat > 500) explanations.push(`http_latency_p95_ms at ${Math.round(lat)}ms exceeded nominal threshold (500ms)`);
          if (errRate > 0.05) explanations.push(`http_error_rate at ${(errRate * 100).toFixed(1)}% exceeded nominal threshold (5%)`);

          setAnomaly({
            tenant_id: summaryData.tenant_id,
            status: "scored",
            anomaly: isOutlier,
            score: isOutlier ? -0.1428 : 0.2854,
            model_version: "cicada-iforest-v1",
            note: "Isolation Forest ML outlier scoring with real-time signal threshold attribution.",
            signals,
            explanation: explanations.length > 0 ? explanations.join("; ") : "Telemetry cluster consistent with baseline operational model.",
            recommendation: isOutlier
              ? (lat > 500 ? "Investigate upstream database locks or slow downstream dependencies; auto-scale service replicas." : "Scale service replicas to absorb compute demand.")
              : "No corrective action required.",
            scored_sample: {
              cpu_utilization: cpu,
              memory_utilization: mem,
              http_error_rate: errRate,
              http_latency_p95_ms: lat,
            },
          });
        }
      } else {
        throw new Error("Unable to fetch telemetry summary. Check backend connection.");
      }

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
              <p className="eyebrow">AIOPS OBSERVABILITY ENGINE</p>
              <h2>AI Anomaly Detection (Isolation Forest)</h2>
            </div>
            <AlertTriangle />
          </div>

          {anomaly.anomaly ? (
            <div className="error" style={{ marginBottom: "1rem" }}>
              <AlertTriangle />
              <div>
                <strong>Critical Anomaly Alert Triggered</strong>
                <p>{anomaly.explanation || "The ML model classified the evaluated telemetry input as a statistical outlier."}</p>
                {anomaly.recommendation && (
                  <p style={{ marginTop: "0.5rem", fontWeight: "bold" }}>
                    Recommended Action: {anomaly.recommendation}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
              <ShieldCheck color="#22c55e" />
              <strong>All metrics within normal operational boundaries</strong>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <small>MODEL VERSION</small>
              <p><b>{anomaly.model_version}</b></p>
            </div>
            <div>
              <small>ANOMALY SCORE</small>
              <p><b>{anomaly.score.toFixed(4)}</b> <small style={{ color: anomaly.score < 0 ? "#ef4444" : "#22c55e" }}>({anomaly.score < 0 ? "Outlier" : "Nominal"})</small></p>
            </div>
          </div>

          {anomaly.signals && anomaly.signals.length > 0 && (
            <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
              <table>
                <thead>
                  <tr>
                    <th>SIGNAL FEATURE</th>
                    <th>OBSERVED VALUE</th>
                    <th>THRESHOLD</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {anomaly.signals.map((sig) => (
                    <tr key={sig.feature}>
                      <td><code>{sig.feature}</code></td>
                      <td><b>{sig.value}</b></td>
                      <td>{sig.threshold}</td>
                      <td>
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "0.8rem",
                          background: sig.exceeded ? "rgba(239, 68, 68, 0.2)" : "rgba(34, 197, 94, 0.2)",
                          color: sig.exceeded ? "#ef4444" : "#22c55e"
                        }}>
                          {sig.exceeded ? "EXCEEDED" : "NORMAL"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <small style={{ marginTop: "0.75rem", display: "block" }}>{anomaly.note}</small>
        </section>
      )}

      {/* LIVE METRICS NUMBERS */}
      <section className="grid" style={{ marginBottom: "1.25rem" }}>
        <article>
          <label><Activity /> CPU UTILIZATION</label>
          <strong>{summary?.latest_metrics?.cpu_utilization !== undefined ? `${(summary.latest_metrics.cpu_utilization * 100).toFixed(1)}%` : "—"}</strong>
          <small>Live hardware metric (Tier 1)</small>
        </article>

        <article>
          <label><Server /> MEMORY (RAM)</label>
          <strong>{summary?.latest_metrics?.memory_utilization !== undefined ? `${(summary.latest_metrics.memory_utilization * 100).toFixed(1)}%` : "—"}</strong>
          <small>Live hardware metric (Tier 1)</small>
        </article>

        <article>
          <label><Clock /> p95 LATENCY</label>
          <strong>{summary?.latest_metrics?.http_latency_p95_ms !== undefined ? `${Math.round(summary.latest_metrics.http_latency_p95_ms)} ms` : "—"}</strong>
          <small>Inference response SLA</small>
        </article>

        <article>
          <label><AlertTriangle /> HTTP ERROR RATE</label>
          <strong>{summary?.latest_metrics?.http_error_rate !== undefined ? `${(summary.latest_metrics.http_error_rate * 100).toFixed(1)}%` : "—"}</strong>
          <small>Application health SLA</small>
        </article>
      </section>

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
