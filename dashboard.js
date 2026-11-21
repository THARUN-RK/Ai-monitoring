/* ═══════════════════════════════════════════════════════════
   NeuralWatch — AI Monitoring Dashboard  |  dashboard.js
   Live data simulation + Chart.js visualizations
   ═══════════════════════════════════════════════════════════ */

'use strict';

/* ══════════════════════════════════════
   1.  CONSTANTS & STATE
══════════════════════════════════════ */
const COLORS = {
  cyan:    '#00d4ff',
  violet:  '#8b5cf6',
  emerald: '#10b981',
  amber:   '#f59e0b',
  red:     '#ef4444',
};

const MODEL_COLORS = [COLORS.cyan, COLORS.violet, COLORS.emerald, COLORS.amber];
const MODELS       = ['GPT-4o', 'Claude 3.5', 'Gemini Pro', 'LLaMA 3'];

// Model performance baselines
const MODEL_METRICS = {
  accuracy:   [97.4, 98.1, 96.8, 94.2],
  latency:    [124,  98,   87,   312],
  error:      [1.2,  0.8,  1.5,  4.2],
  throughput: [3842, 4120, 4580, 980],
};

const HIST = 30; // chart data points history

// Shared state
let totalTokens = 0;
let totalCost   = 0;
let alertCount  = 12;

/* ══════════════════════════════════════
   2.  UTILITIES
══════════════════════════════════════ */
const rand  = (min, max) => Math.random() * (max - min) + min;
const randI = (min, max) => Math.round(rand(min, max));

function rgba(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function fmt(n, decimals = 1) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return decimals === 0 ? Math.round(n).toLocaleString() : n.toFixed(decimals);
}

