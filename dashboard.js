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
   18.  MAIN SIMULATION LOOP
══════════════════════════════════════ */
let tickCount = 0;

function tick() {
  tickCount++;

  // Every tick (2s): inference, chips
  updateInferenceChart();
  updateModelChips();

  // Every 2 ticks (4s): KPIs, gauges
  if (tickCount % 2 === 0) {
    updateKPI();

    gaugeState.cpu = driftGauge(gaugeState.cpu, 10, 95, 4);
    gaugeState.gpu = driftGauge(gaugeState.gpu, 40, 98, 5);
    gaugeState.mem = driftGauge(gaugeState.mem, 30, 90, 3);
    updateGauge('arc-cpu', 'pct-cpu', gaugeState.cpu);
    updateGauge('arc-gpu', 'pct-gpu', gaugeState.gpu);
    updateGauge('arc-mem', 'pct-mem', gaugeState.mem);

    // System metrics
    document.getElementById('sys-net').textContent   = `${rand(0.4, 2.8).toFixed(1)} GB/s`;
    document.getElementById('sys-queue').textContent = randI(10, 120).toString();
    document.getElementById('sys-cache').textContent = `${randI(70, 95)}%`;
  }

  // Every 5 ticks (10s): cost/tokens, drift
  if (tickCount % 5 === 0) {
    updateCostAndTokens();
    updateDriftChart();
  }

  // Random alert (10% chance each tick)
  if (Math.random() < 0.08) {
    pushAlert();
  }
}

setInterval(tick, 2000);

/* ══════════════════════════════════════
   19.  EVENT LISTENERS
══════════════════════════════════════ */

// Sidebar toggle
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('collapsed');
});

// Nav links — highlight active
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
  });
});

// Live button — flash animation
document.getElementById('live-btn').addEventListener('click', function () {
  this.style.transform = 'scale(0.95)';
  setTimeout(() => { this.style.transform = ''; }, 150);
});

console.log('%c NeuralWatch Dashboard loaded ✓ ', 'background:#00d4ff;color:#07090f;font-weight:bold;padding:4px 8px;border-radius:4px;');
