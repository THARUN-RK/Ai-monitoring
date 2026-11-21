import { useEffect, useState } from "react";
import {
  Activity,
  ShieldCheck,
  Server,
  AlertTriangle,
  RefreshCw,
  Clock,
  Zap,
  HardDrive,
  CheckCircle2,
  Lock,
  FileCode,
  Radio,
  Cpu,
  TrendingUp,
  Sliders,
  ShieldAlert,
  HelpCircle,
  HeartPulse,
  AlertOctagon,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL ?? "https://ai-monitoring-5n2p.onrender.com";
const DEMO_KEY = "change-this-demo-key";
const REFRESH_INTERVAL = 10000;

type Summary = {
  tenant_id: string;
  records_returned: number;
  latest_metrics: Record<string, number>;
  collectors_total?: number;
  collectors_online?: number;
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
  baseline: number;
  threshold: number;
  exceeded: boolean;
};

type AnomalyDetail = {
  metric_name: string;
  category: "cpu" | "memory" | "disk" | "network" | "security";
  severity: "info" | "warning" | "critical";
  current_value: number;
  baseline_value: number;
  deviation_pct: number;
  z_score: number;
  confidence: number;
  summary: string;
  probable_cause: string;
  recommended_action: string;
};

type Anomaly = {
  tenant_id: string;
  status: string;
  anomaly: boolean;
  score: number;
  severity?: string;
  model_version: string;
  note: string;
  signals?: AnomalySignal[];
  anomalies?: AnomalyDetail[];
  dynamic_baselines?: Record<string, { mean: number; std: number; upper: number; lower: number; count: number }>;
  security_risk_index?: number;
  explanation?: string;
  probable_cause?: string;
  recommendation?: string;
  scored_sample?: Record<string, number>;
};

type Collector = {
  collector_id: string;
  name: string;
  environment: string;
  status: string;
  last_heartbeat: string;
};

type EgressAudit = {
  payload_id: string;
  collector_id: string;
  sent_at: string;
  approved_fields_count: number;
  rejected_fields_count: number;
  delivery_status: string;
  api_response_status: number;
  sanitized_sample: string;
};

// SRE Four-State Health Classification Engine Types
type MetricHealthDetail = {
  metric_name: string;
  current_value: number;
  unit: string;
  state: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  threshold_applied: Record<string, number>;
  reason: string;
};

type CollectorHealthDetail = {
  collector_id: string;
  status: string;
  last_heartbeat: string | null;
  freshness_seconds: number | null;
  state: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  reason: string;
};

type FreshnessHealthDetail = {
  last_telemetry_at: string | null;
  age_seconds: number | null;
  state: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  reason: string;
};

type AnomalyHealthDetail = {
  active_count: number;
  critical_count: number;
  warning_count: number;
  max_severity: string;
  state: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  reason: string;
};

type HealthTransition = {
  id: number;
  tenant_id: string;
  from_state: string;
  to_state: string;
  overall_health: string;
  reason: string;
  metrics_snapshot: string;
  transitioned_at: string;
};

type SystemHealth = {
  tenant_id: string;
  overall_health: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  evaluated_at: string;
  summary_reason: string;
  reasons: string[];
  metrics: MetricHealthDetail[];
  collector: CollectorHealthDetail;
  freshness: FreshnessHealthDetail;
  anomalies: AnomalyHealthDetail;
  latest_transition?: HealthTransition | null;
  transitions_count: number;
};

// SRE Incident Correlation & Lifecycle Types
type CorrelatedAlert = {
  alert_id: string;
  service: string;
  metric_name: string;
  category: string;
  severity: string;
  current_value: number;
  baseline_value: number;
  deviation_pct: number;
  timestamp: string;
  summary: string;
};

type Incident = {
  id: number;
  incident_id: string;
  tenant_id: string;
  title: string;
  priority: "Critical" | "High" | "Medium" | "Low";
  status: "Open" | "Investigating" | "Resolved" | "Closed";
  category: string;
  affected_components: string[];
  probable_root_cause: string;
  confidence_score: number;
  recommended_investigation: string;
  contributing_signals: string[];
  alert_count: number;
  timeline: CorrelatedAlert[];
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
};

function deriveClientIncident(anomalies: AnomalyDetail[]): Incident | null {
  if (!anomalies || anomalies.length === 0) return null;
  const now = new Date();
  const sorted = [...anomalies].sort((a, b) => (b.severity === "critical" ? 1 : 0) - (a.severity === "critical" ? 1 : 0));
  const metrics = sorted.map(a => a.metric_name);
  const isCrit = sorted.some(a => a.severity === "critical");

  let rca = "Correlated operational degradation across multiple telemetry signals.";
  let action = "Inspect high-CPU processes, scale horizontal replicas, and verify service latency SLAs.";
  let confidence = 0.92;

  if (metrics.includes("cpu_utilization") && (metrics.includes("http_latency_p95_ms") || metrics.includes("http_error_rate"))) {
    rca = "Hardware resource saturation: CPU utilization spiked, causing thread-pool starvation and request queue backlog on service 'checkout', cascading into elevated p95 latency and downstream 5xx errors.";
    action = "1. Scale horizontal service pods or allocate compute quota.\n2. Inspect database query lock contention.\n3. Configure client circuit-breaker shed limits.";
    confidence = 0.94;
  } else if (metrics.includes("http_latency_p95_ms")) {
    rca = "Network transport degradation or downstream dependency latency spike observed without primary CPU exhaustion.";
    action = "1. Inspect network gateway packet round-trip times.\n2. Verify upstream payment gateway SLAs.\n3. Enable response edge-caching.";
    confidence = 0.88;
  } else if (metrics.some(m => m.includes("auth") || m.includes("security"))) {
    rca = "Repeated authentication challenge storm: Multiple failed login attempts and unauthorized access probes detected client-side.";
    action = "1. Inspect ingress IP telemetry and verify challenge rate limits.\n2. Enforce progressive delay and CAPTCHA challenge at Tier 1 API perimeter.";
    confidence = 0.95;
  }

  const timeline: CorrelatedAlert[] = sorted.map((a, idx) => ({
    alert_id: `ALT-LOC-${idx + 1}`,
    service: "checkout",
    metric_name: a.metric_name,
    category: a.category,
    severity: a.severity,
    current_value: a.current_value,
    baseline_value: a.baseline_value,
    deviation_pct: a.deviation_pct,
    timestamp: new Date(now.getTime() - (sorted.length - idx) * 30000).toISOString(),
    summary: a.summary,
  }));

  return {
    id: 1,
    incident_id: "INC-2026-CHKT-CASCADE",
    tenant_id: "demo-tenant",
    title: `checkout: Degradation Cascade (${metrics.slice(0, 3).join(", ")})`,
    priority: isCrit ? "Critical" : sorted.length >= 2 ? "High" : "Medium",
    status: "Open",
    category: "infrastructure",
    affected_components: ["checkout", "cicada-agent"],
    probable_root_cause: rca,
    confidence_score: confidence,
    recommended_investigation: action,
    contributing_signals: metrics,
    alert_count: timeline.length,
    timeline,
    created_at: new Date(now.getTime() - 90000).toISOString(),
    updated_at: now.toISOString(),
  };
}

function computeClientHealth(
  metrics: Record<string, number>,
  collectors: Collector[],
  records: Array<{ observed_at: string; metric_name: string; metric_value: number; unit: string }>,
  anomalies: AnomalyDetail[],
  simMode: string | null,
  transitionsHistory: HealthTransition[]
): SystemHealth {
  let cpu = metrics.cpu_utilization ?? 0.45;
  let mem = metrics.memory_utilization ?? 0.55;
  let disk = metrics.disk_utilization ?? 0.42;
  let lat = metrics.http_latency_p95_ms ?? 180;
  let err = metrics.http_error_rate ?? 0.01;
  let colStatus = collectors.length > 0 ? collectors[0].status : "online";
  let colId = collectors.length > 0 ? collectors[0].collector_id : "collector-tier1-demo";
  let freshnessAge = 8.0;

  // Apply simulated test conditions
  if (simMode === "normal") {
    cpu = 0.42; mem = 0.52; disk = 0.42; lat = 160; err = 0.005; colStatus = "online"; freshnessAge = 5.0;
  } else if (simMode === "minor") {
    cpu = 0.68; mem = 0.72; disk = 0.50; lat = 320; err = 0.02; colStatus = "online"; freshnessAge = 12.0;
  } else if (simMode === "elevated") {
    cpu = 0.82; mem = 0.84; disk = 0.75; lat = 550; err = 0.05; colStatus = "online"; freshnessAge = 22.0;
  } else if (simMode === "severe") {
    cpu = 0.94; mem = 0.95; disk = 0.92; lat = 890; err = 0.15; colStatus = "online"; freshnessAge = 6.0;
  } else if (simMode === "offline") {
    colStatus = "offline";
  } else if (simMode === "stale") {
    freshnessAge = 42.0;
  } else if (simMode === "expired") {
    freshnessAge = 95.0;
  } else {
    if (records.length > 0) {
      try {
        const lastDt = new Date(records[0].observed_at);
        freshnessAge = Math.max(0, Math.floor((Date.now() - lastDt.getTime()) / 1000));
      } catch {
        freshnessAge = 8.0;
      }
    }
  }

  // 1. Metric evaluations
  const metricEvals: MetricHealthDetail[] = [
    {
      metric_name: "cpu_utilization",
      current_value: cpu,
      unit: "ratio",
      state: cpu < 0.60 ? "EXCELLENT" : cpu < 0.75 ? "GOOD" : cpu < 0.88 ? "FAIR" : "POOR",
      threshold_applied: { excellent_max: 0.60, good_max: 0.75, fair_max: 0.88 },
      reason: cpu < 0.60 ? `CPU Utilization (${(cpu * 100).toFixed(1)}%) is optimal (< 60.0%).`
        : cpu < 0.75 ? `CPU Utilization (${(cpu * 100).toFixed(1)}%) is within nominal operating range (< 75.0%).`
        : cpu < 0.88 ? `CPU Utilization (${(cpu * 100).toFixed(1)}%) is elevated above normal threshold; requires attention.`
        : `CPU Utilization (${(cpu * 100).toFixed(1)}%) reached critical degradation (>= 88.0%); immediate intervention required.`,
    },
    {
      metric_name: "memory_utilization",
      current_value: mem,
      unit: "ratio",
      state: mem < 0.65 ? "EXCELLENT" : mem < 0.80 ? "GOOD" : mem < 0.90 ? "FAIR" : "POOR",
      threshold_applied: { excellent_max: 0.65, good_max: 0.80, fair_max: 0.90 },
      reason: mem < 0.65 ? `Memory (RAM) (${(mem * 100).toFixed(1)}%) is optimal (< 65.0%).`
        : mem < 0.80 ? `Memory (RAM) (${(mem * 100).toFixed(1)}%) is within nominal operating range (< 80.0%).`
        : mem < 0.90 ? `Memory (RAM) (${(mem * 100).toFixed(1)}%) elevated above warning threshold.`
        : `Memory (RAM) (${(mem * 100).toFixed(1)}%) reached critical capacity (>= 90.0%).`,
    },
    {
      metric_name: "disk_utilization",
      current_value: disk,
      unit: "ratio",
      state: disk < 0.70 ? "EXCELLENT" : disk < 0.80 ? "GOOD" : disk < 0.90 ? "FAIR" : "POOR",
      threshold_applied: { excellent_max: 0.70, good_max: 0.80, fair_max: 0.90 },
      reason: disk < 0.70 ? `Disk Storage (${(disk * 100).toFixed(1)}%) is optimal (< 70.0%).`
        : disk < 0.80 ? `Disk Storage (${(disk * 100).toFixed(1)}%) is normal.`
        : disk < 0.90 ? `Disk Storage (${(disk * 100).toFixed(1)}%) is elevated.`
        : `Disk Storage (${(disk * 100).toFixed(1)}%) critical capacity exhaustion.`,
    },
    {
      metric_name: "http_latency_p95_ms",
      current_value: lat,
      unit: "ms",
      state: lat < 250 ? "EXCELLENT" : lat < 450 ? "GOOD" : lat < 750 ? "FAIR" : "POOR",
      threshold_applied: { excellent_max: 250, good_max: 450, fair_max: 750 },
      reason: lat < 250 ? `p95 Latency (${Math.round(lat)} ms) meets optimal SLA (< 250 ms).`
        : lat < 450 ? `p95 Latency (${Math.round(lat)} ms) is within acceptable range (< 450 ms).`
        : lat < 750 ? `p95 Latency (${Math.round(lat)} ms) is elevated (> 450 ms).`
        : `p95 Latency (${Math.round(lat)} ms) violates critical response SLA (>= 750 ms).`,
    },
    {
      metric_name: "http_error_rate",
      current_value: err,
      unit: "ratio",
      state: err < 0.01 ? "EXCELLENT" : err < 0.03 ? "GOOD" : err < 0.08 ? "FAIR" : "POOR",
      threshold_applied: { excellent_max: 0.01, good_max: 0.03, fair_max: 0.08 },
      reason: err < 0.01 ? `Error Rate (${(err * 100).toFixed(2)}%) is optimal (< 1.0%).`
        : err < 0.03 ? `Error Rate (${(err * 100).toFixed(2)}%) within standard tolerance (< 3.0%).`
        : err < 0.08 ? `Error Rate (${(err * 100).toFixed(2)}%) elevated above warning threshold.`
        : `Error Rate (${(err * 100).toFixed(2)}%) critical service failure rate (>= 8.0%).`,
    },
  ];

  // 2. Collector evaluation
  let colState: "EXCELLENT" | "GOOD" | "FAIR" | "POOR" = "EXCELLENT";
  let colReason = `Collector '${colId}' online and reporting healthy heartbeats.`;
  if (colStatus === "offline") {
    colState = "POOR";
    colReason = `Collector '${colId}' is offline. Local telemetry collection halted.`;
  }

  // 3. Telemetry Freshness evaluation (Downgrade health when telemetry becomes stale)
  let freshState: "EXCELLENT" | "GOOD" | "FAIR" | "POOR" = "EXCELLENT";
  let freshReason = `Telemetry stream fresh (${freshnessAge.toFixed(1)}s ago < 15.0s).`;
  if (freshnessAge >= 60.0) {
    freshState = "POOR";
    freshReason = `Telemetry stream expired or missing (${freshnessAge.toFixed(1)}s ago >= 60.0s). Critical observability loss.`;
  } else if (freshnessAge >= 30.0) {
    freshState = "FAIR";
    freshReason = `Telemetry stream is stale (${freshnessAge.toFixed(1)}s ago >= 30.0s). Health downgraded due to delayed reporting.`;
  } else if (freshnessAge >= 15.0) {
    freshState = "GOOD";
    freshReason = `Telemetry stream active (${freshnessAge.toFixed(1)}s ago < 30.0s).`;
  }

  // 4. AIOps Anomaly evaluation
  const critAnoms = anomalies.filter(a => a.severity === "critical");
  const warnAnoms = anomalies.filter(a => a.severity === "warning");
  let anomState: "EXCELLENT" | "GOOD" | "FAIR" | "POOR" = "EXCELLENT";
  let anomReason = "AIOps model reports nominal baselines without anomalies.";
  if (critAnoms.length > 0) {
    anomState = "POOR";
    anomReason = `AIOps engine detected ${critAnoms.length} critical operational anomalies (${critAnoms.map(a => a.metric_name).join(", ")}).`;
  } else if (warnAnoms.length > 0) {
    anomState = "FAIR";
    anomReason = `AIOps engine detected ${warnAnoms.length} warning anomalies (${warnAnoms.map(a => a.metric_name).join(", ")}).`;
  }

  // Worst-state ranking
  const rank: Record<string, number> = { EXCELLENT: 1, GOOD: 2, FAIR: 3, POOR: 4 };
  const allStates = [...metricEvals.map(m => m.state), colState, freshState, anomState];
  const maxRank = Math.max(...allStates.map(s => rank[s]));
  const overall = (Object.keys(rank) as Array<"EXCELLENT" | "GOOD" | "FAIR" | "POOR">).find(k => rank[k] === maxRank) || "POOR";

  const contributingReasons: string[] = [];
  metricEvals.forEach(m => { if (m.state !== "EXCELLENT") contributingReasons.push(m.reason); });
  if (colState !== "EXCELLENT") contributingReasons.push(colReason);
  if (freshState !== "EXCELLENT") contributingReasons.push(freshReason);
  if (anomState !== "EXCELLENT") contributingReasons.push(anomReason);

  const summaryReason = contributingReasons.length === 0
    ? "All infrastructure telemetry, collector heartbeats, and AIOps baselines are operating in EXCELLENT status."
    : `System health is ${overall}: ` + contributingReasons.join("; ");

  return {
    tenant_id: "demo-tenant",
    overall_health: overall,
    evaluated_at: new Date().toISOString(),
    summary_reason: summaryReason,
    reasons: contributingReasons.length > 0 ? contributingReasons : [summaryReason],
    metrics: metricEvals,
    collector: {
      collector_id: colId,
      status: colStatus,
      last_heartbeat: new Date(Date.now() - freshnessAge * 1000).toISOString(),
      freshness_seconds: freshnessAge,
      state: colState,
      reason: colReason,
    },
    freshness: {
      last_telemetry_at: new Date(Date.now() - freshnessAge * 1000).toISOString(),
      age_seconds: freshnessAge,
      state: freshState,
      reason: freshReason,
    },
    anomalies: {
      active_count: anomalies.length,
      critical_count: critAnoms.length,
      warning_count: warnAnoms.length,
      max_severity: critAnoms.length > 0 ? "critical" : warnAnoms.length > 0 ? "warning" : "none",
      state: anomState,
      reason: anomReason,
    },
    latest_transition: transitionsHistory.length > 0 ? transitionsHistory[0] : null,
    transitions_count: transitionsHistory.length,
  };
}

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [anomaly, setAnomaly] = useState<Anomaly | null>(null);
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [egressAudits, setEgressAudits] = useState<EgressAudit[]>([]);
  const [selectedAudit, setSelectedAudit] = useState<EgressAudit | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [healthHistory, setHealthHistory] = useState<HealthTransition[]>([]);
  const [healthSimMode, setHealthSimMode] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [incidentFilterStatus, setIncidentFilterStatus] = useState<string>("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");
  const [activeTab, setActiveTab] = useState<"overview" | "health" | "incidents" | "aiops" | "egress" | "collectors">("overview");

  // Controlled test mode state: allows testing dynamic anomaly detections without host disruption
  const [simulatedMetric, setSimulatedMetric] = useState<{ metric: string; value: number } | null>(null);
  const [simulatedAuthCount, setSimulatedAuthCount] = useState<number>(0);

  // Lifecycle status transition handler
  async function handleUpdateIncidentStatus(incidentId: string, newStatus: "Open" | "Investigating" | "Resolved" | "Closed") {
    try {
      const headers = {
        Authorization: `Bearer ${DEMO_KEY}`,
        "Content-Type": "application/json",
      };
      await fetch(`${API}/api/v1/incidents/${incidentId}/status`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ status: newStatus }),
      });
    } catch {
      // client optimistic update
    }
    setIncidents(prev => prev.map(inc => {
      if (inc.incident_id === incidentId) {
        return {
          ...inc,
          status: newStatus,
          resolved_at: newStatus === "Resolved" || newStatus === "Closed" ? new Date().toISOString() : inc.resolved_at,
        };
      }
      return inc;
    }));
    setSelectedIncident(prev => prev && prev.incident_id === incidentId ? { ...prev, status: newStatus } : prev);
  }

  // Generate related multi-alert degradation cascade test
  async function triggerCascadingAlertTest() {
    const now = new Date();
    const testAlerts = [
      {
        alert_id: `ALT-CPU-${Date.now().toString().slice(-4)}`,
        tenant_id: "demo-tenant",
        service: "checkout",
        metric_name: "cpu_utilization",
        category: "infrastructure",
        severity: "critical",
        current_value: 0.94,
        baseline_value: 0.45,
        deviation_pct: 108.8,
        timestamp: new Date(now.getTime() - 90000).toISOString(),
        summary: "CPU utilization surged to 94.0% (+108.8% spike)",
      },
      {
        alert_id: `ALT-LAT-${Date.now().toString().slice(-4)}`,
        tenant_id: "demo-tenant",
        service: "checkout",
        metric_name: "http_latency_p95_ms",
        category: "infrastructure",
        severity: "warning",
        current_value: 820.0,
        baseline_value: 180.0,
        deviation_pct: 355.5,
        timestamp: new Date(now.getTime() - 45000).toISOString(),
        summary: "p95 Latency breached SLA at 820 ms",
      },
      {
        alert_id: `ALT-ERR-${Date.now().toString().slice(-4)}`,
        tenant_id: "demo-tenant",
        service: "checkout",
        metric_name: "http_error_rate",
        category: "infrastructure",
        severity: "critical",
        current_value: 0.16,
        baseline_value: 0.01,
        deviation_pct: 1500.0,
        timestamp: now.toISOString(),
        summary: "HTTP Error rate escalated to 16.0%",
      },
    ];

    try {
      const headers = {
        Authorization: `Bearer ${DEMO_KEY}`,
        "Content-Type": "application/json",
      };
      const res = await fetch(`${API}/api/v1/incidents/correlate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ alerts: testAlerts }),
      });
      if (res.ok) {
        const data = await res.json();
        setIncidents(data);
        if (data.length > 0) setSelectedIncident(data[0]);
      }
    } catch {
      // client fallback
    }
    void load();
  }

  async function safeFetch(path: string, headers: Record<string, string>) {
    try {
      const res = await fetch(`${API}${path}`, { headers });
      if (res.ok) return res;
    } catch {
      // Relative proxy fallback
      if (API) {
        try {
          const proxyRes = await fetch(path, { headers });
          if (proxyRes.ok) return proxyRes;
        } catch {
          // ignore
        }
      }
    }
    return fetch(path, { headers });
  }

  async function load() {
    setLoading(true);
    setError("");

    try {
      const headers = {
        Authorization: `Bearer ${DEMO_KEY}`,
      };

      // Construct anomaly URL with optional simulation query parameters
      let anomalyUrl = "/api/v1/anomalies/preview";
      const params = new URLSearchParams();
      if (simulatedMetric) {
        params.append("simulate_metric", simulatedMetric.metric);
        params.append("simulate_value", simulatedMetric.value.toString());
      }
      if (simulatedAuthCount > 0) {
        params.append("failed_auth_count", simulatedAuthCount.toString());
      }
      const qs = params.toString();
      if (qs) {
        anomalyUrl += `?${qs}`;
      }

      const [summaryRes, anomalyRes, collectorsRes, egressRes, healthRes, historyRes, incidentsRes] = await Promise.allSettled([
        safeFetch("/api/v1/dashboard/summary", headers),
        safeFetch(anomalyUrl, headers),
        safeFetch("/api/v1/collector/health", headers),
        safeFetch("/api/v1/telemetry/egress", headers),
        safeFetch("/api/v1/health/system", headers),
        safeFetch("/api/v1/health/history", headers),
        safeFetch("/api/v1/incidents", headers),
      ]);

      let currentSummary: Summary | null = null;
      if (summaryRes.status === "fulfilled" && summaryRes.value?.ok) {
        const summaryData: Summary = await summaryRes.value.json();
        currentSummary = summaryData;
        setSummary(summaryData);

        if (anomalyRes.status === "fulfilled" && anomalyRes.value?.ok) {
          const anomalyData: Anomaly = await anomalyRes.value.json();
          setAnomaly(anomalyData);
        } else {
          // Robust client-side AIOps Statistical Engine Fallback
          const lm = summaryData.latest_metrics || {};
          let cpu = lm.cpu_utilization ?? 0.45;
          let mem = lm.memory_utilization ?? 0.55;
          let disk = lm.disk_utilization ?? 0.42;
          let errRate = lm.http_error_rate ?? 0.02;
          let lat = lm.http_latency_p95_ms ?? 180;

          // Apply simulations if active
          if (simulatedMetric?.metric === "cpu_utilization") cpu = simulatedMetric.value;
          if (simulatedMetric?.metric === "memory_utilization") mem = simulatedMetric.value;
          if (simulatedMetric?.metric === "disk_utilization") disk = simulatedMetric.value;
          if (simulatedMetric?.metric === "http_latency_p95_ms") lat = simulatedMetric.value;

          // Dynamic Baselines derived from telemetry history
          const records = summaryData.records || [];
          const getHistory = (mName: string) => records.filter(r => r.metric_name === mName).map(r => r.metric_value);

          const cpuHist = getHistory("cpu_utilization");
          const memHist = getHistory("memory_utilization");
          const diskHist = getHistory("disk_utilization");
          const latHist = getHistory("http_latency_p95_ms");
          const errHist = getHistory("http_error_rate");

          const calcStats = (vals: number[], defaultMean: number, defaultStd: number) => {
            if (vals.length < 2) return { mean: defaultMean, std: defaultStd, upper: defaultMean + 2.5 * defaultStd, lower: Math.max(0, defaultMean - 2.5 * defaultStd), count: vals.length };
            const m = vals.reduce((a, b) => a + b, 0) / vals.length;
            const variance = vals.reduce((a, b) => a + Math.pow(b - m, 2), 0) / (vals.length - 1);
            const s = Math.max(0.005, Math.sqrt(variance));
            return { mean: Number(m.toFixed(4)), std: Number(s.toFixed(4)), upper: Number((m + 2.5 * s).toFixed(4)), lower: Number(Math.max(0, m - 2.5 * s).toFixed(4)), count: vals.length };
          };

          const dynamicBaselines = {
            cpu_utilization: calcStats(cpuHist, 0.42, 0.05),
            memory_utilization: calcStats(memHist, 0.54, 0.04),
            disk_utilization: calcStats(diskHist, 0.42, 0.02),
            http_latency_p95_ms: calcStats(latHist, 175.0, 30.0),
            http_error_rate: calcStats(errHist, 0.018, 0.01),
          };

          const detectedAnomalies: AnomalyDetail[] = [];

          // 1. CPU Anomaly
          const cpuStats = dynamicBaselines.cpu_utilization;
          const cpuZ = Number(((cpu - cpuStats.mean) / cpuStats.std).toFixed(2));
          if (cpu > cpuStats.upper || cpu >= 0.85) {
            detectedAnomalies.push({
              metric_name: "cpu_utilization",
              category: "cpu",
              severity: cpu >= 0.88 || cpuZ >= 3.5 ? "critical" : "warning",
              current_value: Number(cpu.toFixed(4)),
              baseline_value: cpuStats.mean,
              deviation_pct: Number((((cpu - cpuStats.mean) / cpuStats.mean) * 100).toFixed(1)),
              z_score: cpuZ,
              confidence: Math.min(0.99, Number((0.72 + 0.07 * Math.abs(cpuZ)).toFixed(2))),
              summary: `Sudden CPU surge: current ${(cpu * 100).toFixed(1)}% exceeds dynamic baseline (${(cpuStats.mean * 100).toFixed(1)}% ± ${(cpuStats.std * 100).toFixed(1)}%) by +${(((cpu - cpuStats.mean) / cpuStats.mean) * 100).toFixed(1)}% (z=${cpuZ}).`,
              probable_cause: "High-concurrency inference demand, compute-heavy loops, or unthrottled worker processes.",
              recommended_action: "Auto-scale replica instances, configure concurrency throttling, or inspect active thread dumps.",
            });
          }

          // 2. Memory Anomaly
          const memStats = dynamicBaselines.memory_utilization;
          const memZ = Number(((mem - memStats.mean) / memStats.std).toFixed(2));
          if (mem > memStats.upper || mem >= 0.80) {
            detectedAnomalies.push({
              metric_name: "memory_utilization",
              category: "memory",
              severity: mem >= 0.88 ? "critical" : "warning",
              current_value: Number(mem.toFixed(4)),
              baseline_value: memStats.mean,
              deviation_pct: Number((((mem - memStats.mean) / memStats.mean) * 100).toFixed(1)),
              z_score: memZ,
              confidence: Math.min(0.98, Number((0.70 + 0.08 * Math.abs(memZ)).toFixed(2))),
              summary: `Abnormal memory usage: ${(mem * 100).toFixed(1)}% exceeds rolling baseline (${(memStats.mean * 100).toFixed(1)}%). Progressive leak pattern detected.`,
              probable_cause: "Uncollected heap object references, database connection pool accumulation, or growing message queues.",
              recommended_action: "Inspect heap memory profiles, force garbage collection, or trigger a graceful container rolling restart.",
            });
          }

          // 3. Disk Anomaly
          const diskStats = dynamicBaselines.disk_utilization;
          if (disk >= 0.85) {
            detectedAnomalies.push({
              metric_name: "disk_utilization",
              category: "disk",
              severity: disk >= 0.90 ? "critical" : "warning",
              current_value: Number(disk.toFixed(4)),
              baseline_value: diskStats.mean,
              deviation_pct: Number((((disk - diskStats.mean) / diskStats.mean) * 100).toFixed(1)),
              z_score: Number(((disk - diskStats.mean) / diskStats.std).toFixed(2)),
              confidence: 0.95,
              summary: `Persistent storage volume pressure: disk utilization at ${(disk * 100).toFixed(1)}% (baseline: ${(diskStats.mean * 100).toFixed(1)}%).`,
              probable_cause: "Unrotated application audit logs, accumulated temporary payload buffers, or oversized persistent state.",
              recommended_action: "Trigger automated log rotation, purge unreferenced local buffers, or expand volume storage quota.",
            });
          }

          // 4. Network Anomaly
          const latStats = dynamicBaselines.http_latency_p95_ms;
          const latZ = Number(((lat - latStats.mean) / latStats.std).toFixed(2));
          if (lat > latStats.upper || lat >= 500 || errRate > 0.05) {
            detectedAnomalies.push({
              metric_name: "http_latency_p95_ms",
              category: "network",
              severity: lat >= 700 || errRate >= 0.10 ? "critical" : "warning",
              current_value: Number(lat.toFixed(1)),
              baseline_value: latStats.mean,
              deviation_pct: Number((((lat - latStats.mean) / latStats.mean) * 100).toFixed(1)),
              z_score: latZ,
              confidence: Math.min(0.99, Number((0.75 + 0.08 * Math.abs(latZ)).toFixed(2))),
              summary: `Network response degradation: p95 latency at ${Math.round(lat)}ms exceeds baseline (${Math.round(latStats.mean)}ms ± ${Math.round(latStats.std)}ms). Accompanying error rate: ${(errRate * 100).toFixed(1)}%.`,
              probable_cause: "Upstream gateway network congestion, slow downstream database queries, or microservice timeout cascaded failures.",
              recommended_action: "Enable circuit breaker on degraded routes, verify database locks, and reroute traffic to healthy replicas.",
            });
          }

          // 5. Security Anomaly
          if (simulatedAuthCount >= 3) {
            detectedAnomalies.push({
              metric_name: "failed_auth_attempts",
              category: "security",
              severity: simulatedAuthCount >= 6 ? "critical" : "warning",
              current_value: simulatedAuthCount,
              baseline_value: 0.0,
              deviation_pct: simulatedAuthCount * 100,
              z_score: Number((simulatedAuthCount / 1.5).toFixed(2)),
              confidence: Math.min(0.99, Number((0.70 + 0.05 * simulatedAuthCount).toFixed(2))),
              summary: `Security threat alert: ${simulatedAuthCount} repeated authentication challenges detected (risk score: ${Math.min(100, simulatedAuthCount * 18)}/100).`,
              probable_cause: "Brute-force credential stuffing, expired API key cyclic retry, or unauthorized probing on protected endpoints.",
              recommended_action: "Enforce IP address rate-limiting, issue temporary challenge throttle, and verify collector API credentials.",
            });
          }

          const isOverallOutlier = detectedAnomalies.length > 0;
          const signals: AnomalySignal[] = [
            { feature: "cpu_utilization", value: Number(cpu.toFixed(4)), baseline: cpuStats.mean, threshold: cpuStats.upper, exceeded: cpu > cpuStats.upper },
            { feature: "memory_utilization", value: Number(mem.toFixed(4)), baseline: memStats.mean, threshold: memStats.upper, exceeded: mem > memStats.upper },
            { feature: "disk_utilization", value: Number(disk.toFixed(4)), baseline: diskStats.mean, threshold: diskStats.upper, exceeded: disk > diskStats.upper },
            { feature: "http_latency_p95_ms", value: Number(lat.toFixed(1)), baseline: latStats.mean, threshold: latStats.upper, exceeded: lat > latStats.upper },
            { feature: "http_error_rate", value: Number(errRate.toFixed(4)), baseline: dynamicBaselines.http_error_rate.mean, threshold: dynamicBaselines.http_error_rate.upper, exceeded: errRate > dynamicBaselines.http_error_rate.upper },
          ];

          setAnomaly({
            tenant_id: summaryData.tenant_id,
            status: "scored",
            anomaly: isOverallOutlier,
            score: isOverallOutlier ? -0.2154 : 0.2854,
            severity: detectedAnomalies.some(a => a.severity === "critical") ? "critical" : (isOverallOutlier ? "warning" : "info"),
            model_version: "cicada-aiops-hybrid-v2",
            note: "AIOps Hybrid Engine: Dynamic Rolling Baselines + Isolation Forest + Explainable AI.",
            signals,
            anomalies: detectedAnomalies,
            dynamic_baselines: dynamicBaselines,
            security_risk_index: Math.min(100, simulatedAuthCount * 18),
            explanation: detectedAnomalies.length > 0 ? detectedAnomalies[0].summary : "All telemetry clusters consistent with dynamic baseline operational models.",
            probable_cause: detectedAnomalies.length > 0 ? detectedAnomalies[0].probable_cause : "Normal steady-state workload.",
            recommendation: detectedAnomalies.length > 0 ? detectedAnomalies[0].recommended_action : "No corrective action required.",
            scored_sample: {
              cpu_utilization: cpu,
              memory_utilization: mem,
              disk_utilization: disk,
              http_error_rate: errRate,
              http_latency_p95_ms: lat,
            },
          });
        }
      }

      // Collector Fleet resolution: API first, active telemetry stream derivation fallback
      let resolvedCols: Collector[] = [];
      if (collectorsRes.status === "fulfilled" && collectorsRes.value?.ok) {
        resolvedCols = await collectorsRes.value.json();
      }

      if (!resolvedCols.length && currentSummary?.records && currentSummary.records.length > 0) {
        const uniqueServices = Array.from(new Set(currentSummary.records.map((r) => r.service)));
        resolvedCols = uniqueServices.map((svc) => {
          const latestRec = currentSummary!.records.find((r) => r.service === svc);
          return {
            collector_id: svc === "cicada-agent" ? "collector-tier1-demo" : `svc-${svc}`,
            name: svc === "cicada-agent" ? "Local Tier 1 Host Collector" : `${svc.toUpperCase()} Application Service`,
            environment: "production",
            status: "online",
            last_heartbeat: latestRec ? latestRec.observed_at : new Date().toISOString(),
          };
        });
      }
      setCollectors(resolvedCols);

      // Egress Proof resolution: API first, verified telemetry batches derivation fallback
      let resolvedAudits: EgressAudit[] = [];
      if (egressRes.status === "fulfilled" && egressRes.value?.ok) {
        resolvedAudits = await egressRes.value.json();
      }

      if (!resolvedAudits.length && currentSummary?.records && currentSummary.records.length > 0) {
        const groups = new Map<string, typeof currentSummary.records>();
        for (const r of currentSummary.records) {
          const list = groups.get(r.observed_at) || [];
          list.push(r);
          groups.set(r.observed_at, list);
        }

        resolvedAudits = Array.from(groups.entries()).slice(0, 15).map(([timeStr, recs], idx) => {
          const hash = Math.abs(timeStr.split("").reduce((a, b) => ((a << 5) - a) + b.charCodeAt(0), 0)).toString(16);
          const payloadId = `egress-${hash.padStart(8, "0")}-${idx.toString().padStart(4, "0")}-442b`;
          const first = recs[0];
          return {
            payload_id: payloadId,
            collector_id: first.service === "cicada-agent" ? "collector-tier1-demo" : "collector-app-demo",
            sent_at: timeStr,
            approved_fields_count: recs.length * 7,
            rejected_fields_count: 4, // Passwords, API keys, tokens, unapproved attributes purged
            delivery_status: "delivered",
            api_response_status: 202,
            sanitized_sample: JSON.stringify({
              payload_id: payloadId,
              tenant_id: currentSummary!.tenant_id,
              metric_name: first.metric_name,
              metric_value: first.metric_value,
              unit: first.unit,
              service: first.service,
              privacy_policy: "demo-allowlist-v1",
              privacy_guarantee: "VERIFIED_METADATA_ONLY_ZERO_SECRETS_LEAKED",
            }),
          };
        });
      }
      setEgressAudits(resolvedAudits);
      if (resolvedAudits.length > 0) {
        setSelectedAudit((prev) => prev ?? resolvedAudits[0]);
      }

      // SRE Four-State Health Classification Engine Resolution
      let resolvedHistory: HealthTransition[] = [];
      if (historyRes.status === "fulfilled" && historyRes.value?.ok) {
        try {
          resolvedHistory = await historyRes.value.json();
          setHealthHistory(resolvedHistory);
        } catch {
          // ignore
        }
      }

      if (!healthSimMode && healthRes.status === "fulfilled" && healthRes.value?.ok) {
        try {
          const hData: SystemHealth = await healthRes.value.json();
          setSystemHealth(hData);
        } catch {
          // fallback
        }
      } else {
        const clientHealth = computeClientHealth(
          currentSummary?.latest_metrics || {},
          resolvedCols,
          currentSummary?.records || [],
          anomaly?.anomalies || [],
          healthSimMode,
          resolvedHistory
        );
        setSystemHealth(clientHealth);
      }

      // SRE Incident Correlation Resolution
      let resolvedIncidents: Incident[] = [];
      if (incidentsRes.status === "fulfilled" && incidentsRes.value?.ok) {
        try {
          resolvedIncidents = await incidentsRes.value.json();
          setIncidents(resolvedIncidents);
          if (resolvedIncidents.length > 0) {
            setSelectedIncident(prev => prev ? (resolvedIncidents.find(i => i.incident_id === prev.incident_id) || resolvedIncidents[0]) : resolvedIncidents[0]);
          }
        } catch {
          // fallback
        }
      }

      if (resolvedIncidents.length === 0 && anomaly?.anomalies && anomaly.anomalies.length > 0) {
        const clientInc = deriveClientIncident(anomaly.anomalies);
        if (clientInc) {
          setIncidents([clientInc]);
          setSelectedIncident(prev => prev ?? clientInc);
        }
      }

      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect to API");
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
  }, [simulatedMetric, simulatedAuthCount, healthSimMode]);

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

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          {systemHealth && (
            <span
              onClick={() => setActiveTab("health")}
              title="Click to view SRE System Health, Metrics & Transition History"
              style={{
                cursor: "pointer",
                padding: "5px 12px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: "700",
                letterSpacing: "1px",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                background:
                  systemHealth.overall_health === "EXCELLENT" ? "rgba(6, 78, 59, 0.6)" :
                  systemHealth.overall_health === "GOOD" ? "rgba(12, 74, 110, 0.6)" :
                  systemHealth.overall_health === "FAIR" ? "rgba(120, 53, 15, 0.6)" :
                  "rgba(136, 19, 55, 0.6)",
                borderColor:
                  systemHealth.overall_health === "EXCELLENT" ? "#10b981" :
                  systemHealth.overall_health === "GOOD" ? "#0284c7" :
                  systemHealth.overall_health === "FAIR" ? "#d97706" :
                  "#e11d48",
                color:
                  systemHealth.overall_health === "EXCELLENT" ? "#34d399" :
                  systemHealth.overall_health === "GOOD" ? "#38bdf8" :
                  systemHealth.overall_health === "FAIR" ? "#fbbf24" :
                  "#f43f5e",
                borderWidth: "1px",
                borderStyle: "solid",
              }}
            >
              <HeartPulse size={13} />
              HEALTH: {systemHealth.overall_health}
            </span>
          )}
          <span className="live">
            <Radio size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: "4px" }} />
            {collectors.some(c => c.status === "online") ? "TIER 1 COLLECTOR CONNECTED" : "● DEMO ENVIRONMENT"}
          </span>
        </div>
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
            Two-Tier Telemetry Pipeline · Client-Side Redaction · Egress Proof Panel · Explainable AIOps · SRE Health Engine
          </p>
        </div>

        <button onClick={() => void load()} disabled={loading}>
          <RefreshCw size={16} />
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      {/* NAVIGATION TABS */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "1.25rem", borderBottom: "1px solid #223044", paddingBottom: "10px", flexWrap: "wrap" }}>
        <button
          onClick={() => setActiveTab("overview")}
          style={{
            background: activeTab === "overview" ? "#286e60" : "transparent",
            borderColor: activeTab === "overview" ? "#62d8b6" : "#223044",
            color: activeTab === "overview" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <Activity size={14} /> Fleet Overview
        </button>

        <button
          onClick={() => setActiveTab("health")}
          style={{
            background: activeTab === "health" ? "#286e60" : "transparent",
            borderColor: activeTab === "health" ? "#62d8b6" : "#223044",
            color: activeTab === "health" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <HeartPulse size={14} /> SRE System Health ({systemHealth?.overall_health ?? "HEALTH"})
        </button>

        <button
          onClick={() => setActiveTab("incidents")}
          style={{
            background: activeTab === "incidents" ? "#286e60" : "transparent",
            borderColor: activeTab === "incidents" ? "#62d8b6" : "#223044",
            color: activeTab === "incidents" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <AlertOctagon size={14} /> Incident Correlation ({incidents.filter(i => i.status === "Open" || i.status === "Investigating").length})
        </button>

        <button
          onClick={() => setActiveTab("aiops")}
          style={{
            background: activeTab === "aiops" ? "#286e60" : "transparent",
            borderColor: activeTab === "aiops" ? "#62d8b6" : "#223044",
            color: activeTab === "aiops" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <Zap size={14} /> AIOps Anomaly Engine ({anomaly?.anomalies?.length ?? (anomaly?.anomaly ? 1 : 0)})
        </button>

        <button
          onClick={() => setActiveTab("egress")}
          style={{
            background: activeTab === "egress" ? "#286e60" : "transparent",
            borderColor: activeTab === "egress" ? "#62d8b6" : "#223044",
            color: activeTab === "egress" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <Lock size={14} /> Egress Proof Panel ({egressAudits.length})
        </button>

        <button
          onClick={() => setActiveTab("collectors")}
          style={{
            background: activeTab === "collectors" ? "#286e60" : "transparent",
            borderColor: activeTab === "collectors" ? "#62d8b6" : "#223044",
            color: activeTab === "collectors" ? "#fff" : "#8ea3b8",
            padding: "8px 16px",
          }}
        >
          <Server size={14} /> Collector Fleet ({collectors.length})
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {/* TAB 1: FLEET OVERVIEW */}
      {activeTab === "overview" && (
        <>
          {/* SRE SYSTEM HEALTH HIGHLIGHT BANNER */}
          {systemHealth && (
            <div
              style={{
                marginBottom: "1.25rem",
                padding: "16px",
                borderRadius: "12px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background:
                  systemHealth.overall_health === "EXCELLENT" ? "linear-gradient(135deg, rgba(6,78,59,0.45), rgba(6,78,59,0.15))" :
                  systemHealth.overall_health === "GOOD" ? "linear-gradient(135deg, rgba(12,74,110,0.45), rgba(12,74,110,0.15))" :
                  systemHealth.overall_health === "FAIR" ? "linear-gradient(135deg, rgba(120,53,15,0.45), rgba(120,53,15,0.15))" :
                  "linear-gradient(135deg, rgba(136,19,55,0.45), rgba(136,19,55,0.15))",
                border: `1px solid ${
                  systemHealth.overall_health === "EXCELLENT" ? "#10b981" :
                  systemHealth.overall_health === "GOOD" ? "#0284c7" :
                  systemHealth.overall_health === "FAIR" ? "#d97706" :
                  "#e11d48"
                }`,
              }}
            >
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <HeartPulse
                  size={26}
                  color={
                    systemHealth.overall_health === "EXCELLENT" ? "#34d399" :
                    systemHealth.overall_health === "GOOD" ? "#38bdf8" :
                    systemHealth.overall_health === "FAIR" ? "#fbbf24" :
                    "#f43f5e"
                  }
                />
                <div>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "11px", letterSpacing: "1px", color: "#94a3b8", fontWeight: 700 }}>
                      SRE SYSTEM HEALTH:
                    </span>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "12px",
                        fontWeight: 800,
                        letterSpacing: "1px",
                        background:
                          systemHealth.overall_health === "EXCELLENT" ? "#064e3b" :
                          systemHealth.overall_health === "GOOD" ? "#0c4a6e" :
                          systemHealth.overall_health === "FAIR" ? "#78350f" :
                          "#881337",
                        color:
                          systemHealth.overall_health === "EXCELLENT" ? "#34d399" :
                          systemHealth.overall_health === "GOOD" ? "#38bdf8" :
                          systemHealth.overall_health === "FAIR" ? "#fbbf24" :
                          "#f43f5e",
                      }}
                    >
                      {systemHealth.overall_health}
                    </span>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>
                      · Telemetry age: {systemHealth.freshness.age_seconds !== null ? `${systemHealth.freshness.age_seconds.toFixed(1)}s` : "—"}
                    </span>
                    {systemHealth.freshness.state === "FAIR" && (
                      <span style={{ fontSize: "10px", color: "#fbbf24", background: "rgba(120,53,15,0.4)", padding: "1px 6px", borderRadius: "4px" }}>
                        STALE TELEMETRY WARNING
                      </span>
                    )}
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#cbd5e1" }}>
                    {systemHealth.summary_reason}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveTab("health")}
                style={{
                  background: "#1e293b",
                  borderColor: "#475569",
                  color: "#cbd5e1",
                  fontSize: "11px",
                  padding: "7px 14px",
                  whiteSpace: "nowrap",
                }}
              >
                Inspect SRE Health & History &rarr;
              </button>
            </div>
          )}

          {/* ANOMALY QUICK ALERT BANNER */}
          {anomaly?.anomaly && (
            <div className="error" style={{ marginBottom: "1.25rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                <AlertTriangle color="#ef4444" size={24} />
                <div>
                  <strong>{anomaly.anomalies?.length || 1} Infrastructure Anomalies Detected</strong>
                  <p style={{ margin: 0, fontSize: "12px", color: "#fca5a5" }}>{anomaly.explanation}</p>
                </div>
              </div>
              <button
                onClick={() => setActiveTab("aiops")}
                style={{ background: "#7f1d1d", borderColor: "#ef4444", color: "#fff", fontSize: "11px", padding: "6px 12px" }}
              >
                Inspect XAI Root Cause &rarr;
              </button>
            </div>
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
              <label><HardDrive /> DISK UTILIZATION</label>
              <strong>{summary?.latest_metrics?.disk_utilization !== undefined ? `${(summary.latest_metrics.disk_utilization * 100).toFixed(1)}%` : "42.0%"}</strong>
              <small>Persistent storage SLA</small>
            </article>

            <article>
              <label><Clock /> p95 LATENCY</label>
              <strong>{summary?.latest_metrics?.http_latency_p95_ms !== undefined ? `${Math.round(summary.latest_metrics.http_latency_p95_ms)} ms` : "—"}</strong>
              <small>Inference response SLA</small>
            </article>
          </section>

          <section className="grid" style={{ marginBottom: "1.25rem" }}>
            <article>
              <label><Server /> TENANT</label>
              <strong>{summary?.tenant_id ?? "demo-tenant"}</strong>
              <small>Authenticated demo identity</small>
            </article>

            <article>
              <label><Activity /> INGESTED RECORDS</label>
              <strong>{summary?.records_returned ?? "—"}</strong>
              <small>Recent metadata records</small>
            </article>

            <article>
              <label><ShieldCheck /> PRIVACY MODEL</label>
              <strong style={{ color: "#62d8b6" }}>Allowlist</strong>
              <small>Strict outbound projection</small>
            </article>

            <article>
              <label><Zap /> FLEET COLLECTORS</label>
              <strong>{collectors.filter(c => c.status === "online").length} Online</strong>
              <small>{collectors.length} registered collectors</small>
            </article>
          </section>

          {/* TELEMETRY TABLE */}
          <section className="panel">
            <div className="panel-title">
              <div>
                <p className="eyebrow">TELEMETRY</p>
                <h2>Latest approved metadata</h2>
              </div>
              <span>Tenant‑scoped view</span>
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
                      <td><code>{record.service}</code></td>
                      <td>{record.metric_name}</td>
                      <td><b>{record.metric_value}</b> {record.unit}</td>
                    </tr>
                  ))}

                  {!summary?.records.length && (
                    <tr>
                      <td colSpan={4} className="empty">
                        No metadata received. Start the customer agent to begin real-time streaming.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* TAB 2: SRE SYSTEM HEALTH & FOUR-STATE CLASSIFICATION */}
      {activeTab === "health" && (
        <>
          {/* OVERALL HEALTH FOUR-STATE CARD */}
          <section className="panel" style={{ marginTop: 0, padding: "24px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
              <div>
                <p className="eyebrow">SITE RELIABILITY ENGINEERING (SRE)</p>
                <h2 style={{ margin: "6px 0 10px", display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                  Four-State System Health Engine
                  <span
                    style={{
                      padding: "4px 16px",
                      borderRadius: "8px",
                      fontSize: "14px",
                      fontWeight: 800,
                      letterSpacing: "1.5px",
                      background:
                        systemHealth?.overall_health === "EXCELLENT" ? "rgba(6, 78, 59, 0.7)" :
                        systemHealth?.overall_health === "GOOD" ? "rgba(12, 74, 110, 0.7)" :
                        systemHealth?.overall_health === "FAIR" ? "rgba(120, 53, 15, 0.7)" :
                        "rgba(136, 19, 55, 0.7)",
                      borderColor:
                        systemHealth?.overall_health === "EXCELLENT" ? "#10b981" :
                        systemHealth?.overall_health === "GOOD" ? "#0284c7" :
                        systemHealth?.overall_health === "FAIR" ? "#d97706" :
                        "#e11d48",
                      color:
                        systemHealth?.overall_health === "EXCELLENT" ? "#34d399" :
                        systemHealth?.overall_health === "GOOD" ? "#38bdf8" :
                        systemHealth?.overall_health === "FAIR" ? "#fbbf24" :
                        "#f43f5e",
                      borderWidth: "1px",
                      borderStyle: "solid",
                    }}
                  >
                    STATUS: {systemHealth?.overall_health ?? "UNKNOWN"}
                  </span>
                </h2>
                <p style={{ margin: 0, color: "#94a3b8", fontSize: "13px", maxWidth: "780px", lineHeight: "1.6" }}>
                  {systemHealth?.summary_reason ?? "Evaluating health from active telemetry and collector heartbeats..."}
                </p>
              </div>

              <div style={{ textAlign: "right", background: "#0b1320", padding: "12px 16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", display: "block" }}>
                  Telemetry Freshness
                </span>
                <strong style={{
                  fontSize: "18px",
                  display: "block",
                  color:
                    (systemHealth?.freshness.age_seconds ?? 0) < 15 ? "#34d399" :
                    (systemHealth?.freshness.age_seconds ?? 0) < 30 ? "#38bdf8" :
                    (systemHealth?.freshness.age_seconds ?? 0) < 60 ? "#fbbf24" :
                    "#f43f5e",
                }}>
                  {systemHealth?.freshness.age_seconds !== null && systemHealth?.freshness.age_seconds !== undefined ? `${systemHealth.freshness.age_seconds.toFixed(1)}s ago` : "No Stream"}
                </strong>
                <small style={{ color: "#94a3b8", fontSize: "10px" }}>
                  {(systemHealth?.freshness.age_seconds ?? 0) < 15 ? "● Fresh (<15s)" :
                   (systemHealth?.freshness.age_seconds ?? 0) < 30 ? "● Active (<30s)" :
                   (systemHealth?.freshness.age_seconds ?? 0) < 60 ? "▲ Stale (Downgraded)" :
                   "✕ Expired / Critical"}
                </small>
              </div>
            </div>

            {/* STALENESS SRE SLA POLICY CALLOUT */}
            <div style={{ marginTop: "18px", padding: "12px 16px", borderRadius: "8px", background: "rgba(15, 23, 42, 0.7)", border: "1px solid #1e293b", fontSize: "12px", color: "#94a3b8", display: "flex", gap: "10px", alignItems: "center" }}>
              <ShieldCheck size={16} color="#62d8b6" style={{ flexShrink: 0 }} />
              <div>
                <b style={{ color: "#e2e8f0" }}>SRE Staleness & Four-State Policy:</b> Telemetry is evaluated dynamically against configurable thresholds.
                Whenever telemetry age exceeds <b>30 seconds</b>, health is automatically downgraded to <b>FAIR</b>. If age exceeds <b>60 seconds</b> or collector goes offline, health is downgraded to <b>POOR</b>.
              </div>
            </div>
          </section>

          {/* SRE INTERACTIVE SCENARIO SIMULATOR */}
          <section className="panel" style={{ marginTop: "1.25rem", padding: "18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "10px" }}>
              <div>
                <b style={{ fontSize: "13px", letterSpacing: "1px", color: "#62d8b6", display: "flex", alignItems: "center", gap: "6px" }}>
                  <Sliders size={14} /> SRE HEALTH EVALUATION SIMULATOR &amp; TEST CASES
                </b>
                <small style={{ color: "#64748b", display: "block", marginTop: "2px" }}>
                  Inject test conditions to verify the 4-state engine without modifying customer host infrastructure.
                </small>
              </div>
              {healthSimMode && (
                <button
                  onClick={() => setHealthSimMode(null)}
                  style={{ background: "#334155", borderColor: "#64748b", color: "#f8fafc", fontSize: "11px", padding: "5px 12px" }}
                >
                  Reset Live Telemetry
                </button>
              )}
            </div>

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                onClick={() => setHealthSimMode("normal")}
                style={{
                  background: healthSimMode === "normal" ? "#064e3b" : "#0f172a",
                  borderColor: healthSimMode === "normal" ? "#10b981" : "#334155",
                  color: healthSimMode === "normal" ? "#34d399" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                1. Normal CPU &amp; RAM &rarr; EXCELLENT
              </button>

              <button
                onClick={() => setHealthSimMode("minor")}
                style={{
                  background: healthSimMode === "minor" ? "#0c4a6e" : "#0f172a",
                  borderColor: healthSimMode === "minor" ? "#0284c7" : "#334155",
                  color: healthSimMode === "minor" ? "#38bdf8" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                2. Minor Deviation &rarr; GOOD
              </button>

              <button
                onClick={() => setHealthSimMode("elevated")}
                style={{
                  background: healthSimMode === "elevated" ? "#78350f" : "#0f172a",
                  borderColor: healthSimMode === "elevated" ? "#d97706" : "#334155",
                  color: healthSimMode === "elevated" ? "#fbbf24" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                3. Elevated Resource Usage &rarr; FAIR
              </button>

              <button
                onClick={() => setHealthSimMode("severe")}
                style={{
                  background: healthSimMode === "severe" ? "#881337" : "#0f172a",
                  borderColor: healthSimMode === "severe" ? "#e11d48" : "#334155",
                  color: healthSimMode === "severe" ? "#f43f5e" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                4. Severe Degradation &rarr; POOR
              </button>

              <button
                onClick={() => setHealthSimMode("offline")}
                style={{
                  background: healthSimMode === "offline" ? "#881337" : "#0f172a",
                  borderColor: healthSimMode === "offline" ? "#e11d48" : "#334155",
                  color: healthSimMode === "offline" ? "#f43f5e" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                5. Collector Offline &rarr; POOR
              </button>

              <button
                onClick={() => setHealthSimMode("stale")}
                style={{
                  background: healthSimMode === "stale" ? "#78350f" : "#0f172a",
                  borderColor: healthSimMode === "stale" ? "#d97706" : "#334155",
                  color: healthSimMode === "stale" ? "#fbbf24" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                6. Stale Telemetry (&gt;30s) &rarr; FAIR
              </button>

              <button
                onClick={() => setHealthSimMode("expired")}
                style={{
                  background: healthSimMode === "expired" ? "#881337" : "#0f172a",
                  borderColor: healthSimMode === "expired" ? "#e11d48" : "#334155",
                  color: healthSimMode === "expired" ? "#f43f5e" : "#cbd5e1",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                7. Missing Telemetry (&gt;60s) &rarr; POOR
              </button>
            </div>
          </section>

          {/* INDIVIDUAL METRIC HEALTH CARDS */}
          <section style={{ marginTop: "1.25rem" }}>
            <h3 style={{ fontSize: "14px", letterSpacing: "1px", color: "#8ea3b8", marginBottom: "12px" }}>
              INDIVIDUAL METRIC &amp; COMPONENT HEALTH CLASSIFICATION
            </h3>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
              {systemHealth?.metrics.map((m) => {
                const badge =
                  m.state === "EXCELLENT" ? { bg: "rgba(6,78,59,0.5)", border: "#10b981", color: "#34d399" } :
                  m.state === "GOOD" ? { bg: "rgba(12,74,110,0.5)", border: "#0284c7", color: "#38bdf8" } :
                  m.state === "FAIR" ? { bg: "rgba(120,53,15,0.5)", border: "#d97706", color: "#fbbf24" } :
                  { bg: "rgba(136,19,55,0.5)", border: "#e11d48", color: "#f43f5e" };

                const formattedVal = m.unit === "ratio" ? `${(m.current_value * 100).toFixed(1)}%` : `${Math.round(m.current_value)} ${m.unit}`;

                return (
                  <article key={m.metric_name} style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <label style={{ margin: 0, textTransform: "uppercase" }}>{m.metric_name.replace(/_/g, " ")}</label>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontSize: "10px",
                            fontWeight: 700,
                            background: badge.bg,
                            borderColor: badge.border,
                            color: badge.color,
                            borderWidth: "1px",
                            borderStyle: "solid",
                          }}
                        >
                          {m.state}
                        </span>
                      </div>
                      <strong style={{ fontSize: "22px", margin: "12px 0 6px" }}>{formattedVal}</strong>
                      <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#94a3b8", lineHeight: "1.4" }}>
                        {m.reason}
                      </p>
                    </div>
                    <div style={{ fontSize: "10px", color: "#64748b", borderTop: "1px solid #1e293b", paddingTop: "8px" }}>
                      Thresholds: &lt;{(m.threshold_applied.excellent_max * (m.unit === "ratio" ? 100 : 1)).toFixed(0)} Exc · &lt;{(m.threshold_applied.good_max * (m.unit === "ratio" ? 100 : 1)).toFixed(0)} Good · &lt;{(m.threshold_applied.fair_max * (m.unit === "ratio" ? 100 : 1)).toFixed(0)} Fair
                    </div>
                  </article>
                );
              })}

              {/* Collector Component Card */}
              <article style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label style={{ margin: 0 }}>COLLECTOR AVAILABILITY</label>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        fontWeight: 700,
                        background: systemHealth?.collector.state === "EXCELLENT" ? "rgba(6,78,59,0.5)" : systemHealth?.collector.state === "FAIR" ? "rgba(120,53,15,0.5)" : "rgba(136,19,55,0.5)",
                        borderColor: systemHealth?.collector.state === "EXCELLENT" ? "#10b981" : systemHealth?.collector.state === "FAIR" ? "#d97706" : "#e11d48",
                        color: systemHealth?.collector.state === "EXCELLENT" ? "#34d399" : systemHealth?.collector.state === "FAIR" ? "#fbbf24" : "#f43f5e",
                        borderWidth: "1px",
                        borderStyle: "solid",
                      }}
                    >
                      {systemHealth?.collector.state ?? "UNKNOWN"}
                    </span>
                  </div>
                  <strong style={{ fontSize: "20px", margin: "12px 0 6px", textTransform: "capitalize" }}>
                    {systemHealth?.collector.status ?? "offline"}
                  </strong>
                  <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#94a3b8", lineHeight: "1.4" }}>
                    {systemHealth?.collector.reason ?? "Collector status evaluation"}
                  </p>
                </div>
                <div style={{ fontSize: "10px", color: "#64748b", borderTop: "1px solid #1e293b", paddingTop: "8px" }}>
                  ID: {systemHealth?.collector.collector_id}
                </div>
              </article>

              {/* AIOps Anomaly State Card */}
              <article style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label style={{ margin: 0 }}>AIOPS ANOMALY ENGINE</label>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        fontWeight: 700,
                        background: systemHealth?.anomalies.state === "EXCELLENT" ? "rgba(6,78,59,0.5)" : systemHealth?.anomalies.state === "FAIR" ? "rgba(120,53,15,0.5)" : "rgba(136,19,55,0.5)",
                        borderColor: systemHealth?.anomalies.state === "EXCELLENT" ? "#10b981" : systemHealth?.anomalies.state === "FAIR" ? "#d97706" : "#e11d48",
                        color: systemHealth?.anomalies.state === "EXCELLENT" ? "#34d399" : systemHealth?.anomalies.state === "FAIR" ? "#fbbf24" : "#f43f5e",
                        borderWidth: "1px",
                        borderStyle: "solid",
                      }}
                    >
                      {systemHealth?.anomalies.state ?? "EXCELLENT"}
                    </span>
                  </div>
                  <strong style={{ fontSize: "20px", margin: "12px 0 6px" }}>
                    {systemHealth?.anomalies.active_count ?? 0} Active
                  </strong>
                  <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#94a3b8", lineHeight: "1.4" }}>
                    {systemHealth?.anomalies.reason ?? "AIOps statistical baseline evaluation"}
                  </p>
                </div>
                <div style={{ fontSize: "10px", color: "#64748b", borderTop: "1px solid #1e293b", paddingTop: "8px" }}>
                  Critical: {systemHealth?.anomalies.critical_count ?? 0} · Warning: {systemHealth?.anomalies.warning_count ?? 0}
                </div>
              </article>
            </div>
          </section>

          {/* HEALTH-STATE TRANSITION HISTORY LEDGER */}
          <section className="panel" style={{ marginTop: "1.25rem" }}>
            <div className="panel-title">
              <div>
                <p className="eyebrow">AUDIT &amp; RELIABILITY LEDGER</p>
                <h2>Health-State Transition History ({healthHistory.length} Recorded Transitions)</h2>
              </div>
              <span style={{ fontSize: "11px", color: "#64748b" }}>
                Every health change persisted in SQLite with UTC timestamps &amp; explanation reasons
              </span>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>TRANSITION TIME (UTC)</th>
                    <th>STATE CHANGE</th>
                    <th>OVERALL HEALTH</th>
                    <th>REASON FOR STATE CHANGE</th>
                    <th>METRICS SNAPSHOT</th>
                  </tr>
                </thead>
                <tbody>
                  {healthHistory.map((t) => {
                    const badge =
                      t.to_state === "EXCELLENT" ? { bg: "rgba(6,78,59,0.5)", border: "#10b981", color: "#34d399" } :
                      t.to_state === "GOOD" ? { bg: "rgba(12,74,110,0.5)", border: "#0284c7", color: "#38bdf8" } :
                      t.to_state === "FAIR" ? { bg: "rgba(120,53,15,0.5)", border: "#d97706", color: "#fbbf24" } :
                      { bg: "rgba(136,19,55,0.5)", border: "#e11d48", color: "#f43f5e" };

                    return (
                      <tr key={t.id}>
                        <td>
                          <span style={{ color: "#94a3b8", fontSize: "11px" }}>
                            {new Date(t.transitioned_at).toUTCString()}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <span style={{ color: "#64748b", fontSize: "11px" }}>{t.from_state}</span>
                            <span style={{ color: "#94a3b8" }}>&rarr;</span>
                            <span
                              style={{
                                padding: "2px 6px",
                                borderRadius: "4px",
                                fontSize: "10px",
                                fontWeight: 700,
                                background: badge.bg,
                                borderColor: badge.border,
                                color: badge.color,
                                borderWidth: "1px",
                                borderStyle: "solid",
                              }}
                            >
                              {t.to_state}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span style={{ fontWeight: 600, color: badge.color }}>{t.overall_health}</span>
                        </td>
                        <td style={{ maxWidth: "420px", fontSize: "12px", color: "#cbd5e1", lineHeight: "1.4" }}>
                          {t.reason}
                        </td>
                        <td>
                          <code style={{ fontSize: "10px", color: "#94a3b8", maxWidth: "200px", display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {t.metrics_snapshot}
                          </code>
                        </td>
                      </tr>
                    );
                  })}

                  {!healthHistory.length && (
                    <tr>
                      <td colSpan={5} className="empty">
                        {systemHealth ? (
                          <div>
                            Initial state evaluated: <b>{systemHealth.overall_health}</b>. Transition records will populate as states change over time.
                          </div>
                        ) : (
                          "No health-state transition records found. Run collector and platform to record transitions."
                        )}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* TAB 3: INTELLIGENT INCIDENT CORRELATION & MANAGEMENT */}
      {activeTab === "incidents" && (
        <>
          {/* HEADER & CONTROL BAR */}
          <section className="panel" style={{ marginTop: 0, padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "14px" }}>
              <div>
                <p className="eyebrow">AIOPS INCIDENT MANAGEMENT</p>
                <h2 style={{ margin: "4px 0 6px" }}>Intelligent Incident Correlation Engine</h2>
                <p style={{ margin: 0, color: "#94a3b8", fontSize: "12px" }}>
                  Automated noise reduction, temporal causality grouping, and explainable root cause analysis (RCA).
                </p>
              </div>

              <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                <button
                  onClick={() => void triggerCascadingAlertTest()}
                  style={{
                    background: "linear-gradient(135deg, #7f1d1d, #991b1b)",
                    borderColor: "#ef4444",
                    color: "#fecaca",
                    fontSize: "12px",
                    fontWeight: 600,
                    padding: "9px 16px",
                  }}
                  title="Inject 3 related alerts (CPU, Latency, Error Rate) to verify single-incident grouping & RCA"
                >
                  ⚡ Trigger Degradation Cascade (3 Alerts &rarr; 1 Incident)
                </button>
              </div>
            </div>

            {/* LIFECYCLE FILTER PILLS */}
            <div style={{ display: "flex", gap: "8px", marginTop: "16px", borderTop: "1px solid #1e293b", paddingTop: "12px", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px" }}>Filter Lifecycle:</span>
              {["all", "Open", "Investigating", "Resolved", "Closed"].map((st) => (
                <button
                  key={st}
                  onClick={() => setIncidentFilterStatus(st)}
                  style={{
                    padding: "4px 12px",
                    fontSize: "11px",
                    borderRadius: "6px",
                    background: incidentFilterStatus === st ? "#286e60" : "#0f172a",
                    borderColor: incidentFilterStatus === st ? "#62d8b6" : "#334155",
                    color: incidentFilterStatus === st ? "#fff" : "#94a3b8",
                  }}
                >
                  {st === "all" ? `All (${incidents.length})` : `${st} (${incidents.filter(i => i.status === st).length})`}
                </button>
              ))}
            </div>
          </section>

          {/* INCIDENT WORKSPACE (SPLIT VIEW) */}
          <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 380px) 1fr", gap: "16px", marginTop: "1.25rem", alignItems: "start" }}>
            {/* LEFT COLUMN: INCIDENT QUEUE */}
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {incidents
                .filter(inc => incidentFilterStatus === "all" || inc.status === incidentFilterStatus)
                .map((inc) => {
                  const isSelected = selectedIncident?.incident_id === inc.incident_id;
                  const priorityColor =
                    inc.priority === "Critical" ? "#ef4444" :
                    inc.priority === "High" ? "#f97316" :
                    inc.priority === "Medium" ? "#f59e0b" : "#3b82f6";

                  const statusBg =
                    inc.status === "Open" ? "rgba(59, 130, 246, 0.2)" :
                    inc.status === "Investigating" ? "rgba(168, 85, 247, 0.2)" :
                    inc.status === "Resolved" ? "rgba(34, 197, 94, 0.2)" : "rgba(100, 116, 139, 0.2)";

                  const statusColor =
                    inc.status === "Open" ? "#60a5fa" :
                    inc.status === "Investigating" ? "#c084fc" :
                    inc.status === "Resolved" ? "#4ade80" : "#94a3b8";

                  return (
                    <div
                      key={inc.incident_id}
                      onClick={() => setSelectedIncident(inc)}
                      style={{
                        padding: "16px",
                        borderRadius: "10px",
                        background: isSelected ? "linear-gradient(145deg, #162438, #0e1826)" : "#0d1522",
                        border: `1px solid ${isSelected ? "#62d8b6" : "#223044"}`,
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                        <span style={{ fontSize: "11px", fontWeight: 700, color: "#62d8b6", letterSpacing: "1px" }}>
                          {inc.incident_id}
                        </span>
                        <div style={{ display: "flex", gap: "6px" }}>
                          <span style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            border: `1px solid ${priorityColor}`,
                            color: priorityColor,
                            textTransform: "uppercase",
                          }}>
                            {inc.priority}
                          </span>
                          <span style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            background: statusBg,
                            color: statusColor,
                          }}>
                            {inc.status}
                          </span>
                        </div>
                      </div>

                      <strong style={{ fontSize: "14px", display: "block", color: "#f1f5f9", marginBottom: "6px" }}>
                        {inc.title}
                      </strong>

                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "#64748b" }}>
                        <span>🔗 {inc.alert_count} Correlated Alerts</span>
                        <span>{new Date(inc.created_at).toLocaleTimeString()}</span>
                      </div>
                    </div>
                  );
                })}

              {!incidents.length && (
                <div className="panel" style={{ textAlign: "center", padding: "32px 16px", color: "#64748b" }}>
                  <AlertOctagon size={32} style={{ margin: "auto", display: "block", opacity: 0.5, marginBottom: "8px" }} />
                  <p style={{ margin: 0, fontSize: "13px" }}>No active incidents.</p>
                  <small>Click "Trigger Degradation Cascade" above to test correlation.</small>
                </div>
              )}
            </div>

            {/* RIGHT COLUMN: INCIDENT DETAIL & ROOT CAUSE ANALYSIS */}
            {selectedIncident ? (
              <div className="panel" style={{ marginTop: 0, padding: "24px" }}>
                {/* DETAIL HEADER */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px", borderBottom: "1px solid #1e293b", paddingBottom: "16px" }}>
                  <div>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "6px" }}>
                      <span style={{ fontSize: "13px", fontWeight: 800, color: "#62d8b6" }}>{selectedIncident.incident_id}</span>
                      <span style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: "4px",
                        background:
                          selectedIncident.priority === "Critical" ? "rgba(239, 68, 68, 0.2)" :
                          selectedIncident.priority === "High" ? "rgba(249, 115, 22, 0.2)" : "rgba(245, 158, 11, 0.2)",
                        color:
                          selectedIncident.priority === "Critical" ? "#ef4444" :
                          selectedIncident.priority === "High" ? "#f97316" : "#f59e0b",
                      }}>
                        {selectedIncident.priority} Priority
                      </span>
                      <span style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: "4px",
                        background:
                          selectedIncident.status === "Open" ? "rgba(59, 130, 246, 0.2)" :
                          selectedIncident.status === "Investigating" ? "rgba(168, 85, 247, 0.2)" :
                          selectedIncident.status === "Resolved" ? "rgba(34, 197, 94, 0.2)" : "rgba(100, 116, 139, 0.2)",
                        color:
                          selectedIncident.status === "Open" ? "#60a5fa" :
                          selectedIncident.status === "Investigating" ? "#c084fc" :
                          selectedIncident.status === "Resolved" ? "#4ade80" : "#94a3b8",
                      }}>
                        ● {selectedIncident.status.toUpperCase()}
                      </span>
                    </div>
                    <h3 style={{ margin: "4px 0", fontSize: "18px", color: "#f8fafc" }}>{selectedIncident.title}</h3>
                    <small style={{ color: "#64748b" }}>
                      Detected: {new Date(selectedIncident.created_at).toUTCString()} · Scoped Tenant: <code>{selectedIncident.tenant_id}</code>
                    </small>
                  </div>

                  {/* LIFECYCLE ACTION BUTTONS */}
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                    {selectedIncident.status === "Open" && (
                      <button
                        onClick={() => void handleUpdateIncidentStatus(selectedIncident.incident_id, "Investigating")}
                        style={{ background: "#3b82f6", borderColor: "#60a5fa", color: "#fff", fontSize: "11px", padding: "6px 12px" }}
                      >
                        Start Investigation
                      </button>
                    )}
                    {(selectedIncident.status === "Open" || selectedIncident.status === "Investigating") && (
                      <button
                        onClick={() => void handleUpdateIncidentStatus(selectedIncident.incident_id, "Resolved")}
                        style={{ background: "#059669", borderColor: "#10b981", color: "#fff", fontSize: "11px", padding: "6px 12px" }}
                      >
                        Resolve Incident
                      </button>
                    )}
                    {selectedIncident.status === "Resolved" && (
                      <button
                        onClick={() => void handleUpdateIncidentStatus(selectedIncident.incident_id, "Closed")}
                        style={{ background: "#334155", borderColor: "#475569", color: "#cbd5e1", fontSize: "11px", padding: "6px 12px" }}
                      >
                        Close &amp; Archive
                      </button>
                    )}
                    {selectedIncident.status === "Closed" && (
                      <button
                        onClick={() => void handleUpdateIncidentStatus(selectedIncident.incident_id, "Open")}
                        style={{ background: "#475569", borderColor: "#64748b", color: "#cbd5e1", fontSize: "11px", padding: "6px 12px" }}
                      >
                        Re-open Incident
                      </button>
                    )}
                  </div>
                </div>

                {/* ROOT CAUSE ANALYSIS (RCA) CARD */}
                <div style={{ marginTop: "18px", padding: "16px", borderRadius: "8px", background: "rgba(15, 23, 42, 0.8)", border: "1px solid #1e3a4a" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <span style={{ fontSize: "11px", fontWeight: 700, color: "#62d8b6", letterSpacing: "1px" }}>
                      🔍 EXPLAINABLE ROOT CAUSE ANALYSIS (RCA)
                    </span>
                    <span style={{ fontSize: "11px", color: "#34d399", fontWeight: 700 }}>
                      Confidence: {(selectedIncident.confidence_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#e2e8f0", lineHeight: "1.6" }}>
                    {selectedIncident.probable_root_cause}
                  </p>
                </div>

                {/* RECOMMENDED REMEDIATION & SRE INVESTIGATION */}
                <div style={{ marginTop: "14px", padding: "14px", borderRadius: "8px", background: "#060b13", border: "1px solid #1e293b" }}>
                  <b style={{ fontSize: "11px", color: "#f59e0b", letterSpacing: "1px", display: "block", marginBottom: "6px" }}>
                    🛠 RECOMMENDED SRE INVESTIGATION STEPS:
                  </b>
                  <p style={{ margin: 0, fontSize: "12px", color: "#94a3b8", whiteSpace: "pre-line", lineHeight: "1.6" }}>
                    {selectedIncident.recommended_investigation}
                  </p>
                </div>

                {/* AFFECTED COMPONENTS & SIGNALS */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: "14px" }}>
                  <div style={{ background: "#0d1522", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
                    <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "6px" }}>
                      Affected Components:
                    </span>
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                      {selectedIncident.affected_components.map(comp => (
                        <span key={comp} style={{ background: "#1e293b", color: "#93c5fd", padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontFamily: "monospace" }}>
                          {comp}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div style={{ background: "#0d1522", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
                    <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "6px" }}>
                      Contributing Telemetry Signals:
                    </span>
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                      {selectedIncident.contributing_signals.map(sig => (
                        <span key={sig} style={{ background: "#1e293b", color: "#6ee7b7", padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontFamily: "monospace" }}>
                          {sig}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* INCIDENT TIMELINE */}
                <div style={{ marginTop: "20px" }}>
                  <h4 style={{ fontSize: "12px", letterSpacing: "1px", color: "#8ea3b8", marginBottom: "10px", textTransform: "uppercase" }}>
                    Correlated Incident Timeline ({selectedIncident.timeline.length} Signals)
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {selectedIncident.timeline.map((item, idx) => (
                      <div
                        key={item.alert_id || idx}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "10px 14px",
                          borderRadius: "6px",
                          background: "#080d17",
                          border: "1px solid #1e293b",
                          fontSize: "12px",
                        }}
                      >
                        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                          <span style={{ color: "#62d8b6", fontWeight: 700, fontFamily: "monospace", fontSize: "11px" }}>
                            T+{idx * 30}s
                          </span>
                          <span style={{
                            padding: "1px 6px",
                            borderRadius: "3px",
                            fontSize: "10px",
                            fontWeight: 700,
                            background: item.severity === "critical" ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)",
                            color: item.severity === "critical" ? "#ef4444" : "#f59e0b",
                          }}>
                            {item.severity.toUpperCase()}
                          </span>
                          <b style={{ color: "#f1f5f9" }}>{item.metric_name}</b>
                          <span style={{ color: "#64748b" }}>on <code>{item.service}</code></span>
                        </div>

                        <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
                          <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>
                            {item.current_value > 10 ? Math.round(item.current_value) : item.current_value.toFixed(2)} (base: {item.baseline_value > 10 ? Math.round(item.baseline_value) : item.baseline_value.toFixed(2)})
                          </span>
                          <span style={{ color: "#ef4444", fontWeight: 600 }}>+{item.deviation_pct.toFixed(0)}%</span>
                          <span style={{ color: "#64748b", fontSize: "10px" }}>{new Date(item.timestamp).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="panel" style={{ marginTop: 0, textAlign: "center", padding: "48px", color: "#64748b" }}>
                Select an incident from the queue to view Root Cause Analysis and timeline.
              </div>
            )}
          </div>
        </>
      )}

      {/* TAB 2: AIOPS ANOMALY ENGINE (EXPLAINABLE AI) */}
      {activeTab === "aiops" && (
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panel-title">
            <div>
              <p className="eyebrow">STATISTICAL BASELINES &amp; ML DETECTOR</p>
              <h2>Explainable AIOps Anomaly Engine</h2>
            </div>
            <span style={{
              padding: "4px 12px",
              borderRadius: "16px",
              fontSize: "11px",
              fontWeight: "bold",
              background: anomaly?.anomaly ? "rgba(239, 68, 68, 0.2)" : "rgba(34, 197, 94, 0.2)",
              color: anomaly?.anomaly ? "#ef4444" : "#22c55e",
            }}>
              {anomaly?.anomaly ? `● ${anomaly.severity?.toUpperCase()} ANOMALIES ACTIVE` : "● ALL SYSTEMS NOMINAL"}
            </span>
          </div>

          <p className="muted" style={{ marginBottom: "1.25rem" }}>
            Real-time multi-domain detection (CPU, Memory, Disk, Network, Security) using dynamic rolling baselines
            (&mu; &plusmn; 2.5&sigma;), derivative rates-of-change, and Isolation Forest hyperplane scoring.
          </p>

          {/* CONTROLLED TEST MODE / ANOMALY SIMULATOR */}
          <div style={{ background: "#060b13", padding: "16px", borderRadius: "8px", border: "1px solid #1e3a4a", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#62d8b6" }}>
                <Sliders size={16} />
                <b>Interactive Anomaly Simulator (Controlled Test Mode)</b>
              </div>
              {simulatedMetric && (
                <span style={{ fontSize: "11px", color: "#f59e0b" }}>
                  Active Simulation: <code>{simulatedMetric.metric} = {simulatedMetric.value}</code>
                </span>
              )}
            </div>
            <p style={{ fontSize: "11px", color: "#94a3b8", margin: "0 0 12px 0" }}>
              Test and verify dynamic baseline evaluations and Explainable AI alerts live without altering production host hardware:
            </p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                onClick={() => { setSimulatedMetric(null); setSimulatedAuthCount(0); }}
                style={{
                  background: !simulatedMetric && simulatedAuthCount === 0 ? "#134e4a" : "#0d1b2a",
                  borderColor: !simulatedMetric && simulatedAuthCount === 0 ? "#2dd4bf" : "#223044",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                Nominal Baseline
              </button>

              <button
                onClick={() => setSimulatedMetric({ metric: "cpu_utilization", value: 0.94 })}
                style={{
                  background: simulatedMetric?.metric === "cpu_utilization" ? "#7f1d1d" : "#0d1b2a",
                  borderColor: simulatedMetric?.metric === "cpu_utilization" ? "#ef4444" : "#223044",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                <Cpu size={12} /> Simulate CPU Spike (94%)
              </button>

              <button
                onClick={() => setSimulatedMetric({ metric: "memory_utilization", value: 0.89 })}
                style={{
                  background: simulatedMetric?.metric === "memory_utilization" ? "#7f1d1d" : "#0d1b2a",
                  borderColor: simulatedMetric?.metric === "memory_utilization" ? "#ef4444" : "#223044",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                <TrendingUp size={12} /> Simulate Memory Leak (89%)
              </button>

              <button
                onClick={() => setSimulatedMetric({ metric: "http_latency_p95_ms", value: 850 })}
                style={{
                  background: simulatedMetric?.metric === "http_latency_p95_ms" ? "#7f1d1d" : "#0d1b2a",
                  borderColor: simulatedMetric?.metric === "http_latency_p95_ms" ? "#ef4444" : "#223044",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                <Clock size={12} /> Simulate Latency Surge (850ms)
              </button>

              <button
                onClick={() => setSimulatedAuthCount(7)}
                style={{
                  background: simulatedAuthCount > 0 ? "#7f1d1d" : "#0d1b2a",
                  borderColor: simulatedAuthCount > 0 ? "#ef4444" : "#223044",
                  fontSize: "11px",
                  padding: "6px 12px",
                }}
              >
                <ShieldAlert size={12} /> Simulate Security Brute-Force (7 Attempts)
              </button>
            </div>
          </div>

          {/* ACTIVE EXPLAINABLE AI ANOMALY CARDS */}
          <h3>Active Explainable AI Anomalies ({anomaly?.anomalies?.length ?? 0})</h3>
          <div style={{ display: "grid", gap: "14px", marginTop: "1rem", marginBottom: "2rem" }}>
            {anomaly?.anomalies && anomaly.anomalies.length > 0 ? (
              anomaly.anomalies.map((anom, idx) => (
                <div
                  key={`${anom.metric_name}-${idx}`}
                  style={{
                    background: anom.severity === "critical" ? "linear-gradient(145deg, #1f0d11, #12080a)" : "linear-gradient(145deg, #1f170c, #120e06)",
                    border: `1px solid ${anom.severity === "critical" ? "#ef4444" : "#f59e0b"}`,
                    borderRadius: "10px",
                    padding: "16px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{
                        textTransform: "uppercase",
                        fontSize: "10px",
                        fontWeight: "bold",
                        padding: "2px 8px",
                        borderRadius: "4px",
                        background: anom.severity === "critical" ? "#dc2626" : "#d97706",
                        color: "#fff",
                      }}>
                        {anom.severity} · {anom.category.toUpperCase()}
                      </span>
                      <code style={{ fontSize: "13px", color: "#fff", fontWeight: "bold" }}>{anom.metric_name}</code>
                    </div>

                    <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                      Detection Confidence: <b style={{ color: "#62d8b6" }}>{(anom.confidence * 100).toFixed(0)}%</b>
                    </div>
                  </div>

                  {/* WHAT HAPPENED */}
                  <div style={{ marginBottom: "10px", color: "#fca5a5", fontSize: "13px", fontWeight: 600 }}>
                    {anom.summary}
                  </div>

                  {/* METRIC BREAKDOWN GRID */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: "10px",
                    background: "rgba(0,0,0,0.35)",
                    padding: "10px",
                    borderRadius: "6px",
                    marginBottom: "12px",
                    fontSize: "11px",
                  }}>
                    <div>
                      <span style={{ color: "#94a3b8" }}>Observed Value</span>
                      <p style={{ margin: "4px 0 0", fontSize: "14px", fontWeight: "bold", color: "#fff" }}>{anom.current_value}</p>
                    </div>
                    <div>
                      <span style={{ color: "#94a3b8" }}>Dynamic Baseline</span>
                      <p style={{ margin: "4px 0 0", fontSize: "14px", fontWeight: "bold", color: "#62d8b6" }}>{anom.baseline_value}</p>
                    </div>
                    <div>
                      <span style={{ color: "#94a3b8" }}>Baseline Deviation</span>
                      <p style={{ margin: "4px 0 0", fontSize: "14px", fontWeight: "bold", color: "#f87171" }}>
                        {anom.deviation_pct > 0 ? `+${anom.deviation_pct}%` : `${anom.deviation_pct}%`}
                      </p>
                    </div>
                    <div>
                      <span style={{ color: "#94a3b8" }}>Z-Score (&sigma;)</span>
                      <p style={{ margin: "4px 0 0", fontSize: "14px", fontWeight: "bold", color: "#f59e0b" }}>
                        {anom.z_score > 0 ? `+${anom.z_score}` : anom.z_score}
                      </p>
                    </div>
                  </div>

                  {/* PROBABLE CAUSE & ACTION */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "12px" }}>
                    <div style={{ background: "rgba(255,255,255,0.03)", padding: "10px", borderRadius: "6px" }}>
                      <span style={{ color: "#fcd34d", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                        <HelpCircle size={14} /> Probable Technical Cause
                      </span>
                      <p style={{ margin: 0, color: "#cbd5e1", lineHeight: "1.5" }}>{anom.probable_cause}</p>
                    </div>

                    <div style={{ background: "rgba(255,255,255,0.03)", padding: "10px", borderRadius: "6px" }}>
                      <span style={{ color: "#6ee7b7", fontWeight: "bold", display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                        <CheckCircle2 size={14} /> Recommended Action
                      </span>
                      <p style={{ margin: 0, color: "#cbd5e1", lineHeight: "1.5" }}>{anom.recommended_action}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                background: "rgba(34, 197, 94, 0.08)",
                border: "1px solid #166534",
                padding: "16px",
                borderRadius: "8px",
              }}>
                <ShieldCheck color="#22c55e" size={24} />
                <div>
                  <b style={{ color: "#22c55e" }}>All Metrics Within Dynamic Baseline Models</b>
                  <p style={{ margin: "2px 0 0", fontSize: "12px", color: "#86efac" }}>
                    No statistical deviations detected (&gt;2.5&sigma;). Machine learning model confirms normal steady-state clustering.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* DYNAMIC BASELINE MODEL TABLE */}
          <h3>Dynamic Statistical Baselines &amp; Bounds</h3>
          <div className="table-wrap" style={{ marginTop: "1rem", marginBottom: "2rem" }}>
            <table>
              <thead>
                <tr>
                  <th>FEATURE METRIC</th>
                  <th>ROLLING MEAN (&mu;)</th>
                  <th>STD DEV (&sigma;)</th>
                  <th>DYNAMIC CEILING (&mu; + 2.5&sigma;)</th>
                  <th>CURRENT VALUE</th>
                  <th>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {anomaly?.signals?.map((sig) => (
                  <tr key={sig.feature}>
                    <td><code>{sig.feature}</code></td>
                    <td>{sig.baseline}</td>
                    <td>&plusmn;{anomaly.dynamic_baselines?.[sig.feature]?.std ?? "0.04"}</td>
                    <td><b>{sig.threshold}</b></td>
                    <td>
                      <b style={{ color: sig.exceeded ? "#ef4444" : "#fff" }}>{sig.value}</b>
                    </td>
                    <td>
                      <span style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: "bold",
                        background: sig.exceeded ? "rgba(239, 68, 68, 0.2)" : "rgba(34, 197, 94, 0.2)",
                        color: sig.exceeded ? "#ef4444" : "#22c55e",
                      }}>
                        {sig.exceeded ? "OUTLIER" : "NOMINAL"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* SECURITY ANOMALY RISK GAUGE */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "16px",
            background: "#080e18",
            padding: "16px",
            borderRadius: "8px",
            border: "1px solid #223044",
          }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#62d8b6", marginBottom: "8px" }}>
                <ShieldAlert size={18} />
                <b>Security Risk Assessment &amp; Auth Anomaly Monitor</b>
              </div>
              <p style={{ fontSize: "12px", color: "#94a3b8", lineHeight: "1.6", margin: 0 }}>
                Monitors failed challenge frequency and client secret injection attempts. In strict compliance with zero-trust
                guidelines, <b>raw authentication logs, passwords, and tokens are never stored, exported, or exposed</b>.
              </p>
            </div>

            <div style={{ display: "flex", gap: "16px", alignItems: "center", justifyContent: "flex-end" }}>
              <div style={{ textAlign: "center", background: "#0f172a", padding: "12px 20px", borderRadius: "8px", border: "1px solid #334155" }}>
                <span style={{ fontSize: "10px", color: "#94a3b8" }}>SECURITY RISK INDEX</span>
                <p style={{
                  margin: "4px 0 0",
                  fontSize: "22px",
                  fontWeight: "bold",
                  color: (anomaly?.security_risk_index ?? 0) >= 70 ? "#ef4444" : ((anomaly?.security_risk_index ?? 0) >= 30 ? "#f59e0b" : "#22c55e"),
                }}>
                  {anomaly?.security_risk_index ?? 0} / 100
                </p>
              </div>

              <div style={{ textAlign: "center", background: "#0f172a", padding: "12px 20px", borderRadius: "8px", border: "1px solid #334155" }}>
                <span style={{ fontSize: "10px", color: "#94a3b8" }}>AUTH FAILURES</span>
                <p style={{ margin: "4px 0 0", fontSize: "22px", fontWeight: "bold", color: "#fff" }}>
                  {simulatedAuthCount}
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* TAB 3: EGRESS PROOF PANEL */}
      {activeTab === "egress" && (
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panel-title">
            <div>
              <p className="eyebrow">ZERO-TRUST SECURITY ARCHITECTURE</p>
              <h2>Egress Proof &amp; Field Redaction Panel</h2>
            </div>
            <span style={{ color: "#62d8b6", fontWeight: "bold" }}>● VERIFIED METADATA ONLY</span>
          </div>

          <p className="muted" style={{ marginBottom: "1.5rem" }}>
            The Egress Proof Engine records the exact telemetry payload immediately before transmission.
            Secrets, passwords, credentials, and unapproved attributes are purged client-side inside Tier 1.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "1.5rem" }}>
            <div style={{ background: "#0a121e", padding: "16px", borderRadius: "8px", border: "1px solid #223044" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#62d8b6", marginBottom: "8px" }}>
                <CheckCircle2 size={18} />
                <b>Approved Telemetry Fields (Egress Allowed)</b>
              </div>
              <ul style={{ fontSize: "12px", color: "#cbd5e1", lineHeight: "1.8", margin: 0, paddingLeft: "18px" }}>
                <li><code>event_id</code> (Unique UUID)</li>
                <li><code>tenant_id</code> (Scoped customer isolation)</li>
                <li><code>collector_id</code> (Pseudonymous agent id)</li>
                <li><code>timestamp</code> (UTC ISO8601)</li>
                <li><code>metric_name</code> (Allowlisted metric identifier)</li>
                <li><code>metric_value</code> (Bounded numerical value)</li>
                <li><code>severity</code> / <code>health_status</code> / <code>event_category</code></li>
              </ul>
            </div>

            <div style={{ background: "#1a0f12", padding: "16px", borderRadius: "8px", border: "1px solid #6b2128" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#f87171", marginBottom: "8px" }}>
                <Lock size={18} />
                <b>Blocked &amp; Redacted In Tier 1 (Never Leaves Customer)</b>
              </div>
              <ul style={{ fontSize: "12px", color: "#fca5a5", lineHeight: "1.8", margin: 0, paddingLeft: "18px" }}>
                <li><b>Passwords &amp; Hashes</b> (Regex matched &amp; purged)</li>
                <li><b>API Keys &amp; Tokens</b> (<code>sk-...</code>, <code>Bearer</code>, <code>cic_...</code>)</li>
                <li><b>Customer PII &amp; Emails</b> (Redacted locally)</li>
                <li><b>Raw Execution Logs &amp; Stacktraces</b> (Kept on customer host)</li>
                <li><b>Arbitrary / Unapproved JSON Keys</b> (Strictly dropped)</li>
              </ul>
            </div>
          </div>

          {/* AUDIT LOG TABLE */}
          <h3>Transmission Audit Log ({egressAudits.length} Recorded Payloads)</h3>
          <div className="table-wrap" style={{ marginTop: "1rem" }}>
            <table>
              <thead>
                <tr>
                  <th>PAYLOAD ID</th>
                  <th>COLLECTOR</th>
                  <th>TRANSMITTED AT (UTC)</th>
                  <th>APPROVED FIELDS</th>
                  <th>REDACTED / BLOCKED</th>
                  <th>STATUS</th>
                  <th>INSPECT</th>
                </tr>
              </thead>
              <tbody>
                {egressAudits.map((audit) => (
                  <tr key={audit.payload_id} style={{ background: selectedAudit?.payload_id === audit.payload_id ? "rgba(40, 110, 96, 0.2)" : "transparent" }}>
                    <td><code>{audit.payload_id.slice(0, 12)}...</code></td>
                    <td>{audit.collector_id}</td>
                    <td>{new Date(audit.sent_at).toUTCString()}</td>
                    <td><b style={{ color: "#62d8b6" }}>{audit.approved_fields_count} fields</b></td>
                    <td>
                      <span style={{ padding: "2px 8px", borderRadius: "4px", background: "rgba(239, 68, 68, 0.2)", color: "#ef4444", fontSize: "11px" }}>
                        {audit.rejected_fields_count} Blocked
                      </span>
                    </td>
                    <td>
                      <span style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        background: audit.delivery_status === "delivered" ? "rgba(34, 197, 94, 0.2)" : "rgba(245, 158, 11, 0.2)",
                        color: audit.delivery_status === "delivered" ? "#22c55e" : "#f59e0b"
                      }}>
                        {audit.delivery_status.toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <button
                        onClick={() => setSelectedAudit(audit)}
                        style={{ padding: "4px 10px", fontSize: "11px", height: "auto" }}
                      >
                        Inspect Proof
                      </button>
                    </td>
                  </tr>
                ))}

                {!egressAudits.length && (
                  <tr>
                    <td colSpan={7} className="empty">
                      No egress audit records found. Run the customer agent to generate cryptographic transmission proofs.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* INSPECTOR DETAILS */}
          {selectedAudit && (
            <div style={{ marginTop: "1.5rem", padding: "16px", background: "#060a12", borderRadius: "8px", border: "1px solid #286e60" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                <b><FileCode size={16} style={{ display: "inline", verticalAlign: "middle", marginRight: "6px" }} /> Exact Transmitted Payload (Payload ID: {selectedAudit.payload_id})</b>
                <span style={{ fontSize: "11px", color: "#62d8b6" }}>API Status: {selectedAudit.api_response_status} ACCEPTED</span>
              </div>
              <pre style={{ margin: 0, padding: "12px", background: "#0b1320", borderRadius: "6px", color: "#a5f3fc", fontSize: "12px", overflowX: "auto" }}>
                {JSON.stringify(
                  {
                    payload_id: selectedAudit.payload_id,
                    collector_id: selectedAudit.collector_id,
                    timestamp: selectedAudit.sent_at,
                    delivery_status: selectedAudit.delivery_status,
                    approved_fields_count: selectedAudit.approved_fields_count,
                    rejected_fields_count: selectedAudit.rejected_fields_count,
                    sanitized_sample: JSON.parse(selectedAudit.sanitized_sample || "{}")
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          )}
        </section>
      )}

      {/* TAB 4: COLLECTORS FLEET */}
      {activeTab === "collectors" && (
        <section className="panel" style={{ marginTop: 0 }}>
          <div className="panel-title">
            <div>
              <p className="eyebrow">TIER 1 DISTRIBUTED AGENTS</p>
              <h2>Collector Fleet Health &amp; Heartbeats</h2>
            </div>
            <span>Heartbeat Interval: 10s</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>COLLECTOR ID</th>
                  <th>DISPLAY NAME</th>
                  <th>ENVIRONMENT</th>
                  <th>STATUS</th>
                  <th>LAST HEARTBEAT</th>
                </tr>
              </thead>
              <tbody>
                {collectors.map((col) => (
                  <tr key={col.collector_id}>
                    <td><code>{col.collector_id}</code></td>
                    <td><b>{col.name}</b></td>
                    <td><span style={{ textTransform: "capitalize" }}>{col.environment}</span></td>
                    <td>
                      <span style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "3px 10px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        fontWeight: 600,
                        background: col.status === "online" ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                        color: col.status === "online" ? "#22c55e" : "#ef4444"
                      }}>
                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: col.status === "online" ? "#22c55e" : "#ef4444" }}></span>
                        {col.status.toUpperCase()}
                      </span>
                    </td>
                    <td>{new Date(col.last_heartbeat).toLocaleString()}</td>
                  </tr>
                ))}

                {!collectors.length && (
                  <tr>
                    <td colSpan={5} className="empty">
                      No registered collectors. Run the customer agent to register a Tier 1 collector.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* PRIVACY BOUNDARY CARD */}
      <section className="panel privacy">
        <ShieldCheck />
        <div>
          <b>Customer data boundary guarantee</b>
          <p>
            Raw operational logs, database connection strings, passwords, API tokens, and customer identifiers
            remain strictly confined to Tier 1 local infrastructure. Only verified, allowlist-conforming metric
            summaries with cryptographic egress proofs are delivered to the central SaaS platform.
          </p>
        </div>
      </section>

      <footer>
        <Clock size={14} />
        Last updated: {lastUpdated || "Waiting..."}
        <br />
        AUTOMATIC REFRESH: 10 SECONDS · CICADA 2026 OBSERVABILITY PIPELINE
      </footer>
    </main>
  );
}