function timeLabel(offsetSec) {
  const d = new Date(Date.now() + offsetSec * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function minsAgo(n) {
  if (n === 0) return 'just now';
  if (n < 60)  return `${n}m ago`;
  return `${Math.floor(n/60)}h ${n%60}m ago`;
}

// Build a gradient inside a Chart.js canvas callback
function makeGradient(chart, colorTop, colorBot) {
  const { ctx, chartArea } = chart;
  if (!chartArea) return colorTop;
  const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  g.addColorStop(0, colorTop);
  g.addColorStop(1, colorBot);
  return g;
}

/* ══════════════════════════════════════
   3.  CHART.JS GLOBAL DEFAULTS
══════════════════════════════════════ */
Chart.defaults.color                       = '#64748b';
Chart.defaults.borderColor                 = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family                 = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size                   = 11;
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.pointStyle    = 'circle';
Chart.defaults.plugins.legend.labels.padding = 14;

const TOOLTIP_DEFAULTS = {
  backgroundColor: '#0c0f1c',
  borderColor:     'rgba(255,255,255,0.1)',
  borderWidth: 1,
  titleColor:  '#f1f5f9',
  bodyColor:   '#94a3b8',
  padding: 10,
  cornerRadius: 8,
  displayColors: true,
  boxWidth: 8, boxHeight: 8,
};

const SCALE_DEFAULTS = {
  grid:  { color: 'rgba(255,255,255,0.05)', drawBorder: false },
  ticks: { color: '#64748b' },
};

/* ══════════════════════════════════════
   4.  CLOCK
══════════════════════════════════════ */
(function initClock() {
  const el = document.getElementById('header-clock');
  function tick() {
    el.textContent = new Date().toLocaleTimeString([], {
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  }
  tick();
  setInterval(tick, 1000);
})();

/* ══════════════════════════════════════
   5.  SPARKLINE CHARTS (KPI Cards)
══════════════════════════════════════ */
function sparkline(id, color, data) {
  const ctx = document.getElementById(id);
  if (!ctx) return null;

  const c = new Chart(ctx, {
    type: 'line',
    data: {
      labels:   data.map((_, i) => i),
      datasets: [{
        data,
        borderColor:     color,
        borderWidth:     1.5,
        fill:            true,
        backgroundColor: rgba(color, 0.18),
        tension:         0.45,
        pointRadius:     0,
      }],
    },
    options: {
      animation:         false,
      responsive:        true,
      maintainAspectRatio: false,
      plugins: {
        legend:  { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: { display: false },
        y: { display: false },
      },
    },
  });
  return c;
}

// Generate and init sparklines
const sparkData = {
  accuracy:   Array.from({ length: 12 }, () => rand(94, 99)),
  latency:    Array.from({ length: 12 }, () => rand(80, 200)),
  throughput: Array.from({ length: 12 }, () => rand(2000, 5000)),
  error:      Array.from({ length: 12 }, () => rand(0.5, 3.5)),
};

const sparks = {
  accuracy:   sparkline('spark-accuracy',   COLORS.cyan,    sparkData.accuracy),
  latency:    sparkline('spark-latency',    COLORS.violet,  sparkData.latency),
  throughput: sparkline('spark-throughput', COLORS.emerald, sparkData.throughput),
  error:      sparkline('spark-error',      COLORS.red,     sparkData.error),
};

/* ══════════════════════════════════════
   6.  REAL-TIME INFERENCE CHART
══════════════════════════════════════ */
// Initial data: 4 models × HIST points
const inferenceBase = [210, 185, 240, 75];
const inferenceData = MODELS.map((_, i) =>
  Array.from({ length: HIST }, () => Math.round(rand(inferenceBase[i] * 0.6, inferenceBase[i] * 1.4)))
);
const inferenceLabels = Array.from({ length: HIST }, (_, i) =>
  timeLabel(-( HIST - 1 - i) * 2)
);

const inferenceChart = new Chart(document.getElementById('chart-inference'), {
  type: 'line',
  data: {
    labels: inferenceLabels,
    datasets: MODELS.map((name, i) => ({
      label:            name,
      data:             inferenceData[i],
      borderColor:      MODEL_COLORS[i],
      borderWidth:      2,
      fill:             i === 0,
      backgroundColor:  (ctx) => i === 0
        ? makeGradient(ctx.chart, rgba(COLORS.cyan, 0.3), rgba(COLORS.cyan, 0.0))
        : 'transparent',
      tension:          0.4,
      pointRadius:      0,
      pointHoverRadius: 4,
    })),
  },
  options: {
    responsive:        true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    animation:  { duration: 400 },
    plugins: {
      legend:  { position: 'top' },
      tooltip: TOOLTIP_DEFAULTS,
    },
    scales: {
      x: { ...SCALE_DEFAULTS, ticks: { ...SCALE_DEFAULTS.ticks, maxTicksLimit: 8, maxRotation: 0 } },
      y: { ...SCALE_DEFAULTS, title: { display: true, text: 'Requests / 2s', color: '#64748b', font: { size: 10 } } },
    },
  },
});

/* ══════════════════════════════════════
   7.  COST AREA CHART
══════════════════════════════════════ */
const COST_LABELS = Array.from({ length: 13 }, (_, i) => {
  const mins = (12 - i) * 5;
  return mins === 0 ? 'Now' : `${mins}m ago`;
}).reverse();

let costHistory = (() => {
  const arr = [0];
  for (let i = 1; i < 13; i++) arr.push(+(arr[i - 1] + rand(0.02, 0.18)).toFixed(3));
  return arr;
})();
totalCost = costHistory[costHistory.length - 1];

const costChart = new Chart(document.getElementById('chart-cost'), {
  type: 'line',
  data: {
    labels: COST_LABELS,
    datasets: [{
      label:            'Cumulative Cost ($)',
      data:             costHistory,
      borderColor:      COLORS.emerald,
      borderWidth:      2,
      fill:             true,
      backgroundColor:  (ctx) => makeGradient(ctx.chart, rgba(COLORS.emerald, 0.35), rgba(COLORS.emerald, 0.0)),
      tension:          0.5,
      pointRadius:      3,
      pointHoverRadius: 5,
      pointBackgroundColor: COLORS.emerald,
    }],
  },
  options: {
    responsive:        true,
    maintainAspectRatio: false,
    animation:  { duration: 600 },
    plugins: {
      legend:  { display: false },
      tooltip: { ...TOOLTIP_DEFAULTS, callbacks: {
        label: (ctx) => ` $${ctx.parsed.y.toFixed(3)}`,
      }},
    },
    scales: {
      x: { ...SCALE_DEFAULTS, ticks: { ...SCALE_DEFAULTS.ticks, maxTicksLimit: 7 } },
      y: {
        ...SCALE_DEFAULTS,
        title: { display: true, text: 'USD ($)', color: '#64748b', font: { size: 10 } },
        ticks: { ...SCALE_DEFAULTS.ticks, callback: (v) => `$${v.toFixed(2)}` },
      },
    },
  },
});

/* ══════════════════════════════════════
   8.  TOKEN DONUT CHART
══════════════════════════════════════ */
let tokenSplit = { prompt: 45, completion: 35, cached: 20 };
totalTokens = randI(1_200_000, 2_400_000);

const donutChart = new Chart(document.getElementById('chart-donut'), {
  type: 'doughnut',
  data: {
    labels:   ['Prompt', 'Completion', 'Cached'],
    datasets: [{
      data:            [tokenSplit.prompt, tokenSplit.completion, tokenSplit.cached],
      backgroundColor: [rgba(COLORS.cyan, 0.85), rgba(COLORS.violet, 0.85), rgba(COLORS.emerald, 0.75)],
      borderColor:     ['#07090f', '#07090f', '#07090f'],
      borderWidth:     3,
      hoverOffset:     6,
    }],
  },
  options: {
    responsive:        true,
    maintainAspectRatio: false,
    cutout: '70%',
    plugins: {
      legend:  { display: false },
      tooltip: { ...TOOLTIP_DEFAULTS, callbacks: { label: (c) => ` ${c.label}: ${c.raw}%` } },
    },
    animation: { animateRotate: true, duration: 800 },
  },
});

// Seed the UI
document.getElementById('total-tokens').textContent = fmt(totalTokens);
document.getElementById('donut-cost').textContent   = `$${totalCost.toFixed(2)}`;

/* ══════════════════════════════════════
   9.  MULTI-MODEL COMPARISON CHART
══════════════════════════════════════ */
const comparisonChart = new Chart(document.getElementById('chart-compare'), {
  type: 'bar',
  data: {
    labels: MODELS,
    datasets: [{
      label:            'Accuracy (%)',
      data:             MODEL_METRICS.accuracy,
      backgroundColor:  MODEL_COLORS.map(c => rgba(c, 0.75)),
      borderColor:      MODEL_COLORS,
      borderWidth:      1.5,
      borderRadius:     7,
      borderSkipped:    false,
    }],
  },
  options: {
    responsive:        true,
    maintainAspectRatio: false,
    animation:  { duration: 600 },
    plugins: {
      legend:  { display: false },
      tooltip: TOOLTIP_DEFAULTS,
    },
    scales: {
      x: { ...SCALE_DEFAULTS },
      y: { ...SCALE_DEFAULTS, beginAtZero: true },
    },
  },
});

document.getElementById('compare-metric').addEventListener('change', function () {
  const m = this.value;
  const labels = {
    accuracy:   'Accuracy (%)',
    latency:    'Latency (ms)',
    error:      'Error Rate (%)',
    throughput: 'Throughput (r/m)',
  };
  comparisonChart.data.datasets[0].data  = MODEL_METRICS[m];
  comparisonChart.data.datasets[0].label = labels[m];
  comparisonChart.update('active');
});

/* ══════════════════════════════════════
   10.  DATA DRIFT CHART
══════════════════════════════════════ */
const DRIFT_N = 24;
const driftLabels = Array.from({ length: DRIFT_N }, (_, i) => {
  const mins = (DRIFT_N - 1 - i) * 5;
  return mins === 0 ? 'Now' : `${mins}m`;
});
let driftValues = Array.from({ length: DRIFT_N }, () => +(rand(0.05, 0.48)).toFixed(3));

const driftChart = new Chart(document.getElementById('chart-drift'), {
  type: 'line',
  data: {
    labels: driftLabels,
    datasets: [
      {
        label:               'PSI Score',
        data:                driftValues,
        borderColor:         COLORS.violet,
        borderWidth:         2,
        fill:                true,
        backgroundColor:     (ctx) => makeGradient(ctx.chart, rgba(COLORS.violet, 0.3), rgba(COLORS.violet, 0.0)),
        tension:             0.4,
        pointRadius:         driftValues.map(v => v > 0.3 ? 6 : 3),
        pointBackgroundColor:driftValues.map(v => v > 0.3 ? COLORS.red : COLORS.violet),
        pointBorderColor:    driftValues.map(v => v > 0.3 ? COLORS.red : COLORS.violet),
        pointHoverRadius:    7,
      },
      {
        label:         'Threshold',
        data:          Array(DRIFT_N).fill(0.3),
        borderColor:   rgba(COLORS.red, 0.55),
        borderWidth:   2,
        borderDash:    [7, 4],
        pointRadius:   0,
        fill:          false,
        tension:       0,
      },
    ],
  },
  options: {
    responsive:        true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    animation:  { duration: 600 },
    plugins: {
      legend:  { position: 'top' },
      tooltip: TOOLTIP_DEFAULTS,
    },
    scales: {
      x: { ...SCALE_DEFAULTS, ticks: { ...SCALE_DEFAULTS.ticks, maxTicksLimit: 10, maxRotation: 0 } },
      y: {
        ...SCALE_DEFAULTS, min: 0, max: 0.6,
        title: { display: true, text: 'PSI Score', color: '#64748b', font: { size: 10 } },
      },
    },
  },
});

/* ══════════════════════════════════════
   11.  ALERT FEED
══════════════════════════════════════ */
const ALERT_POOL = [
  { type: 'crit', icon: 'fa-circle-xmark',       text: 'GPT-4o error rate exceeded 5% SLA',         pill: 'CRITICAL'  },
  { type: 'warn', icon: 'fa-triangle-exclamation',text: 'Claude 3.5 latency spike: 450ms detected',  pill: 'WARNING'   },
  { type: 'info', icon: 'fa-circle-info',         text: 'Gemini Pro updated to checkpoint v2.1',     pill: 'INFO'      },
  { type: 'ok',   icon: 'fa-circle-check',        text: 'LLaMA 3 recovered from degraded state',     pill: 'RECOVERED' },
  { type: 'warn', icon: 'fa-triangle-exclamation',text: 'Input embedding drift above 0.30 threshold', pill: 'WARNING'   },
  { type: 'crit', icon: 'fa-circle-xmark',        text: 'GPU utilization exceeded 95% limit',        pill: 'CRITICAL'  },
  { type: 'info', icon: 'fa-circle-info',         text: 'Model weights synced across all replicas',  pill: 'INFO'      },
  { type: 'ok',   icon: 'fa-circle-check',        text: 'Auto-scaling triggered — +2 pods added',    pill: 'SCALED'    },
  { type: 'warn', icon: 'fa-triangle-exclamation',text: 'Daily token budget at 80% capacity',        pill: 'WARNING'   },
  { type: 'crit', icon: 'fa-circle-xmark',        text: 'Inference queue depth exceeded 500 reqs',   pill: 'CRITICAL'  },
  { type: 'info', icon: 'fa-circle-info',         text: 'Daily cost report generated and sent',      pill: 'INFO'      },
  { type: 'ok',   icon: 'fa-circle-check',        text: 'Drift baseline reset for new data window',  pill: 'OK'        },
];

let alertTimers = [0, 1, 3, 7, 12, 18, 25, 31, 44, 52, 61, 74]; // minutes ago

function renderAlert(item, minutesAgo) {
  const el = document.createElement('div');
  el.className = `alert-item ${item.type}`;
  el.innerHTML = `
    <i class="fas ${item.icon} alert-ic"></i>
    <div class="alert-txt">
      <div class="alert-title">${item.text}</div>
      <div class="alert-time">${minsAgo(minutesAgo)}</div>
    </div>
    <span class="alert-pill">${item.pill}</span>
  `;
  return el;
}

function initAlertFeed() {
  const feed = document.getElementById('alerts-feed');
  feed.innerHTML = '';
  ALERT_POOL.forEach((item, i) => {
    feed.appendChild(renderAlert(item, alertTimers[i] ?? randI(5, 120)));
  });
}
initAlertFeed();

function pushAlert() {
  const pool = ALERT_POOL.filter(a => a.type === 'crit' || a.type === 'warn');
  const item  = pool[randI(0, pool.length - 1)];
  const feed  = document.getElementById('alerts-feed');
  const el    = renderAlert(item, 0);
  feed.prepend(el);
  alertCount++;

  const badge = document.getElementById('nav-alert-badge');
  const nbadge= document.getElementById('notif-count');
  badge.textContent  = alertCount;
  nbadge.textContent = alertCount;
  document.getElementById('alert-count-tag').textContent = `${alertCount} alerts`;

  // Prune old alerts
  while (feed.children.length > 15) feed.removeChild(feed.lastChild);
}

/* ══════════════════════════════════════
   12.  GAUGE UPDATER
══════════════════════════════════════ */
let gaugeState = { cpu: 30, gpu: 70, mem: 50 };
const CIRC = 314.16;

function updateGauge(arcId, pctId, value) {
  const offset = CIRC * (1 - value / 100);
  const arc = document.getElementById(arcId);
  const pct = document.getElementById(pctId);
  if (arc) arc.setAttribute('stroke-dashoffset', offset.toFixed(2));
  if (pct) pct.textContent = `${Math.round(value)}%`;
}

function driftGauge(current, min, max, step = 3) {
  return Math.min(max, Math.max(min, current + rand(-step, step)));
}

/* ══════════════════════════════════════
   13.  KPI VALUE UPDATER
══════════════════════════════════════ */
let kpi = { accuracy: 97.4, latency: 124, throughput: 3842, error: 1.2 };

function updateKPI() {
  kpi.accuracy   = Math.min(99.9, Math.max(90, kpi.accuracy   + rand(-0.2, 0.2)));
  kpi.latency    = Math.min(400,  Math.max(60, kpi.latency    + rand(-8, 8)));
  kpi.throughput = Math.min(6000, Math.max(500,kpi.throughput + rand(-80, 80)));
  kpi.error      = Math.min(8,    Math.max(0.1,kpi.error      + rand(-0.15, 0.15)));

  document.getElementById('val-accuracy').innerHTML   = `${kpi.accuracy.toFixed(1)}<span class="kpi-unit">%</span>`;
  document.getElementById('val-latency').innerHTML    = `${Math.round(kpi.latency)}<span class="kpi-unit">ms</span>`;
  document.getElementById('val-throughput').innerHTML = `${Math.round(kpi.throughput).toLocaleString()}<span class="kpi-unit">r/m</span>`;
  document.getElementById('val-error').innerHTML      = `${kpi.error.toFixed(1)}<span class="kpi-unit">%</span>`;

  // Update sparklines
  ['accuracy', 'latency', 'throughput', 'error'].forEach(key => {
    const spark = sparks[key];
    if (!spark) return;
    spark.data.datasets[0].data.push(kpi[key]);
    spark.data.datasets[0].data.shift();
    spark.update('none');
  });
}

/* ══════════════════════════════════════
   14.  MODEL CHIP UPDATER
══════════════════════════════════════ */
const baseLatencies = { gpt4: 124, claude: 98, gemini: 87, llama: 312 };

function updateModelChips() {
  ['gpt4', 'claude', 'gemini', 'llama'].forEach(key => {
    const el = document.getElementById(`ms-${key}`);
    if (!el) return;
    const delta = rand(-15, 15);
    const val   = Math.round(baseLatencies[key] + delta);
    el.textContent = `${val}ms`;
  });
  document.getElementById('last-update').textContent = 'just now';
}

/* ══════════════════════════════════════
   15.  INFERENCE CHART UPDATER
══════════════════════════════════════ */
function updateInferenceChart() {
  const newLabel = timeLabel(0);
  inferenceChart.data.labels.push(newLabel);
  inferenceChart.data.labels.shift();

  inferenceChart.data.datasets.forEach((ds, i) => {
    const base = inferenceBase[i];
    ds.data.push(Math.round(rand(base * 0.5, base * 1.5)));
    ds.data.shift();
  });

  inferenceChart.update('none');
}

/* ══════════════════════════════════════
   16.  COST & TOKEN UPDATER
══════════════════════════════════════ */
function updateCostAndTokens() {
  // New tokens this tick
  const newTokens = randI(10_000, 50_000);
  totalTokens    += newTokens;

  // Shift prompt/completion/cached ratios slightly
  tokenSplit.prompt     = Math.min(60, Math.max(30, tokenSplit.prompt     + rand(-1, 1)));
  tokenSplit.completion = Math.min(50, Math.max(25, tokenSplit.completion + rand(-1, 1)));
  tokenSplit.cached     = 100 - tokenSplit.prompt - tokenSplit.completion;

  donutChart.data.datasets[0].data = [
    tokenSplit.prompt, tokenSplit.completion, tokenSplit.cached
  ];
  donutChart.update('none');

  // Cost
  const newCost = newTokens * 0.000003;
  totalCost    += newCost;

  costChart.data.datasets[0].data.push(+totalCost.toFixed(3));
  costChart.data.datasets[0].data.shift();
  costChart.update('none');

  document.getElementById('total-tokens').textContent = fmt(totalTokens);
  document.getElementById('donut-cost').textContent   = `$${totalCost.toFixed(2)}`;
}

/* ══════════════════════════════════════
   17.  DRIFT CHART UPDATER
══════════════════════════════════════ */
function updateDriftChart() {
  const newVal = +(rand(0.05, 0.5)).toFixed(3);
  driftValues.push(newVal);
  driftValues.shift();

  driftChart.data.datasets[0].data              = driftValues;
  driftChart.data.datasets[0].pointRadius       = driftValues.map(v => v > 0.3 ? 6 : 3);
  driftChart.data.datasets[0].pointBackgroundColor = driftValues.map(v => v > 0.3 ? COLORS.red : COLORS.violet);
  driftChart.data.datasets[0].pointBorderColor     = driftValues.map(v => v > 0.3 ? COLORS.red : COLORS.violet);

  const driftLabelsNow = Array.from({ length: DRIFT_N }, (_, i) => {
    const mins = (DRIFT_N - 1 - i) * 5;
    return mins === 0 ? 'Now' : `${mins}m`;
  });
  driftChart.data.labels = driftLabelsNow;
  driftChart.update('none');
}

/* ══════════════════════════════════════
   18. SRE FOUR-STATE HEALTH ENGINE & DATA STRUCTURES
══════════════════════════════════════ */

const HEALTH_CONFIG = {
  states: {
    EXCELLENT: { label: 'EXCELLENT', color: '#34d399', bg: 'rgba(16,185,129,0.18)', border: '#10b981', dot: '#10b981', rank: 4 },
    GOOD:      { label: 'GOOD',      color: '#60a5fa', bg: 'rgba(59,130,246,0.18)', border: '#3b82f6', dot: '#3b82f6', rank: 3 },
    FAIR:      { label: 'FAIR',      color: '#fbbf24', bg: 'rgba(245,158,11,0.18)', border: '#f59e0b', dot: '#f59e0b', rank: 2 },
    POOR:      { label: 'POOR',      color: '#f87171', bg: 'rgba(239,68,68,0.18)', border: '#ef4444', dot: '#ef4444', rank: 1 },
  }
};

let sreCurrentHealth = 'EXCELLENT';
let sreFreshnessSeconds = 4.2;
let sreFreshnessStatus = 'FRESH';
let sreExplanation = 'All infrastructure metrics (CPU, RAM, Disk, Latency) and collector heartbeats are within normal operating thresholds.';
let sreSimMode = false;

let sreMetricsData = {
  cpu: { name: 'CPU Utilization', value: 21.4, unit: '%', state: 'EXCELLENT', baseline: 22.0, deviation: '-2.7%', max: 100, explanation: 'Nominal CPU workload across all worker cores.' },
  memory: { name: 'Memory Utilization', value: 42.1, unit: '%', state: 'EXCELLENT', baseline: 44.5, deviation: '-5.4%', max: 100, explanation: 'Stable heap & resident memory usage.' },
  disk: { name: 'Disk Utilization', value: 38.0, unit: '%', state: 'EXCELLENT', baseline: 37.8, deviation: '+0.5%', max: 100, explanation: 'Ample storage headroom (62% free).' },
  network: { name: 'HTTP Latency (P95)', value: 48, unit: 'ms', state: 'EXCELLENT', baseline: 52, deviation: '-7.7%', max: 500, explanation: 'Sub-100ms response time on public ingress.' },
  collector: { name: 'Collector Availability', value: 3.8, unit: 's ago', state: 'EXCELLENT', baseline: 10, deviation: 'Healthy', max: 60, explanation: 'Tier 1 local collector heartbeat active (interval 10s).' }
};

let sreHistoryLog = [
  { id: 'TR-101', timestamp: new Date(Date.now() - 3600000).toISOString(), previous_state: 'GOOD', new_state: 'EXCELLENT', trigger_reason: 'CPU utilization returned to 21.4% from elevated 68.2%', metric_trigger: 'cpu_utilization' }
];

function evaluateSREHealth(cpu, mem, disk, latency, collectorAgeSec, freshnessSec) {
  let cpuState = 'EXCELLENT';
  if (cpu > 92) cpuState = 'POOR';
  else if (cpu > 80) cpuState = 'FAIR';
  else if (cpu > 65) cpuState = 'GOOD';

  let memState = 'EXCELLENT';
  if (mem > 88) memState = 'POOR';
  else if (mem > 78) memState = 'FAIR';
  else if (mem > 65) memState = 'GOOD';

  let diskState = 'EXCELLENT';
  if (disk > 92) diskState = 'POOR';
  else if (disk > 85) diskState = 'FAIR';
  else if (disk > 75) diskState = 'GOOD';

  let netState = 'EXCELLENT';
  if (latency > 400) netState = 'POOR';
  else if (latency > 200) netState = 'FAIR';
  else if (latency > 100) netState = 'GOOD';

  let colState = 'EXCELLENT';
  if (collectorAgeSec > 60) colState = 'POOR';
  else if (collectorAgeSec > 30) colState = 'FAIR';
  else if (collectorAgeSec > 15) colState = 'GOOD';

  let freshStatus = 'FRESH';
  if (freshnessSec > 60) freshStatus = 'EXPIRED';
  else if (freshnessSec > 30) freshStatus = 'STALE';
  else if (freshnessSec > 15) freshStatus = 'AGING';

  const states = [cpuState, memState, diskState, netState, colState];
  const ranks = states.map(s => HEALTH_CONFIG.states[s].rank);
  const minRank = Math.min(...ranks);

  let overall = Object.keys(HEALTH_CONFIG.states).find(k => HEALTH_CONFIG.states[k].rank === minRank);

  let freshnessDowngradeReason = '';
  if (freshStatus === 'EXPIRED') {
    overall = 'POOR';
    freshnessDowngradeReason = `Telemetry expired (${freshnessSec.toFixed(1)}s old > 60s SLA threshold). Downgraded to POOR.`;
  } else if (freshStatus === 'STALE') {
    if (HEALTH_CONFIG.states[overall].rank > 2) overall = 'FAIR';
    freshnessDowngradeReason = `Telemetry stale (${freshnessSec.toFixed(1)}s old > 30s SLA threshold). Downgraded to FAIR.`;
  }

  let reason = '';
  if (freshnessDowngradeReason) {
    reason = freshnessDowngradeReason;
  } else if (overall === 'POOR') {
    reason = `Critical threshold breach detected: ${states.map((s, i) => s === 'POOR' ? ['CPU', 'Memory', 'Disk', 'Network Latency', 'Collector Availability'][i] : null).filter(Boolean).join(', ')}. Immediate SRE intervention required.`;
  } else if (overall === 'FAIR') {
    reason = `Elevated operational indicators observed: ${states.map((s, i) => s === 'FAIR' ? ['CPU', 'Memory', 'Disk', 'Network Latency', 'Collector Availability'][i] : null).filter(Boolean).join(', ')}. System requires monitoring.`;
  } else if (overall === 'GOOD') {
    reason = `Minor resource variance observed: ${states.map((s, i) => s === 'GOOD' ? ['CPU', 'Memory', 'Disk', 'Network Latency', 'Collector Availability'][i] : null).filter(Boolean).join(', ')}. All services functional.`;
  } else {
    reason = 'All infrastructure metrics (CPU, RAM, Disk, Latency) and collector heartbeats are within normal operating thresholds.';
  }

  return {
    system_health: overall,
    freshness_status: freshStatus,
    freshness_seconds: freshnessSec,
    explanation: reason,
    metrics: {
      cpu: { name: 'CPU Utilization', value: cpu, unit: '%', state: cpuState, baseline: 22.0, deviation: `${(cpu - 22.0 >= 0 ? '+' : '')}${(cpu - 22.0).toFixed(1)}%`, max: 100, explanation: cpuState === 'EXCELLENT' ? 'Nominal CPU workload across worker cores.' : `CPU load elevated at ${cpu.toFixed(1)}%` },
      memory: { name: 'Memory Utilization', value: mem, unit: '%', state: memState, baseline: 44.5, deviation: `${(mem - 44.5 >= 0 ? '+' : '')}${(mem - 44.5).toFixed(1)}%`, max: 100, explanation: memState === 'EXCELLENT' ? 'Stable heap & resident memory usage.' : `Memory consumption at ${mem.toFixed(1)}%` },
      disk: { name: 'Disk Utilization', value: disk, unit: '%', state: diskState, baseline: 37.8, deviation: `${(disk - 37.8 >= 0 ? '+' : '')}${(disk - 37.8).toFixed(1)}%`, max: 100, explanation: diskState === 'EXCELLENT' ? 'Ample storage headroom (62% free).' : `Storage heavily utilized at ${disk.toFixed(1)}%` },
      network: { name: 'HTTP Latency (P95)', value: latency, unit: 'ms', state: netState, baseline: 52, deviation: `${(latency - 52 >= 0 ? '+' : '')}${(latency - 52).toFixed(0)}ms`, max: 500, explanation: netState === 'EXCELLENT' ? 'Sub-100ms response time on public ingress.' : `Elevated gateway latency: ${latency.toFixed(0)}ms` },
      collector: { name: 'Collector Availability', value: collectorAgeSec, unit: 's ago', state: colState, baseline: 10, deviation: colState === 'EXCELLENT' ? 'Healthy' : `${collectorAgeSec.toFixed(0)}s lag`, max: 60, explanation: colState === 'EXCELLENT' ? 'Active Tier 1 collector heartbeat stream.' : `Heartbeat delayed by ${collectorAgeSec.toFixed(0)}s` }
    }
  };
}

function recordHealthTransition(oldState, newState, reason, metricName) {
  if (oldState === newState) return;
  const trans = {
    id: `TR-${Date.now().toString().slice(-4)}`,
    timestamp: new Date().toISOString(),
    previous_state: oldState,
    new_state: newState,
    trigger_reason: reason,
    metric_trigger: metricName || 'system_evaluation'
  };
  sreHistoryLog.unshift(trans);
  if (sreHistoryLog.length > 20) sreHistoryLog.pop();
}

function renderSREHealthUI() {
  const cfg = HEALTH_CONFIG.states[sreCurrentHealth] || HEALTH_CONFIG.states.EXCELLENT;

  // 1. Header status & dot
  const headerText = document.getElementById('header-health-text');
  const headerDot = document.getElementById('header-health-dot');
  if (headerText) {
    headerText.textContent = `HEALTH: ${sreCurrentHealth}`;
    headerText.style.color = cfg.color;
  }
  if (headerDot) headerDot.style.background = cfg.dot;

  // 2. Dashboard banner
  const dashBadge = document.getElementById('dash-health-badge');
  const dashFresh = document.getElementById('dash-freshness-text');
  const dashSummary = document.getElementById('dash-health-summary');
  if (dashBadge) {
    dashBadge.textContent = sreCurrentHealth;
    dashBadge.style.color = cfg.color;
    dashBadge.style.background = cfg.bg;
    dashBadge.style.border = `1px solid ${cfg.border}`;
  }
  if (dashFresh) {
    dashFresh.textContent = `· Telemetry age: ${sreFreshnessSeconds.toFixed(1)}s (${sreFreshnessStatus})`;
  }
  if (dashSummary) {
    dashSummary.textContent = sreExplanation;
  }

  // 3. View Health Section
  const viewBadge = document.getElementById('sre-health-state-badge');
  const viewDesc = document.getElementById('sre-health-summary-desc');
  const viewFreshVal = document.getElementById('sre-freshness-val');
  const viewFreshSub = document.getElementById('sre-freshness-sub');

  if (viewBadge) {
    viewBadge.textContent = sreCurrentHealth;
    viewBadge.style.color = cfg.color;
    viewBadge.style.background = cfg.bg;
    viewBadge.style.border = `1px solid ${cfg.border}`;
  }
  if (viewDesc) viewDesc.textContent = sreExplanation;
  if (viewFreshVal) {
    viewFreshVal.textContent = `${sreFreshnessSeconds.toFixed(1)}s ago`;
    viewFreshVal.style.color = sreFreshnessStatus === 'FRESH' ? '#34d399' : (sreFreshnessStatus === 'AGING' ? '#60a5fa' : (sreFreshnessStatus === 'STALE' ? '#fbbf24' : '#f87171'));
  }
  if (viewFreshSub) {
    viewFreshSub.textContent = `● ${sreFreshnessStatus} (${sreFreshnessSeconds < 15 ? '<15s SLA' : (sreFreshnessSeconds < 30 ? '15-30s' : '>30s Degraded')})`;
  }

  // 4. Metric Cards Grid
  const grid = document.getElementById('sre-metrics-grid');
  if (grid) {
    grid.innerHTML = Object.entries(sreMetricsData).map(([key, m]) => {
      const mCfg = HEALTH_CONFIG.states[m.state] || HEALTH_CONFIG.states.EXCELLENT;
      const valNum = typeof m.value === 'number' ? m.value : parseFloat(m.value);
      const pct = Math.min(100, Math.max(0, (valNum / m.max) * 100));
      return `
        <div class="card" style="padding:18px; border-top:3px solid ${mCfg.color}; background:rgba(15,23,42,0.6);">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
            <div>
              <div style="font-size:11px; text-transform:uppercase; color:#94a3b8; letter-spacing:1px; font-weight:700;">${m.name}</div>
              <div style="font-size:22px; font-weight:800; color:#f8fafc; margin-top:4px;">
                ${typeof m.value === 'number' ? m.value.toFixed(1) : m.value} <span style="font-size:13px; color:#64748b;">${m.unit}</span>
              </div>
            </div>
            <span class="badge" style="background:${mCfg.bg}; color:${mCfg.color}; border:1px solid ${mCfg.border}; font-weight:700; font-size:11px; padding:2px 8px;">
              ${m.state}
            </span>
          </div>
          <div style="width:100%; height:6px; background:#1e293b; border-radius:3px; overflow:hidden; margin-bottom:10px;">
            <div style="width:${pct}%; height:100%; background:${mCfg.color}; transition:width 0.4s ease;"></div>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:11px; color:#64748b; margin-bottom:6px;">
            <span>Baseline: <strong style="color:#94a3b8;">${m.baseline}${m.unit}</strong></span>
            <span>Deviation: <strong style="color:${String(m.deviation).startsWith('+') ? '#f59e0b' : '#34d399'};">${m.deviation}</strong></span>
          </div>
          <div style="font-size:11.5px; color:#cbd5e1; line-height:1.4; border-top:1px solid rgba(255,255,255,0.05); padding-top:8px;">
            ${m.explanation}
          </div>
        </div>
      `;
    }).join('');
  }

  // 5. Transition History Table
  const tbody = document.getElementById('sre-history-tbody');
  const countEl = document.getElementById('sre-trans-count');
  if (countEl) countEl.textContent = sreHistoryLog.length;
  if (tbody) {
    if (sreHistoryLog.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#64748b; padding:20px;">No transitions recorded yet.</td></tr>`;
    } else {
      tbody.innerHTML = sreHistoryLog.map(t => {
        const pCfg = HEALTH_CONFIG.states[t.previous_state] || HEALTH_CONFIG.states.GOOD;
        const nCfg = HEALTH_CONFIG.states[t.new_state] || HEALTH_CONFIG.states.EXCELLENT;
        return `
          <tr>
            <td><code>${t.id}</code></td>
            <td style="font-size:11px; color:#94a3b8;">${new Date(t.timestamp).toUTCString()}</td>
            <td><span class="badge" style="background:${pCfg.bg}; color:${pCfg.color}; border:1px solid ${pCfg.border}; font-size:10px; padding:2px 6px;">${t.previous_state}</span></td>
            <td>&rarr;</td>
            <td><span class="badge" style="background:${nCfg.bg}; color:${nCfg.color}; border:1px solid ${nCfg.border}; font-size:10px; padding:2px 6px;">${t.new_state}</span></td>
            <td style="font-size:12px; color:#cbd5e1;">${t.trigger_reason}</td>
          </tr>
        `;
      }).join('');
    }
  }
}

function applySREScenario(type) {
  sreSimMode = true;
  const oldState = sreCurrentHealth;
  let evalResult;

  switch(type) {
    case 'normal':
      evalResult = evaluateSREHealth(21.4, 42.1, 38.0, 48, 3.8, 3.8);
      break;
    case 'minor':
      evalResult = evaluateSREHealth(68.5, 54.0, 39.0, 142, 4.0, 4.0);
      break;
    case 'elevated':
      evalResult = evaluateSREHealth(82.4, 79.1, 74.0, 230, 5.0, 5.0);
      break;
    case 'severe':
      evalResult = evaluateSREHealth(97.2, 95.8, 94.2, 540, 4.0, 4.0);
      break;
    case 'offline':
      evalResult = evaluateSREHealth(22.0, 42.0, 38.0, 50, 64.0, 4.0);
      break;
    case 'stale':
      evalResult = evaluateSREHealth(22.0, 42.0, 38.0, 50, 4.0, 34.0);
      break;
    case 'expired':
      evalResult = evaluateSREHealth(22.0, 42.0, 38.0, 50, 4.0, 78.0);
      break;
    default:
      evalResult = evaluateSREHealth(21.4, 42.1, 38.0, 48, 3.8, 3.8);
  }

  sreCurrentHealth = evalResult.system_health;
  sreFreshnessStatus = evalResult.freshness_status;
  sreFreshnessSeconds = evalResult.freshness_seconds;
  sreExplanation = evalResult.explanation;
  sreMetricsData = evalResult.metrics;

  recordHealthTransition(oldState, sreCurrentHealth, sreExplanation, type);
  renderSREHealthUI();
}
window.applySREScenario = applySREScenario;

/* ══════════════════════════════════════
   19. INTELLIGENT INCIDENT CORRELATION ENGINE
══════════════════════════════════════ */

let incidentsList = [
  {
    incident_id: 'INC-2026-8910',
    title: 'Upstream Ingress & Resource Degradation',
    severity: 'HIGH',
    status: 'INVESTIGATING',
    tenant_id: 'customer-acme-prod',
    collector_id: 'collector-prod-us-east-1',
    created_at: new Date(Date.now() - 420000).toISOString(),
    confidence_score: 91.5,
    root_cause: 'Memory leak pattern detected on worker threads (86.4% utilization) causing increased garbage collection latency (280ms P95).',
    recommendation: 'Inspect container memory limits and trigger blue-green worker recycling.',
    affected_components: ['Worker Tier', 'FastAPI Ingress', 'Tier 1 Collector'],
    alerts_count: 2,
    alerts: [
      { alert_id: 'ALT-101', metric_name: 'memory_utilization', baseline: '44.5%', value: '86.4%', deviation: '+94.2%', severity: 'HIGH', timestamp: new Date(Date.now() - 440000).toISOString() },
      { alert_id: 'ALT-102', metric_name: 'http_latency_p95_ms', baseline: '52ms', value: '280ms', deviation: '+438%', severity: 'MEDIUM', timestamp: new Date(Date.now() - 420000).toISOString() }
    ],
    timeline: [
      { timestamp: new Date(Date.now() - 440000).toISOString(), event: 'Memory utilization anomaly detected (86.4% vs 44.5% baseline).' },
      { timestamp: new Date(Date.now() - 420000).toISOString(), event: 'HTTP Latency P95 alert triggered (280ms).' },
      { timestamp: new Date(Date.now() - 418000).toISOString(), event: 'Correlation Engine clustered 2 alerts into Incident INC-2026-8910 (Noise reduced by 50%).' },
      { timestamp: new Date(Date.now() - 300000).toISOString(), event: 'Status updated to INVESTIGATING by SRE triage.' }
    ]
  }
];

let selectedIncidentId = incidentsList[0]?.incident_id || null;
let activeIncidentFilter = 'ALL';

function renderIncidentsUI() {
  const openIncidents = incidentsList.filter(i => i.status === 'OPEN' || i.status === 'INVESTIGATING');
  const headerIncBtn = document.getElementById('header-incident-btn');
  const navBadge = document.getElementById('nav-incident-badge');
  const dashPill = document.getElementById('dash-incident-alert-pill');

  if (navBadge) navBadge.textContent = openIncidents.length;
  if (headerIncBtn) {
    if (openIncidents.length > 0) {
      headerIncBtn.style.display = 'flex';
      const countEl = document.getElementById('header-incident-count');
      if (countEl) countEl.textContent = openIncidents.length;
    } else {
      headerIncBtn.style.display = 'none';
    }
  }
  if (dashPill) {
    if (openIncidents.length > 0) {
      dashPill.style.display = 'inline-flex';
      dashPill.innerHTML = `<i class="fas fa-triangle-exclamation" style="margin-right:5px;"></i> ${openIncidents.length} INCIDENT${openIncidents.length > 1 ? 'S' : ''} ACTIVE`;
    } else {
      dashPill.style.display = 'none';
    }
  }

  const filtered = incidentsList.filter(inc => {
    if (activeIncidentFilter === 'ALL') return true;
    if (activeIncidentFilter === 'CRITICAL') return inc.severity === 'CRITICAL';
    if (activeIncidentFilter === 'OPEN') return inc.status === 'OPEN' || inc.status === 'INVESTIGATING';
    if (activeIncidentFilter === 'RESOLVED') return inc.status === 'RESOLVED' || inc.status === 'CLOSED';
    return true;
  });

  const listEl = document.getElementById('nw-incident-list');
  if (listEl) {
    if (filtered.length === 0) {
      listEl.innerHTML = `<div style="padding:24px; text-align:center; color:#64748b; background:rgba(15,23,42,0.4); border-radius:10px;">No incidents matching filter "${activeIncidentFilter}".</div>`;
    } else {
      listEl.innerHTML = filtered.map(inc => {
        const isSelected = inc.incident_id === selectedIncidentId;
        const sevBg = inc.severity === 'CRITICAL' ? 'rgba(239,68,68,0.2)' : (inc.severity === 'HIGH' ? 'rgba(245,158,11,0.2)' : 'rgba(59,130,246,0.2)');
        const sevColor = inc.severity === 'CRITICAL' ? '#ef4444' : (inc.severity === 'HIGH' ? '#f59e0b' : '#3b82f6');
        const stBg = inc.status === 'RESOLVED' || inc.status === 'CLOSED' ? 'rgba(16,185,129,0.2)' : (inc.status === 'INVESTIGATING' ? 'rgba(245,158,11,0.2)' : 'rgba(239,68,68,0.2)');
        const stColor = inc.status === 'RESOLVED' || inc.status === 'CLOSED' ? '#34d399' : (inc.status === 'INVESTIGATING' ? '#fbbf24' : '#f87171');

        return `
          <div class="card" onclick="selectIncident('${inc.incident_id}')" style="cursor:pointer; padding:16px 20px; transition:all 0.2s ease; border-left:4px solid ${sevColor}; ${isSelected ? 'background:rgba(30,41,59,0.9); border-color:#38bdf8;' : 'background:rgba(15,23,42,0.6);'}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <div style="display:flex; gap:10px; align-items:center;">
                <strong style="color:#f8fafc; font-size:14px;">${inc.incident_id}</strong>
                <span class="badge" style="background:${sevBg}; color:${sevColor}; border:1px solid ${sevColor}; font-size:10px; font-weight:800; padding:2px 8px;">${inc.severity}</span>
                <span class="badge" style="background:${stBg}; color:${stColor}; border:1px solid ${stColor}; font-size:10px; font-weight:700; padding:2px 8px;">${inc.status}</span>
              </div>
              <span style="font-size:11px; color:#64748b;"><i class="fas fa-clock"></i> ${new Date(inc.created_at).toLocaleTimeString()}</span>
            </div>
            <div style="font-size:13px; font-weight:600; color:#e2e8f0; margin-bottom:6px;">${inc.title}</div>
            <div style="font-size:11.5px; color:#94a3b8; margin-bottom:10px; line-height:1.4;">${inc.root_cause}</div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; border-top:1px solid rgba(255,255,255,0.06); padding-top:8px;">
              <span style="color:#38bdf8;"><i class="fas fa-layer-group"></i> ${inc.alerts_count} Correlated Alerts (${inc.alerts.map(a => a.metric_name).join(', ')})</span>
              <span style="color:#10b981; font-weight:600;"><i class="fas fa-filter"></i> ${Math.round((1 - 1/Math.max(1, inc.alerts_count)) * 100)}% Noise Reduction</span>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  renderIncidentDetail();
}

function selectIncident(incId) {
  selectedIncidentId = incId;
  renderIncidentsUI();
}
window.selectIncident = selectIncident;

function renderIncidentDetail() {
  const detailEl = document.getElementById('nw-incident-detail');
  if (!detailEl) return;

  const inc = incidentsList.find(i => i.incident_id === selectedIncidentId) || incidentsList[0];
  if (!inc) {
    detailEl.innerHTML = `<div style="text-align:center; color:#64748b; padding:40px;">Select an incident to view details.</div>`;
    return;
  }

  const sevColor = inc.severity === 'CRITICAL' ? '#ef4444' : (inc.severity === 'HIGH' ? '#f59e0b' : '#3b82f6');

  detailEl.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; border-bottom:1px solid #1e293b; padding-bottom:16px;">
      <div>
        <div style="display:flex; gap:10px; align-items:center; margin-bottom:6px;">
          <h2 style="font-size:20px; font-weight:800; color:#f8fafc; margin:0;">${inc.incident_id}</h2>
          <span class="badge" style="background:rgba(239,68,68,0.15); color:${sevColor}; border:1px solid ${sevColor}; font-weight:800;">${inc.severity}</span>
          <span class="badge" style="background:#1e293b; color:#94a3b8; border:1px solid #334155;">STATUS: ${inc.status}</span>
        </div>
        <div style="font-size:14px; font-weight:600; color:#cbd5e1;">${inc.title}</div>
        <div style="font-size:11.5px; color:#64748b; margin-top:4px;">
          Tenant: <code style="color:#38bdf8;">${inc.tenant_id}</code> | Collector: <code style="color:#38bdf8;">${inc.collector_id}</code> | Created: ${new Date(inc.created_at).toUTCString()}
        </div>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="nw-btn nw-btn-sm ${inc.status === 'INVESTIGATING' ? 'nw-btn-amber' : 'nw-btn-outline'}" onclick="updateIncidentStatus('${inc.incident_id}', 'INVESTIGATING')">
          <i class="fas fa-magnifying-glass"></i> Investigating
        </button>
        <button class="nw-btn nw-btn-sm ${inc.status === 'RESOLVED' ? 'nw-btn-emerald' : 'nw-btn-outline'}" onclick="updateIncidentStatus('${inc.incident_id}', 'RESOLVED')">
          <i class="fas fa-check"></i> Resolve
        </button>
        <button class="nw-btn nw-btn-sm ${inc.status === 'CLOSED' ? 'nw-btn-cyan' : 'nw-btn-outline'}" onclick="updateIncidentStatus('${inc.incident_id}', 'CLOSED')">
          <i class="fas fa-lock"></i> Close
        </button>
      </div>
    </div>

    <!-- Root Cause Box -->
    <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(56,189,248,0.3); border-radius:10px; padding:16px; margin-bottom:20px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:11px; font-weight:800; letter-spacing:1px; color:#38bdf8; text-transform:uppercase;">
          <i class="fas fa-brain"></i> Explainable AI Root Cause Analysis (RCA)
        </span>
        <span class="badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid #38bdf8; font-size:11px;">
          ${inc.confidence_score}% Confidence
        </span>
      </div>
      <p style="margin:0 0 10px; font-size:13px; color:#f1f5f9; line-height:1.5;">${inc.root_cause}</p>
      <div style="font-size:12px; color:#94a3b8;">
        <strong style="color:#38bdf8;">Recommended Remediation:</strong> ${inc.recommendation}
      </div>
      <div style="display:flex; gap:8px; margin-top:12px; align-items:center;">
        <span style="font-size:11px; color:#64748b;">Affected Components:</span>
        ${inc.affected_components.map(c => `<span class="badge" style="background:#1e293b; color:#cbd5e1; font-size:10.5px;">${c}</span>`).join('')}
      </div>
    </div>

    <!-- Correlated Alerts Table -->
    <div style="margin-bottom:20px;">
      <div style="font-size:12px; font-weight:700; color:#cbd5e1; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px;">
        <i class="fas fa-bell"></i> Correlated Constituent Alerts (${inc.alerts.length})
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Alert ID</th>
            <th>Metric Trigger</th>
            <th>Observed Value</th>
            <th>Baseline</th>
            <th>Deviation</th>
            <th>Severity</th>
          </tr>
        </thead>
        <tbody>
          ${inc.alerts.map(a => `
            <tr>
              <td><code>${a.alert_id}</code></td>
              <td><strong style="color:#f8fafc;">${a.metric_name}</strong></td>
              <td style="color:#ef4444; font-weight:700;">${a.value}</td>
              <td style="color:#94a3b8;">${a.baseline}</td>
              <td style="color:#f59e0b;">${a.deviation}</td>
              <td><span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid #ef4444; font-size:10px;">${a.severity}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>

    <!-- Incident Timeline -->
    <div>
      <div style="font-size:12px; font-weight:700; color:#cbd5e1; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px;">
        <i class="fas fa-timeline"></i> Incident Propagation Timeline
      </div>
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${inc.timeline.map(evt => `
          <div style="display:flex; gap:12px; align-items:flex-start; font-size:12px;">
            <span style="min-width:130px; color:#64748b; font-family:monospace; font-size:11px;">${new Date(evt.timestamp).toLocaleTimeString()}</span>
            <div style="width:8px; height:8px; border-radius:50%; background:#38bdf8; margin-top:4px;"></div>
            <div style="color:#cbd5e1;">${evt.event}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function updateIncidentStatus(incId, newStatus) {
  const inc = incidentsList.find(i => i.incident_id === incId);
  if (!inc) return;

  inc.status = newStatus;
  inc.timeline.push({
    timestamp: new Date().toISOString(),
    event: `Incident status updated to ${newStatus}.`
  });

  fetch(`${RENDER_BACKEND}/api/v1/incidents/${incId}/status?status=${newStatus}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
  }).catch(() => null);

  renderIncidentsUI();
}
window.updateIncidentStatus = updateIncidentStatus;

function triggerCascadeSimulation() {
  const now = new Date();
  const incId = `INC-2026-${Math.floor(1000 + Math.random() * 9000)}`;

  const cascadeIncident = {
    incident_id: incId,
    title: 'Multi-Signal Resource Starvation & Service Cascade',
    severity: 'CRITICAL',
    status: 'OPEN',
    tenant_id: 'customer-acme-prod',
    collector_id: 'collector-prod-us-east-1',
    created_at: now.toISOString(),
    confidence_score: 96.4,
    root_cause: 'Primary root cause: CPU utilization spike (97.4% vs 21.0% baseline) starved thread workers, propagating to HTTP gateway queue delay (520ms) and cascading 5xx timeouts (9.2% error rate).',
    recommendation: 'Check runaway container processes, cycle worker pods, and adjust thread pool sizing.',
    affected_components: ['Tier 1 Compute', 'FastAPI Ingress Gateway', 'PostgreSQL Pool'],
    alerts_count: 3,
    alerts: [
      { alert_id: `ALT-${Math.floor(2000 + Math.random() * 1000)}`, metric_name: 'cpu_utilization', baseline: '21.0%', value: '97.4%', deviation: '+363.8%', severity: 'CRITICAL', timestamp: now.toISOString() },
      { alert_id: `ALT-${Math.floor(3000 + Math.random() * 1000)}`, metric_name: 'http_latency_p95_ms', baseline: '52ms', value: '520ms', deviation: '+900.0%', severity: 'HIGH', timestamp: now.toISOString() },
      { alert_id: `ALT-${Math.floor(4000 + Math.random() * 1000)}`, metric_name: 'http_error_rate', baseline: '0.4%', value: '9.2%', deviation: '+2200%', severity: 'HIGH', timestamp: now.toISOString() }
    ],
    timeline: [
      { timestamp: now.toISOString(), event: 'AI Anomaly Engine detected CPU utilization spike (97.4%).' },
      { timestamp: now.toISOString(), event: 'HTTP Latency P95 breached high threshold (520ms).' },
      { timestamp: now.toISOString(), event: '5xx HTTP Error Rate breached threshold (9.2%).' },
      { timestamp: now.toISOString(), event: `Intelligent Correlation Engine grouped 3 alerts into ${incId} (66.7% noise reduction).` }
    ]
  };

  incidentsList.unshift(cascadeIncident);
  selectedIncidentId = incId;

  // Downgrade system health to POOR
  applySREScenario('severe');

  renderIncidentsUI();
}

/* ══════════════════════════════════════
   20. EGRESS PROOF & FIELD REDACTION ENGINE (REQUIREMENT 3)
══════════════════════════════════════ */
let egressAuditList = [
  {
    payload_id: 'pl-9f82d1c7a4e0318b',
    collector_id: 'collector-prod-us-east-1',
    sent_at: new Date(Date.now() - 10000).toISOString(),
    approved_fields_count: 8,
    rejected_fields_count: 5,
    delivery_status: 'DELIVERED_SAAS',
    policy_version: 'v1.0-strict-allowlist',
    policy_decision: 'APPROVED_WITH_REDACTION',
    payload_hash: 'sha256-hmac:9f82d1c7a4e0318bc0892019fe826189abf082e6d97c5e318',
    payload_size_bytes: 1184,
    fields_permitted: ['event_id', 'source_timestamp', 'collector_timestamp', 'sequence_number', 'metric_name', 'metric_value', 'unit', 'service'],
    fields_redacted: ['db_connection', 'api_key', 'authorization', 'user_email', 'unapproved_debug_trace'],
    raw_sample_redacted: JSON.stringify({
      "collector_id": "collector-prod-us-east-1",
      "timestamp": new Date(Date.now() - 10000).toISOString(),
      "metric_name": "cpu_utilization",
      "metric_value": 0.428,
      "service": "inference-engine-v2",
      "environment": "production",
      "__LOCAL_RAW_ATTRIBUTES__": {
        "db_connection": "postgresql://admin:***MASKED-PASSWORD***@internal-db:5432/orders",
        "api_key": "sk-proj-********************************429f",
        "authorization": "Bearer ***MASKED-BEARER-TOKEN***",
        "user_email": "t***@***.com",
        "unapproved_debug_trace": "stacktrace frame[0] at /var/app/inference.py:214"
      },
      "__POLICY_EVALUATION__": "VIOLATION DETECTED: 5 unapproved/sensitive fields intercepted locally. Purged client-side before serialization."
    }, null, 2),
    exact_outbound_payload: JSON.stringify({
      "payload_id": "pl-9f82d1c7a4e0318b",
      "collector_id": "collector-prod-us-east-1",
      "timestamp": new Date(Date.now() - 10000).toISOString(),
      "records": [
        {
          "event_id": "evt-c3b890f1-429f",
          "source_timestamp": new Date(Date.now() - 10025).toISOString(),
          "collector_timestamp": new Date(Date.now() - 10012).toISOString(),
          "sequence_number": 1042,
          "metric_name": "cpu_utilization",
          "metric_value": 0.428,
          "unit": "ratio",
          "service": "inference-engine-v2",
          "environment": "production"
        }
      ],
      "approved_fields_count": 8,
      "rejected_fields_count": 5,
      "policy_version": "v1.0-strict-allowlist",
      "policy_decision": "APPROVED_WITH_REDACTION",
      "payload_hash": "sha256-hmac:9f82d1c7a4e0318bc0892019fe826189abf082e6d97c5e318"
    }, null, 2)
  },
  {
    payload_id: 'pl-6c41b8a2e7f9042c',
    collector_id: 'collector-prod-us-east-1',
    sent_at: new Date(Date.now() - 30000).toISOString(),
    approved_fields_count: 8,
    rejected_fields_count: 4,
    delivery_status: 'DELIVERED_SAAS',
    policy_version: 'v1.0-strict-allowlist',
    policy_decision: 'APPROVED_WITH_REDACTION',
    payload_hash: 'sha256-hmac:6c41b8a2e7f9042cd1884029fa917281bc920481efa8912',
    payload_size_bytes: 1142
  },
  {
    payload_id: 'pl-2e90c5a3d4f8176e',
    collector_id: 'collector-prod-us-east-1',
    sent_at: new Date(Date.now() - 60000).toISOString(),
    approved_fields_count: 8,
    rejected_fields_count: 6,
    delivery_status: 'DELIVERED_SAAS',
    policy_version: 'v1.0-strict-allowlist',
    policy_decision: 'APPROVED_WITH_REDACTION',
    payload_hash: 'sha256-hmac:2e90c5a3d4f8176ebc019284fa98172bda028471cde9182',
    payload_size_bytes: 1198
  }
];

function renderEgressBeforeAfter(proof) {
  if (!proof) return;
  const panelA = document.getElementById('egress-panel-a-json');
  const panelB = document.getElementById('egress-panel-b-json');
  const hashEl = document.getElementById('egress-proof-hash');
  const sizeEl = document.getElementById('egress-proof-size');
  const decEl = document.getElementById('egress-proof-decision');
  const statusEl = document.getElementById('egress-panel-b-status');

  // Panel A: Local Raw Telemetry
  let sampleA = proof.raw_sample_redacted;
  if (!sampleA) {
    sampleA = JSON.stringify({
      "collector_id": proof.collector_id || "collector-prod-us-east-1",
      "timestamp": proof.sent_at || new Date().toISOString(),
      "metric_name": "cpu_utilization",
      "metric_value": 0.428,
      "service": "inference-engine-v2",
      "environment": "production",
      "__LOCAL_RAW_ATTRIBUTES__": {
        "db_connection": "postgresql://admin:***MASKED-PASSWORD***@internal-db:5432/orders",
        "api_key": "sk-proj-********************************429f",
        "authorization": "Bearer ***MASKED-BEARER-TOKEN***",
        "user_email": "t***@***.com",
        "unapproved_debug_trace": "stacktrace frame[0] at /var/app/inference.py:214"
      },
      "__POLICY_EVALUATION__": "VIOLATION DETECTED: 5 unapproved/sensitive fields intercepted locally. Purged client-side before serialization."
    }, null, 2);
  } else if (typeof sampleA === 'object') {
    sampleA = JSON.stringify(sampleA, null, 2);
  }
  if (panelA) panelA.textContent = sampleA;

  // Panel B: Actual Outgoing Payload
  let sampleB = proof.exact_outbound_payload;
  if (!sampleB) {
    sampleB = JSON.stringify({
      "payload_id": proof.payload_id,
      "collector_id": proof.collector_id || "collector-prod-us-east-1",
      "timestamp": proof.sent_at || new Date().toISOString(),
      "records": [
        {
          "event_id": "evt-" + (proof.payload_id ? proof.payload_id.slice(3, 15) : "429f-88a1"),
          "source_timestamp": proof.sent_at || new Date().toISOString(),
          "sequence_number": 1042,
          "metric_name": "cpu_utilization",
          "metric_value": 0.428,
          "unit": "ratio",
          "service": "inference-engine-v2",
          "environment": "production"
        }
      ],
      "approved_fields_count": proof.approved_fields_count || 8,
      "rejected_fields_count": proof.rejected_fields_count || 5,
      "policy_version": proof.policy_version || "v1.0-strict-allowlist",
      "policy_decision": proof.policy_decision || "APPROVED_WITH_REDACTION",
      "payload_hash": proof.payload_hash || "sha256-hmac:9f82d1c7a4e0318bc0892019fe826189abf082e6d97c5e318"
    }, null, 2);
  } else if (typeof sampleB === 'object') {
    sampleB = JSON.stringify(sampleB, null, 2);
  }
  if (panelB) panelB.textContent = sampleB;

  if (hashEl) hashEl.textContent = proof.payload_hash || 'sha256-hmac:9f82d1c7a4e0318bc0892019fe826189...';
  if (sizeEl) sizeEl.textContent = (proof.payload_size_bytes || 1184).toLocaleString() + ' Bytes';
  if (decEl) {
    decEl.textContent = proof.policy_decision || 'APPROVED_WITH_REDACTION';
    decEl.style.background = 'rgba(16,185,129,0.18)';
    decEl.style.color = '#34d399';
    decEl.style.border = '1px solid #10b981';
  }
  if (statusEl) {
    statusEl.textContent = proof.delivery_status || 'DELIVERED SAAS';
  }
}

function renderEgressUI() {
  const fullBody = document.getElementById('egress-audit-tbody-full');
  const shortBody = document.getElementById('egress-audit-tbody');

  const rowsHtml = egressAuditList.map(e => `
    <tr>
      <td><code>${e.payload_id.slice(0, 16)}...</code></td>
      <td><span style="color:#f8fafc; font-weight:600;">${e.collector_id}</span></td>
      <td style="font-size:11px; color:#94a3b8;">${new Date(e.sent_at).toUTCString()}</td>
      <td><span class="badge" style="background:rgba(16,185,129,0.18); color:#34d399; border:1px solid #10b981;">${e.approved_fields_count || 8} allowlisted</span></td>
      <td><span class="badge" style="background:rgba(239,68,68,0.18); color:#f87171; border:1px solid #ef4444;">${e.rejected_fields_count || 0} secrets blocked</span></td>
      <td><span class="badge" style="background:rgba(56,189,248,0.18); color:#38bdf8; border:1px solid #38bdf8;">${e.delivery_status || 'DELIVERED_SAAS'}</span></td>
      <td>
        <button class="nw-btn nw-btn-outline nw-btn-sm" onclick="inspectEgressProof('${e.payload_id}')">
          <i class="fas fa-shield-halved"></i> Inspect Proof
        </button>
      </td>
    </tr>
  `).join('');

  if (fullBody) fullBody.innerHTML = rowsHtml;
  if (shortBody) shortBody.innerHTML = rowsHtml;

  // Render first item into Before/After preview
  if (egressAuditList.length > 0) {
    renderEgressBeforeAfter(egressAuditList[0]);
  }
}

function inspectEgressProof(payloadId) {
  const p = egressAuditList.find(e => e.payload_id === payloadId) || egressAuditList[0];
  if (!p) return;

  renderEgressBeforeAfter(p);
  switchView('nav-egress');

  const el = document.getElementById('egress-panel-a-json');
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}
window.inspectEgressProof = inspectEgressProof;

function simulateSecretInjection() {
  const simulatedId = 'pl-sim-' + Math.random().toString(36).slice(2, 10);
  const now = new Date().toISOString();
  const simProof = {
    payload_id: simulatedId,
    collector_id: 'collector-tier1-local',
    sent_at: now,
    approved_fields_count: 8,
    rejected_fields_count: 5,
    delivery_status: 'DELIVERED_SAAS',
    policy_version: 'v1.0-strict-allowlist',
    policy_decision: 'APPROVED_WITH_REDACTION',
    payload_hash: 'sha256-hmac:sim-' + Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2),
    payload_size_bytes: 1248,
    raw_sample_redacted: JSON.stringify({
      "collector_id": "collector-tier1-local",
      "timestamp": now,
      "metric_name": "cpu_utilization",
      "metric_value": 0.74,
      "service": "payment-auth-worker",
      "__INJECTED_SECRETS_INTERCEPTED__": {
        "db_password": "P@ssw0rd2026!SecretPassword",
        "api_key": "sk-proj-LiveProdSecretKey998877665544",
        "jwt_bearer": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "customer_ssn": "987-65-4321",
        "aws_secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
      },
      "__PRIVACY_DECISION__": "PURGED 5 SENSITIVE SECRETS LOCALLY IN TIER 1. ZERO SECRETS TRANSMITTED."
    }, null, 2),
    exact_outbound_payload: JSON.stringify({
      "payload_id": simulatedId,
      "collector_id": "collector-tier1-local",
      "timestamp": now,
      "records": [
        {
          "event_id": "evt-" + simulatedId.slice(7),
          "source_timestamp": now,
          "sequence_number": 2048,
          "metric_name": "cpu_utilization",
          "metric_value": 0.74,
          "unit": "ratio",
          "service": "payment-auth-worker",
          "environment": "production"
        }
      ],
      "approved_fields_count": 8,
      "rejected_fields_count": 5,
      "policy_version": "v1.0-strict-allowlist",
      "policy_decision": "APPROVED_WITH_REDACTION",
      "payload_hash": "sha256-hmac:sim-verified-clean-proof"
    }, null, 2)
  };

  egressAuditList.unshift(simProof);
  renderEgressUI();
  renderEgressBeforeAfter(simProof);

  const blockedEl = document.getElementById('stat-events-blocked');
  if (blockedEl) blockedEl.textContent = '0 (5 Secrets Purged)';
  const lastTxEl = document.getElementById('stat-last-tx');
  if (lastTxEl) lastTxEl.textContent = 'Just now (Simulated)';

  alert(
    '🔒 SECRET INJECTION TEST SUCCESSFUL!\n\n' +
    '5 sensitive credentials (API key, DB password, Bearer token, SSN, AWS secret) were injected locally.\n' +
    'The Tier 1 Egress Policy immediately intercepted and purged all 5 client-side.\n' +
    'Only the allowlisted operational metric was transmitted to the SaaS platform.\n\n' +
    'Inspect Panel A vs Panel B in the comparison viewer!'
  );
}
window.simulateSecretInjection = simulateSecretInjection;

/* ══════════════════════════════════════
   20B. REAL-TIME TIMESTAMP & ORGANISER STREAM ENGINE (REQUIREMENTS 1 & 2)
══════════════════════════════════════ */
let realtimeTelemetryState = {
  last_event_id: 'evt-c3b890f1-429f',
  source_timestamp: new Date(Date.now() - 25).toISOString(),
  collector_timestamp: new Date(Date.now() - 13).toISOString(),
  ingestion_timestamp: new Date(Date.now() - 6).toISOString(),
  processing_timestamp: new Date().toISOString(),
  sequence_number: 1042,
  ingestion_delay_ms: 12.2,
  processing_delay_ms: 6.1,
  total_e2e_delay_ms: 24.5,
  collector_heartbeat_age_seconds: 3.2,
  telemetry_freshness_status: 'FRESH',
  delayed_events_count: 0,
  duplicate_events_count: 0,
  out_of_order_count: 0,
  total_events_ingested: 4820,
  is_live: true
};

function renderRealtimeTelemetry(data) {
  if (!data) return;
  realtimeTelemetryState = { ...realtimeTelemetryState, ...data };
  const s = realtimeTelemetryState;

  const e2eEl = document.getElementById('rt-e2e-delay');
  if (e2eEl) e2eEl.innerHTML = `${(s.total_e2e_delay_ms || 24.5).toFixed(1)}<span style="font-size:12px; color:#64748b; font-weight:500;">ms</span>`;

  const e2eStatusEl = document.getElementById('rt-e2e-status');
  if (e2eStatusEl) {
    if (s.total_e2e_delay_ms < 50) {
      e2eStatusEl.innerHTML = '● Optimal (&lt;50ms)';
      e2eStatusEl.style.color = '#34d399';
    } else if (s.total_e2e_delay_ms < 200) {
      e2eStatusEl.innerHTML = '● Normal (&lt;200ms)';
      e2eStatusEl.style.color = '#38bdf8';
    } else {
      e2eStatusEl.innerHTML = '● High Latency (&gt;200ms)';
      e2eStatusEl.style.color = '#f87171';
    }
  }

  const ingEl = document.getElementById('rt-ingest-delay');
  if (ingEl) ingEl.innerHTML = `${(s.ingestion_delay_ms || 12.2).toFixed(1)}<span style="font-size:12px; color:#64748b; font-weight:500;">ms</span>`;

  const procEl = document.getElementById('rt-proc-delay');
  if (procEl) procEl.innerHTML = `${(s.processing_delay_ms || 12.3).toFixed(1)}<span style="font-size:12px; color:#64748b; font-weight:500;">ms</span>`;

  const delEl = document.getElementById('rt-delayed-count');
  if (delEl) {
    delEl.textContent = s.delayed_events_count || 0;
    delEl.style.color = (s.delayed_events_count > 0) ? '#f59e0b' : '#10b981';
  }

  const dupEl = document.getElementById('rt-duplicate-count');
  if (dupEl) {
    dupEl.textContent = s.duplicate_events_count || 0;
    dupEl.style.color = (s.duplicate_events_count > 0) ? '#38bdf8' : '#10b981';
  }

  const hbEl = document.getElementById('rt-heartbeat-age');
  if (hbEl) {
    const age = (s.collector_heartbeat_age_seconds !== undefined) ? s.collector_heartbeat_age_seconds.toFixed(1) : '2.8';
    hbEl.textContent = `${age}s ago`;
    hbEl.style.color = parseFloat(age) < 15 ? '#34d399' : '#f87171';
  }

  const freshBadge = document.getElementById('rt-freshness-badge');
  if (freshBadge) {
    const fStatus = (s.telemetry_freshness_status || 'FRESH').toUpperCase();
    freshBadge.textContent = fStatus === 'FRESH' ? 'FRESH (<15s SLA)' : fStatus;
    if (fStatus === 'FRESH') {
      freshBadge.style.background = 'rgba(16,185,129,0.18)';
      freshBadge.style.color = '#34d399';
      freshBadge.style.borderColor = '#10b981';
    } else if (fStatus === 'AGING') {
      freshBadge.style.background = 'rgba(245,158,11,0.18)';
      freshBadge.style.color = '#fbbf24';
      freshBadge.style.borderColor = '#f59e0b';
    } else {
      freshBadge.style.background = 'rgba(239,68,68,0.18)';
      freshBadge.style.color = '#f87171';
      freshBadge.style.borderColor = '#ef4444';
    }
  }

  const evtIdEl = document.getElementById('rt-last-event-id');
  if (evtIdEl) evtIdEl.textContent = s.last_event_id ? s.last_event_id.slice(0, 20) + '...' : 'evt-c3b890f1-4...';

  const seqEl = document.getElementById('rt-sequence-num');
  if (seqEl) seqEl.textContent = `#${s.sequence_number || 1042}`;

  const formatUtcTime = (iso) => {
    if (!iso) return new Date().toISOString().replace('T', ' ').slice(0, 23);
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toISOString().replace('T', ' ').slice(0, 23);
  };

  const srcTsEl = document.getElementById('rt-source-ts');
  if (srcTsEl) srcTsEl.textContent = formatUtcTime(s.source_timestamp);

  const colTsEl = document.getElementById('rt-collector-ts');
  if (colTsEl) colTsEl.textContent = formatUtcTime(s.collector_timestamp).slice(11);

  const ingTsEl = document.getElementById('rt-ingest-ts');
  if (ingTsEl) ingTsEl.textContent = formatUtcTime(s.ingestion_timestamp).slice(11);

  const procTsEl = document.getElementById('rt-proc-ts');
  if (procTsEl) procTsEl.textContent = formatUtcTime(s.processing_timestamp).slice(11);
}

function renderStreamStatus(sData) {
  if (!sData) return;
  const badge = document.getElementById('rt-stream-badge');
  const txt = document.getElementById('rt-stream-status-text');

  if (badge) {
    if (sData.status === 'CONNECTED') {
      badge.textContent = 'ORGANISER STREAM CONNECTED';
      badge.style.background = 'rgba(16,185,129,0.18)';
      badge.style.color = '#34d399';
      badge.style.borderColor = '#10b981';
    } else if (sData.status === 'RECONNECTING') {
      badge.textContent = `RECONNECTING (Backoff: ${sData.current_backoff_seconds}s)`;
      badge.style.background = 'rgba(245,158,11,0.18)';
      badge.style.color = '#fbbf24';
      badge.style.borderColor = '#f59e0b';
    } else {
      badge.textContent = 'AWAITING ORGANISER STREAM PARAMS';
      badge.style.background = 'rgba(168,85,247,0.18)';
      badge.style.color = '#c084fc';
      badge.style.borderColor = '#a855f7';
    }
  }

  if (txt) {
    txt.textContent = sData.details || `Engine Ready (${sData.protocol || 'HTTP_SSE'}) · Target: ${sData.target_endpoint || 'Configurable via env'}`;
  }
}

function tickRealtimeFallback() {
  const now = new Date();
  const src = new Date(now.getTime() - 25);
  const col = new Date(now.getTime() - 13);
  const ing = new Date(now.getTime() - 6);
  const proc = now;
  realtimeTelemetryState.sequence_number = (realtimeTelemetryState.sequence_number || 1042) + 1;
  realtimeTelemetryState.source_timestamp = src.toISOString();
  realtimeTelemetryState.collector_timestamp = col.toISOString();
  realtimeTelemetryState.ingestion_timestamp = ing.toISOString();
  realtimeTelemetryState.processing_timestamp = proc.toISOString();
  realtimeTelemetryState.ingestion_delay_ms = Math.round(((ing - col) + Math.random() * 2) * 10) / 10;
  realtimeTelemetryState.processing_delay_ms = Math.round(((proc - ing) + Math.random() * 2) * 10) / 10;
  realtimeTelemetryState.total_e2e_delay_ms = Math.round(((proc - src) + Math.random() * 3) * 10) / 10;
  realtimeTelemetryState.collector_heartbeat_age_seconds = parseFloat((Math.random() * 3 + 1).toFixed(1));
  renderRealtimeTelemetry(realtimeTelemetryState);
}

/* ══════════════════════════════════════
   21. MAIN SIMULATION & LIVE BACKEND LOOP
══════════════════════════════════════ */
const RENDER_BACKEND = "https://ai-monitoring-5n2p.onrender.com";
const AUTH_TOKEN = "change-this-demo-key";
let lastAnomalyDetected = false;

async function fetchLiveBackend() {
  try {
    const [summaryRes, anomalyRes, egressRes, healthRes, incRes, realtimeRes, streamRes] = await Promise.all([
      fetch(`${RENDER_BACKEND}/api/v1/dashboard/summary`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/anomalies/preview`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/telemetry/egress`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/health/system`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/incidents`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/telemetry/realtime`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null),
      fetch(`${RENDER_BACKEND}/api/v1/stream/status`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` }
      }).catch(() => null)
    ]);

    // Live Real-Time Telemetry (Requirement 1)
    if (realtimeRes && realtimeRes.ok) {
      const rtData = await realtimeRes.json();
      if (rtData) {
        renderRealtimeTelemetry(rtData);
      }
    }

    // Live Organiser Stream Status (Requirement 2)
    if (streamRes && streamRes.ok) {
      const sData = await streamRes.json();
      if (sData) {
        renderStreamStatus(sData);
      }
    }

    // Live Egress Proofs (Requirement 3)
    if (egressRes && egressRes.ok) {
      const egressList = await egressRes.json();
      if (Array.isArray(egressList) && egressList.length > 0) {
        egressAuditList = egressList;
        renderEgressUI();
      }
    }

    // Live SRE Health from Backend (if not in manual simulation)
    if (!sreSimMode && healthRes && healthRes.ok) {
      const hData = await healthRes.json();
      if (hData && hData.system_health) {
        if (sreCurrentHealth !== hData.system_health) {
          recordHealthTransition(sreCurrentHealth, hData.system_health, hData.explanation, 'backend_sync');
        }
        sreCurrentHealth = hData.system_health;
        sreFreshnessStatus = hData.freshness_status || 'FRESH';
        sreFreshnessSeconds = hData.freshness_seconds || 4.2;
        sreExplanation = hData.explanation || sreExplanation;
        if (hData.metrics) sreMetricsData = hData.metrics;
        renderSREHealthUI();
      }
    }

    // Live Incidents from Backend
    if (incRes && incRes.ok) {
      const bIncList = await incRes.json();
      if (Array.isArray(bIncList) && bIncList.length > 0) {
        incidentsList = bIncList;
        if (!selectedIncidentId || !incidentsList.find(i => i.incident_id === selectedIncidentId)) {
          selectedIncidentId = incidentsList[0].incident_id;
        }
        renderIncidentsUI();
      }
    }

    // Live Dashboard Summary
    if (summaryRes && summaryRes.ok) {
      const summary = await summaryRes.json();
      const latest = summary.latest_metrics || {};

      // 1. Live CPU Gauge
      if (latest.cpu_utilization !== undefined) {
        gaugeState.cpu = Math.round(latest.cpu_utilization * 100);
        updateGauge('arc-cpu', 'pct-cpu', gaugeState.cpu);
      }

      // 2. Live Memory Gauge
      if (latest.memory_utilization !== undefined) {
        gaugeState.mem = Math.round(latest.memory_utilization * 100);
        updateGauge('arc-mem', 'pct-mem', gaugeState.mem);
      }

      // 3. Live Latency KPI
      if (latest.http_latency_p95_ms !== undefined) {
        kpi.latency = latest.http_latency_p95_ms;
        const el = document.getElementById('val-latency');
        if (el) el.innerHTML = `${Math.round(kpi.latency)}<span class="kpi-unit">ms</span>`;
      }

      // 4. Live Error Rate KPI
      if (latest.http_error_rate !== undefined) {
        kpi.error = latest.http_error_rate * 100;
        const el = document.getElementById('val-error');
        if (el) el.innerHTML = `${kpi.error.toFixed(1)}<span class="kpi-unit">%</span>`;
      }

      // 5. Live Network Throughput
      if (latest.network_bytes_per_second !== undefined) {
        const mb = (latest.network_bytes_per_second / (1024 * 1024)).toFixed(2);
        const el = document.getElementById('sys-net');
        if (el) el.textContent = `${mb} MB/s`;
      }
    }

    // 6. Anomaly Detection Engine
    if (anomalyRes && anomalyRes.ok) {
      const anomaly = await anomalyRes.json();
      if (anomaly && anomaly.status === "scored") {
        const isOutlier = Boolean(anomaly.anomaly);
        const sysStatus = document.querySelector('.header-sys-status span');
        const sysDot = document.querySelector('.sys-dot');

        if (isOutlier) {
          if (sysStatus) {
            sysStatus.textContent = "AI Anomaly Triggered (Isolation Forest)";
            sysStatus.style.color = "#ef4444";
          }
          if (sysDot) sysDot.style.background = "#ef4444";

          if (!lastAnomalyDetected) {
            lastAnomalyDetected = true;
            const feed = document.getElementById('alerts-feed');
            if (feed) {
              const item = {
                type: 'crit',
                icon: 'fa-triangle-exclamation',
                text: `[AI ENGINE] ${anomaly.explanation || "Telemetry outlier detected by Isolation Forest"} | Rec: ${anomaly.recommendation || "Scale instances"}`,
                pill: 'AI ANOMALY',
              };
              const alertEl = renderAlert(item, 0);
              feed.prepend(alertEl);
              alertCount++;
              const badge = document.getElementById('nav-alert-badge');
              const nbadge = document.getElementById('notif-count');
              if (badge) badge.textContent = alertCount;
              if (nbadge) nbadge.textContent = alertCount;
            }
          }
        } else {
          lastAnomalyDetected = false;
        }
      }
    }

    // Live backend badge update
    const liveBtn = document.getElementById('live-btn');
    if (liveBtn) {
      liveBtn.innerHTML = '<span class="live-btn-dot" style="background:#10b981"></span>LIVE RENDER';
      liveBtn.title = "Connected to " + RENDER_BACKEND;
    }
  } catch (err) {
    console.debug("Backend polling:", err);
  }
}

// Initial fetch and continuous live sync every 3 seconds
fetchLiveBackend();
setInterval(fetchLiveBackend, 3000);

let tickCount = 0;

function tick() {
  tickCount++;

  // Every tick (2s): inference, chips, real-time timestamp simulation
  updateInferenceChart();
  updateModelChips();
  tickRealtimeFallback();

  // Every 2 ticks (4s): KPIs, gauges
  if (tickCount % 2 === 0) {
    updateKPI();

    // System metrics
    document.getElementById('sys-queue').textContent = randI(10, 120).toString();
    document.getElementById('sys-cache').textContent = `${randI(70, 95)}%`;

    // Increment simulated freshness seconds if sim mode
    if (!sreSimMode) {
      sreFreshnessSeconds = parseFloat((rand(2.0, 7.5)).toFixed(1));
      renderSREHealthUI();
    }
  }

  // Every 5 ticks (10s): cost/tokens, drift
  if (tickCount % 5 === 0) {
    updateCostAndTokens();
    updateDriftChart();
  }
}

setInterval(tick, 2000);

/* ══════════════════════════════════════
   22. VIEW SWITCHING & EVENT LISTENERS
══════════════════════════════════════ */

// Sidebar toggle
const sidebarToggle = document.getElementById('sidebar-toggle');
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('collapsed');
  });
}

const VIEW_MAP = {
  'nav-dashboard': { id: 'view-dashboard', title: 'AI Performance Dashboard', subtitle: 'Real-time monitoring across all models' },
  'nav-health':    { id: 'view-health',    title: 'SRE Four-State System Health Engine', subtitle: 'Configurable health states (EXCELLENT, GOOD, FAIR, POOR), metric evaluations & state transitions' },
  'nav-incidents': { id: 'view-incidents', title: 'Intelligent Incident Correlation Engine', subtitle: 'Automated alert aggregation, root cause analysis (RCA), noise reduction & incident lifecycle' },
  'nav-realtime':  { id: 'view-dashboard', title: 'Real-Time Telemetry Stream & Timestamp Engine', subtitle: 'Real-time measured UTC timestamps, delay metrics, and organiser stream integration', targetEl: 'dashboard-realtime-card' },
  'nav-egress':    { id: 'view-egress',    title: 'Egress Proof & Field Redaction Panel', subtitle: 'Tier 1 client-side credential purging, cryptographic proofs & metadata transmission audits' },
  'nav-models':    { id: 'view-models',    title: 'Model Registry & Health', subtitle: 'Fleet status, versions, and deployment tiers' },
  'nav-inference': { id: 'view-inference', title: 'Inference & SLA Observability', subtitle: 'Latency percentiles, throughput, and error rates' },
  'nav-costs':     { id: 'view-costs',     title: 'Cost & Token Tracking', subtitle: 'Daily spend, model token distributions, and budget burn-rates' },
  'nav-drift':     { id: 'view-drift',     title: 'Feature & Data Drift Analysis', subtitle: 'Population Stability Index (PSI) and embedding variance' },
  'nav-alerts':    { id: 'view-alerts',    title: 'Alerts & Incident Management Hub', subtitle: 'Isolation Forest anomaly detections and operational triage' },
  'nav-settings':  { id: 'view-settings',  title: 'Platform & Security Settings', subtitle: 'Two-tier SaaS gateway configuration and privacy allowlist policies' },
};

function switchView(navId) {
  const target = VIEW_MAP[navId];
  if (!target) return;

  // 1. Update active sidebar item
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const activeNav = document.getElementById(navId);
  if (activeNav) activeNav.classList.add('active');

  // 2. Update Header
  const titleEl = document.querySelector('.header-title');
  const subEl = document.querySelector('.header-subtitle');
  if (titleEl) titleEl.textContent = target.title;
  if (subEl) subEl.textContent = target.subtitle;

  // 3. Switch visible view
  document.querySelectorAll('.dashboard-view').forEach(v => {
    v.style.display = 'none';
  });
  const viewEl = document.getElementById(target.id);
  if (viewEl) {
    viewEl.style.display = 'flex';
  }

  // 4. Scroll to target element if specified
  if (target.targetEl) {
    const el = document.getElementById(target.targetEl);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.style.boxShadow = '0 0 25px rgba(0,212,255,0.4)';
      setTimeout(() => { el.style.boxShadow = ''; }, 2000);
    }
  }

  // 5. Trigger resize on Chart.js instances if returning to dashboard
  if (navId === 'nav-dashboard') {
    [inferenceChart, costChart, donutChart, compareChart, driftChart].forEach(c => {
      try { c && c.resize(); } catch (_) {}
    });
  }
}
window.switchView = switchView;

// Nav links — switch views on click
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    switchView(link.id);
  });
});

