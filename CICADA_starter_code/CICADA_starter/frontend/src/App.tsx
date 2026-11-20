import { useEffect, useState } from "react";
import { Activity, ShieldCheck, Server, AlertTriangle, RefreshCw } from "lucide-react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DEMO_KEY = "change-this-demo-key";
type Summary = {
  tenant_id: string; records_returned: number; latest_metrics: Record<string, number>;
  records: Array<{observed_at:string;service:string;metric_name:string;metric_value:number;unit:string}>;
};

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [anomaly, setAnomaly] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const headers = { Authorization: `Bearer ${DEMO_KEY}` };
      const [s, a] = await Promise.all([
        fetch(`${API}/api/v1/dashboard/summary`, {headers}),
        fetch(`${API}/api/v1/anomalies/preview`, {headers})
      ]);
      if (!s.ok || !a.ok) throw new Error("API unavailable. Start the central API and verify the demo key.");
      setSummary(await s.json()); setAnomaly(await a.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load data"); }
  }
  useEffect(() => { void load(); }, []);

  return <main className="shell">
    <header><div className="brand"><span className="mark"><Activity/></span><div><b>CICADA</b><small>SECURE AIOPS OBSERVABILITY</small></div></div><span className="live">● DEMO ENVIRONMENT</span></header>
    <section className="hero"><div><p className="eyebrow">CENTRAL SAAS / FLEET OVERVIEW</p><h1>Operational intelligence.<br/><em>Privacy by architecture.</em></h1><p className="muted">Only policy-approved metadata is displayed. Raw customer telemetry remains local.</p></div><button onClick={load}><RefreshCw size={16}/> Refresh</button></section>
    {error && <div className="error">{error}</div>}
    <section className="grid">
      <article><label><Server/> TENANT</label><strong>{summary?.tenant_id ?? "—"}</strong><small>Authenticated demo identity</small></article>
      <article><label><Activity/> INGESTED RECORDS</label><strong>{summary?.records_returned ?? "—"}</strong><small>Recent metadata records</small></article>
      <article><label><ShieldCheck/> PRIVACY MODEL</label><strong>Allowlist</strong><small>Explicit outbound projection</small></article>
      <article><label><AlertTriangle/> DETECTOR</label><strong>{anomaly?.status ?? "—"}</strong><small>{anomaly?.anomaly == null ? "Baseline feature set pending" : anomaly.anomaly ? "Potential outlier detected" : "No outlier detected"}</small></article>
    </section>
    <section className="panel"><div className="panel-title"><div><p className="eyebrow">TELEMETRY</p><h2>Latest approved metadata</h2></div><span>Tenant-scoped view</span></div>
      <div className="table-wrap"><table><thead><tr><th>TIME</th><th>SERVICE</th><th>METRIC</th><th>VALUE</th></tr></thead><tbody>
      {summary?.records.map((r,i)=><tr key={`${r.metric_name}-${i}`}><td>{new Date(r.observed_at).toLocaleTimeString()}</td><td>{r.service}</td><td>{r.metric_name}</td><td>{r.metric_value} {r.unit}</td></tr>)}
      {!summary?.records.length && <tr><td colSpan={4} className="empty">No metadata received. Run the customer agent.</td></tr>}
      </tbody></table></div></section>
    <section className="panel privacy"><ShieldCheck/><div><b>Customer data boundary</b><p>The demo agent sends metric summaries only. Raw message text and arbitrary attributes are excluded from the outbound object.</p></div></section>
    <footer>HACKATHON PROTOTYPE · NOT PRODUCTION-HARDENED</footer>
  </main>;
}