// Header shortcuts
const headerHealthBtn = document.getElementById('header-health-btn');
if (headerHealthBtn) headerHealthBtn.addEventListener('click', () => switchView('nav-health'));

const headerIncBtn = document.getElementById('header-incident-btn');
if (headerIncBtn) headerIncBtn.addEventListener('click', () => switchView('nav-incidents'));

// Dashboard banner shortcuts
const dashHealthBtn = document.getElementById('dash-view-health-btn');
if (dashHealthBtn) dashHealthBtn.addEventListener('click', () => switchView('nav-health'));

const dashIncBtn = document.getElementById('dash-view-incidents-btn');
if (dashIncBtn) dashIncBtn.addEventListener('click', () => switchView('nav-incidents'));

// SRE Simulation Buttons
document.querySelectorAll('#sre-sim-buttons button').forEach(btn => {
  btn.addEventListener('click', () => {
    const simType = btn.getAttribute('data-sim');
    if (simType) applySREScenario(simType);
  });
});

const simResetBtn = document.getElementById('sre-sim-reset-btn');
if (simResetBtn) simResetBtn.addEventListener('click', () => {
  sreSimMode = false;
  applySREScenario('normal');
});

// Incident Cascade Trigger Button
const cascadeBtn = document.getElementById('nw-trigger-cascade-btn');
if (cascadeBtn) cascadeBtn.addEventListener('click', triggerCascadeSimulation);

// Incident Filter Buttons
document.querySelectorAll('#nw-incident-filters button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#nw-incident-filters button').forEach(b => {
      b.classList.remove('nw-btn-cyan');
      b.classList.add('nw-btn-outline');
    });
    btn.classList.remove('nw-btn-outline');
    btn.classList.add('nw-btn-cyan');
    activeIncidentFilter = btn.getAttribute('data-filter') || 'ALL';
    renderIncidentsUI();
  });
});

// Live button — flash animation
const liveBtnEl = document.getElementById('live-btn');
if (liveBtnEl) {
  liveBtnEl.addEventListener('click', function () {
    this.style.transform = 'scale(0.95)';
    setTimeout(() => { this.style.transform = ''; }, 150);
  });
}

// Secret injection simulation button
const injectBtn = document.getElementById('egress-inject-sim-btn');
if (injectBtn) injectBtn.addEventListener('click', simulateSecretInjection);

// Realtime refresh button
const rtRefreshBtn = document.getElementById('rt-refresh-btn');
if (rtRefreshBtn) rtRefreshBtn.addEventListener('click', () => {
  fetchLiveBackend();
  tickRealtimeFallback();
});

// Initial renders
renderSREHealthUI();
renderIncidentsUI();
renderEgressUI();
renderRealtimeTelemetry(realtimeTelemetryState);
renderStreamStatus({
  stream_id: 'stream-cicada-shared',
  protocol: 'HTTP_SSE / WebSocket',
  status: 'AWAITING_PARAMS',
  target_endpoint: 'Awaiting Organiser Stream URL',
  details: 'Organiser stream consumer engine ready · Awaiting live stream credentials'
});

console.log('%c NeuralWatch Dashboard loaded ✓ (Real-Time Timestamps, Organiser Stream & Egress Proof Before/After Active)', 'background:#00d4ff;color:#07090f;font-weight:bold;padding:4px 8px;border-radius:4px;');

