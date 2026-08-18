const ui = {};
let runState = null;
let taskDetail = null;
let selectedTask = null;
let activeFilter = "all";
let activeTab = "activity";
let polling = false;
let experiments = [];
let selectedRun = null;
let comparisonData = null;
let comparisonSignature = null;
let comparisonPolling = false;
let lastComparisonFetch = 0;
let windowRestoreGeneration = 0;
let stateSignature = null;
let detailSignature = null;

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function preserveWindowScroll(render) {
  const left = window.scrollX;
  const top = window.scrollY;
  const generation = ++windowRestoreGeneration;
  render();
  if (Math.abs(window.scrollX - left) > 1 || Math.abs(window.scrollY - top) > 1) {
    window.scrollTo(left, top);
  }
  requestAnimationFrame(() => {
    if (generation === windowRestoreGeneration
        && (Math.abs(window.scrollX - left) > 1 || Math.abs(window.scrollY - top) > 1)) {
      window.scrollTo(left, top);
    }
  });
}

function setScrollableText(panel, value) {
  if (panel.textContent === value) return;
  const top = panel.scrollTop;
  const left = panel.scrollLeft;
  panel.textContent = value;
  panel.scrollTop = top;
  panel.scrollLeft = left;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes) return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  return `${secs}s`;
}

function formatTokens(value) {
  const number = Number(value || 0);
  if (number >= 1000) return `${(number / 1000).toFixed(number >= 10000 ? 1 : 2)}k`;
  return number.toLocaleString();
}

function formatCost(value) {
  return typeof value === "number" ? `$${value.toFixed(3)}` : "—";
}

function timeLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
}

function statusLabel(status) {
  return ({
    active: "Running",
    verified: "Compiled",
    failed: "Compile failed",
    interrupted: "Interrupted",
    queued: "Queued",
    semantic_success: "Semantic pass",
    compiled_no_semantic_pass: "No semantic pass",
    compile_failed: "Compile failed",
    missing: "Missing output",
  })[status] || status;
}

function renderOverview() {
  const summary = runState.summary;
  const run = runState.run;
  const complete = summary.verified + summary.failed;
  const percent = summary.total ? (complete / summary.total) * 100 : 0;
  byId("run-status").textContent = run.status || "unknown";
  byId("run-subtitle").textContent = run.runner_pid ? `Runner PID ${run.runner_pid}` : "No active runner PID";
  byId("progress-count").textContent = `${complete} / ${summary.total}`;
  byId("progress-bar").style.width = `${percent}%`;
  byId("verified-count").textContent = summary.verified;
  const semanticCopy = Number.isInteger(summary.semantic_success)
    ? ` · ${summary.semantic_success} semantic passes`
    : "";
  const interruptedCopy = summary.interrupted ? ` · ${summary.interrupted} interrupted` : "";
  byId("failed-count").textContent = `${summary.failed} compile failures${semanticCopy}${interruptedCopy}`;
  byId("cost-total").textContent = `$${Number(summary.known_cost_usd || 0).toFixed(2)}`;
  byId("task-total").textContent = summary.total;
  byId("model-label").textContent = [run.model || "Claude Code", run.effort].filter(Boolean).join(" · ");
  byId("interruption-banner").classList.toggle("hidden", !["interrupted", "stopped"].includes(run.status) || summary.interrupted === 0);
}

function taskMatches(task) {
  if (activeFilter === "all") return true;
  if (activeFilter === "active") return task.status === "active";
  return task.outcome_state === activeFilter;
}

function renderTaskList() {
  const tasks = runState.tasks.filter(taskMatches);
  const panel = byId("task-list");
  const panelTop = panel.scrollTop;
  const signature = JSON.stringify({
    filter: activeFilter,
    selected: selectedTask,
    tasks: tasks.map((task) => [task.name, task.status, task.outcome_state, task.stage, task.duration_seconds]),
  });
  if (panel.dataset.renderSignature === signature) return;
  preserveWindowScroll(() => {
    panel.innerHTML = tasks.length ? tasks.map((task) => `
      <button class="task-button ${task.name === selectedTask ? "selected" : ""}" data-task="${escapeHtml(task.name)}">
        <span class="status-dot ${escapeHtml(task.outcome_state || task.status)}"></span>
        <span class="task-copy"><strong>${escapeHtml(task.name)}</strong><small>${escapeHtml(task.stage)}</small></span>
        <span class="task-meta">${escapeHtml(formatDuration(task.duration_seconds))}</span>
      </button>`).join("") : `<p class="empty-state">No cases match this filter.</p>`;
    panel.dataset.renderSignature = signature;
    panel.scrollTop = panelTop;
  });
  document.querySelectorAll(".task-button").forEach((button) => button.addEventListener("click", () => {
    selectedTask = button.dataset.task;
    taskDetail = null;
    renderTaskList();
    fetchDetail();
  }));
}

function renderStages(summary) {
  const hasAgent = summary.status !== "queued";
  const hasLean = summary.check_attempts > 0;
  const saved = ["verified", "failed"].includes(summary.status);
  const current = saved ? 4 : hasLean ? 3 : hasAgent ? 2 : 1;
  const stages = [...document.querySelectorAll(".stage")];
  const lines = [...document.querySelectorAll(".stage-line")];
  byId("stage-rail").dataset.outcome = summary.outcome_state || summary.status;
  stages.forEach((stage, index) => {
    stage.classList.toggle("complete", index + 1 < current || saved);
    stage.classList.toggle("current", index + 1 === current && !saved);
  });
  lines.forEach((line, index) => line.classList.toggle("complete", index + 1 < current || saved));
}

function renderDiff(diff) {
  const panel = byId("diff-content");
  const code = taskDetail?.code || taskDetail?.experiment?.code || "";
  const signature = diff ? `diff:${diff}` : `code:${code}`;
  if (panel.dataset.renderSignature === signature) return;
  const panelTop = panel.scrollTop;
  const panelLeft = panel.scrollLeft;
  if (!diff) {
    panel.textContent = code || "No code or edits recorded.";
    panel.dataset.renderSignature = signature;
    panel.scrollTop = panelTop;
    panel.scrollLeft = panelLeft;
    return;
  }
  panel.innerHTML = diff.split("\n").map((line) => {
    let className = "";
    if (line.startsWith("+") && !line.startsWith("+++")) className = "diff-add";
    if (line.startsWith("-") && !line.startsWith("---")) className = "diff-del";
    if (line.startsWith("@@")) className = "diff-hunk";
    return `<span class="${className}">${escapeHtml(line)}</span>`;
  }).join("");
  panel.dataset.renderSignature = signature;
  panel.scrollTop = panelTop;
  panel.scrollLeft = panelLeft;
}

function renderTimeline(timeline) {
  const panel = byId("timeline");
  const signature = JSON.stringify(timeline);
  if (panel.dataset.renderSignature === signature) return;
  const panelTop = panel.scrollTop;
  if (!timeline.length) {
    panel.innerHTML = `<p class="empty-state">Waiting for agent events…</p>`;
    panel.dataset.renderSignature = signature;
    panel.scrollTop = panelTop;
    return;
  }
  panel.innerHTML = timeline.map((item) => {
    const stateClass = item.status === "error" ? "error" : item.status === "failed" ? "failed" : item.status === "verified" ? "verified" : "";
    return `<article class="timeline-item ${escapeHtml(item.kind)} ${stateClass}">
      <span class="timeline-marker"></span>
      <div class="timeline-head"><strong>${escapeHtml(item.title)}</strong><time>${escapeHtml(timeLabel(item.timestamp))}</time></div>
      ${item.body ? `<div class="timeline-body">${escapeHtml(item.body)}</div>` : ""}
      ${item.output ? `<pre class="tool-output">${escapeHtml(item.output)}</pre>` : ""}
    </article>`;
  }).join("");
  panel.dataset.renderSignature = signature;
  if (byId("auto-follow").checked) panel.scrollTop = panel.scrollHeight;
  else panel.scrollTop = panelTop;
}

function renderDetail() {
  if (!taskDetail) return;
  preserveWindowScroll(() => {
    const summary = taskDetail.summary;
    const displayedStatus = summary.outcome_state || summary.status;
    byId("task-name").textContent = summary.name;
    byId("task-stage").textContent = summary.stage;
    byId("task-status-dot").className = `status-dot ${displayedStatus}`;
    byId("task-badge").className = `status-badge ${displayedStatus}`;
    byId("task-badge").textContent = statusLabel(displayedStatus);
    byId("task-duration").textContent = formatDuration(summary.duration_seconds);
    byId("task-turns").textContent = summary.turns ?? "—";
    byId("task-loc-added").textContent = Number.isInteger(summary.loc_added) ? `+${summary.loc_added}` : "—";
    byId("task-cost").textContent = formatCost(summary.cost_usd);
    byId("thinking-count").textContent = formatTokens(summary.thinking_tokens);
    byId("check-count").textContent = summary.check_attempts;
    byId("denied-count").textContent = summary.denied_tools;
    byId("event-count").textContent = taskDetail.event_count;
    const showThinking = summary.status === "active" && summary.thinking_tokens > 0;
    byId("thinking-strip").classList.toggle("hidden", !showThinking);
    byId("thinking-copy").textContent = `Approximately ${Number(summary.thinking_tokens).toLocaleString()} thinking tokens observed`;
    renderStages(summary);
    renderTimeline(taskDetail.timeline || []);
    renderDiff(taskDetail.diff || "");
    const semantic = taskDetail.experiment?.semantic_analysis;
    const verifier = taskDetail.result?.feedback || taskDetail.experiment?.verifier_feedback;
    const robust = taskDetail.robust_artifacts || {};
    const robustSections = [
      robust.diagnostics && `Source-mapped diagnostics:\n${robust.diagnostics}`,
      robust.leansearch_queries?.length && `LeanSearch queries:\n${JSON.stringify(robust.leansearch_queries, null, 2)}`,
    ].filter(Boolean);
    setScrollableText(
      byId("feedback-content"),
      [semantic && `Semantic judge:\n${semantic}`, verifier && `Verifier:\n${verifier}`, ...robustSections].filter(Boolean).join("\n\n") || "No saved verifier feedback.",
    );
    setScrollableText(byId("stderr-content"), taskDetail.stderr || "No stderr output.");
    setScrollableText(
      byId("algorithm-plan-content"),
      robust.algorithm_plan || "AlgorithmPlan.md is not available for this run.",
    );
    setScrollableText(
      byId("proof-state-content"),
      robust.proof_state || "ProofState.md is not available for this run.",
    );
  });
}

async function fetchDetail() {
  if (!selectedTask) return;
  try {
    const response = await fetch(`/api/task?run=${encodeURIComponent(selectedRun || "")}&name=${encodeURIComponent(selectedTask)}`, {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const nextDetail = await response.json();
    const nextSignature = `${selectedRun}:${selectedTask}:${JSON.stringify(nextDetail)}`;
    if (nextSignature === detailSignature) return;
    taskDetail = nextDetail;
    detailSignature = nextSignature;
    renderDetail();
  } catch (error) {
    console.error("Could not load task detail", error);
  }
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const response = await fetch(`/api/state?run=${encodeURIComponent(selectedRun || "")}`, {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const nextState = await response.json();
    const stableState = {...nextState, generated_at: null};
    const nextStateSignature = JSON.stringify(stableState);
    const stateChanged = nextStateSignature !== stateSignature;
    runState = nextState;
    stateSignature = nextStateSignature;
    byId("connection-dot").className = "connection-dot online";
    byId("connection-label").textContent = "Live";
    if (!selectedTask || !runState.tasks.some((task) => task.name === selectedTask)) {
      selectedTask = runState.tasks.find((task) => task.status === "active")?.name
        || runState.tasks.find((task) => task.status === "interrupted")?.name
        || runState.tasks[0]?.name || null;
    }
    if (stateChanged) {
      renderOverview();
      renderTaskList();
    }
    await fetchDetail();
    byId("last-refresh").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    byId("connection-dot").className = "connection-dot offline";
    byId("connection-label").textContent = "Disconnected";
    console.error("Dashboard poll failed", error);
  } finally {
    polling = false;
  }
}

document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
  activeFilter = button.dataset.filter;
  document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button));
  renderTaskList();
}));

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  activeTab = button.dataset.tab;
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".tab-view").forEach((view) => view.classList.toggle("active", view.id === `${activeTab}-view`));
}));

function selectedExperimentIds() {
  return [...document.querySelectorAll(".model-toggle input:checked")].map((input) => input.value);
}

function curveAt(experiment, tryNumber) {
  return experiment.try_curve.find((point) => point.try === tryNumber) || experiment.try_curve.at(-1) || {successes: 0, rate: 0};
}

function renderComparisonBars(tryNumber) {
  const rows = comparisonData.experiments.map((experiment) => {
    const point = curveAt(experiment, tryNumber);
    const semantic = experiment.semantic_evaluated
      ? `${(experiment.semantic_rate * 100).toFixed(1)}%`
      : "not evaluated";
    return `<div class="bar-row"><div class="bar-label"><strong>${escapeHtml(experiment.label)}</strong><span>${point.successes}/${experiment.total} · ${(point.rate * 100).toFixed(1)}%</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${point.rate * 100}%;background:${escapeHtml(experiment.color)}"></div></div>
      <div class="bar-secondary"><span>Final compile <b>${(experiment.compile_rate * 100).toFixed(1)}%</b></span><span>Semantic <b>${semantic}</b></span><span>Missing <b>${experiment.missing}</b></span></div></div>`;
  });
  byId("comparison-bars").innerHTML = rows.join("");
  byId("bars-title").textContent = `Compilation success by try ${tryNumber}`;
}

function renderTryChart() {
  const svg = byId("try-chart");
  const width = 900, height = 300, left = 52, right = 18, top = 15, bottom = 35;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const maxTry = Math.max(1, ...comparisonData.experiments.map((item) => item.max_tries));
  let content = "";
  [0, .25, .5, .75, 1].forEach((rate) => {
    const y = top + plotHeight * (1 - rate);
    content += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}"></line><text class="chart-axis-label" x="${left-9}" y="${y+3}" text-anchor="end">${rate*100}%</text>`;
  });
  [1, 3, 5, 7, 9, 11, 13, 15].filter((value) => value <= maxTry).forEach((value) => {
    const x = left + ((value - 1) / Math.max(1, maxTry - 1)) * plotWidth;
    content += `<text class="chart-axis-label" x="${x}" y="${height-10}" text-anchor="middle">${value}</text>`;
  });
  comparisonData.experiments.forEach((experiment) => {
    const points = experiment.try_curve.map((point) => {
      const x = left + ((point.try - 1) / Math.max(1, maxTry - 1)) * plotWidth;
      const y = top + (1 - point.rate) * plotHeight;
      return `${x},${y}`;
    });
    content += `<polyline class="chart-line" stroke="${escapeHtml(experiment.color)}" points="${points.join(" ")}"></polyline>`;
  });
  content += `<text class="chart-axis-label" x="${left + plotWidth/2}" y="${height-1}" text-anchor="middle">Repair / Lean-check try</text>`;
  svg.innerHTML = content;
}

function renderComparisonTable(tryNumber) {
  byId("try-column").textContent = `Compile by try ${tryNumber}`;
  byId("comparison-table").innerHTML = comparisonData.experiments.map((experiment) => {
    const point = curveAt(experiment, tryNumber);
    const semanticText = experiment.semantic_evaluated
      ? `<span class="rate-value">${experiment.semantic_success}/${experiment.total}</span><span class="rate-sub">${(experiment.semantic_rate*100).toFixed(1)}%</span>`
      : "Not evaluated";
    const locText = experiment.loc_coverage
      ? `<span class="rate-value">+${experiment.loc_added}</span><span class="rate-sub">${experiment.average_loc_added.toFixed(1)} avg</span>`
      : "—";
    return `<tr><td><strong>${escapeHtml(experiment.label)}</strong><br><span class="rate-sub">${escapeHtml(experiment.condition)}</span></td><td>${experiment.total}</td><td>${experiment.outputs}/${experiment.total}</td><td><span class="rate-value">${point.successes}</span><span class="rate-sub">${(point.rate*100).toFixed(1)}%</span></td><td><span class="rate-value">${experiment.compile_success}</span><span class="rate-sub">${(experiment.compile_rate*100).toFixed(1)}%</span></td><td>${semanticText}</td><td>${experiment.semantic_evaluated}/${experiment.total}</td><td>${locText}</td></tr>`;
  }).join("");
}

function renderMatrix() {
  const ids = comparisonData.experiments.map((item) => item.id);
  byId("matrix-head").innerHTML = `<tr><th>Case</th>${comparisonData.experiments.map((item) => `<th title="${escapeHtml(item.condition)}">${escapeHtml(item.label)}</th>`).join("")}</tr>`;
  byId("matrix-body").innerHTML = comparisonData.matrix.map((row) => `<tr><td>${escapeHtml(row.task)}</td>${ids.map((id) => {
    const value = row.models[id] || {state: "missing", out_of_scope: true};
    const tryCopy = value.success_try ? ` · try ${value.success_try}` : "";
    const locCopy = Number.isInteger(value.loc_added) ? ` · +${value.loc_added} LOC` : "";
    const sourceCopy = value.source_label ? ` · source: ${value.source_label}` : "";
    let description = {
      semantic_success: "compiled and passed semantic check",
      compiled_no_semantic_pass: value.semantic_evaluated === false
        ? "compiled; semantic check not run"
        : "compiled but failed semantic check",
      compile_failed: "does not compile",
      missing: "missing output",
    }[value.state] || value.state;
    if (value.out_of_scope) description = "not part of this run's task scope";
    const disabled = value.out_of_scope ? "disabled" : "";
    return `<td class="matrix-cell"><button class="matrix-result" data-run="${escapeHtml(id)}" data-task="${escapeHtml(row.task)}" title="${value.out_of_scope ? "" : "Open result: "}${escapeHtml(description + tryCopy + locCopy + sourceCopy)}" ${disabled}><span class="matrix-mark ${escapeHtml(value.state)}"></span></button></td>`;
  }).join("")}</tr>`).join("");
  document.querySelectorAll(".matrix-result:not(:disabled)").forEach((button) => button.addEventListener("click", () => {
    selectedRun = button.dataset.run;
    selectedTask = button.dataset.task;
    byId("experiment-select").value = selectedRun;
    document.querySelectorAll(".view-button").forEach((item) => item.classList.toggle("active", item.dataset.view === "monitor"));
    byId("monitor-view").classList.remove("hidden");
    byId("comparison-view").classList.add("hidden");
    poll();
  }));
}

function renderComparison() {
  if (!comparisonData) return;
  preserveWindowScroll(() => {
    const tryNumber = Number(byId("try-slider").value);
    byId("try-value").textContent = tryNumber;
    byId("comparison-scope").textContent = comparisonData.scope_mode === "common" ? `${comparisonData.scope_count} common cases` : "Native scopes";
    renderComparisonBars(tryNumber);
    renderTryChart();
    renderComparisonTable(tryNumber);
    renderMatrix();
  });
}

async function fetchComparison(force = false) {
  const now = Date.now();
  if (comparisonPolling || (!force && now - lastComparisonFetch < 10000)) return;
  const ids = selectedExperimentIds();
  if (!ids.length) return;
  const scope = byId("scope-select").value;
  comparisonPolling = true;
  try {
    const response = await fetch(`/api/comparison?ids=${encodeURIComponent(ids.join(","))}&scope=${encodeURIComponent(scope)}`, {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const nextData = await response.json();
    const nextSignature = JSON.stringify(nextData);
    if (nextSignature === comparisonSignature) return;
    comparisonData = nextData;
    comparisonSignature = nextSignature;
    const maxTry = Math.max(1, ...comparisonData.experiments.map((item) => item.max_tries));
    byId("try-slider").max = maxTry;
    if (Number(byId("try-slider").value) > maxTry) byId("try-slider").value = maxTry;
    renderComparison();
  } catch (error) {
    console.error("Could not load comparison", error);
  } finally {
    comparisonPolling = false;
    lastComparisonFetch = Date.now();
  }
}

function renderExperimentControls() {
  const groups = new Map();
  experiments.forEach((item) => {
    const group = item.group || "Experiments";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(item);
  });
  byId("experiment-select").innerHTML = [...groups.entries()].map(([group, items]) => `
    <optgroup label="${escapeHtml(group)}">
      ${items.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === selectedRun ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
    </optgroup>`).join("");
  byId("model-toggles").innerHTML = [...groups.entries()].map(([group, items]) => `
    <details class="model-toggle-group" ${group === "Architecture results by budget" ? "open" : ""}>
      <summary><span>${escapeHtml(group)}</span><small>${items.length} run${items.length === 1 ? "" : "s"}</small></summary>
      <div class="model-toggle-items">
        ${items.map((item) => `<label class="model-toggle" style="--model-color:${escapeHtml(item.color)}"><input type="checkbox" value="${escapeHtml(item.id)}" ${item.comparison_default ? "checked" : ""}><span class="model-swatch"></span><span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.condition)}</small></span></label>`).join("")}
      </div>
    </details>`).join("");
  document.querySelectorAll(".model-toggle input").forEach((input) => input.addEventListener("change", () => fetchComparison(true)));
}

function applyComparisonPreset(view) {
  const judgeModel = view === "semantic-temp0"
    ? "gpt-5.4"
    : view === "semantic-gpt56-temp0" ? "gpt-5.6-sol" : null;
  document.querySelectorAll(".model-toggle input").forEach((input) => {
    const experiment = experiments.find((item) => item.id === input.value);
    input.checked = judgeModel
      ? experiment?.judge_temperature === 0 && experiment?.judge_model === judgeModel
      : Boolean(experiment?.comparison_default);
  });
  if (judgeModel) {
    document.querySelectorAll(".model-toggle-group").forEach((group) => {
      group.open = [...group.querySelectorAll("input")].some((input) => input.checked);
    });
  }
  byId("comparison-title").textContent = judgeModel
    ? `${judgeModel === "gpt-5.4" ? "GPT-5.4" : "GPT-5.6 Sol"} temperature 0 semantic comparison`
    : "Model comparison";
  byId("comparison-description").textContent = judgeModel === "gpt-5.4"
    ? "All five generation conditions are judged independently by GPT-5.4 at temperature 0; temperature-1 results remain separate."
    : judgeModel === "gpt-5.6-sol"
      ? "All five generation conditions are judged independently by GPT-5.6 Sol at temperature 0 and reasoning effort none."
      : "Compilation and semantic success remain separate. Missing outputs are never counted as judged failures.";
  comparisonSignature = null;
}

async function bootstrap() {
  try {
    const response = await fetch("/api/experiments", {cache: "no-store"});
    const data = await response.json();
    experiments = data.experiments;
    selectedRun = data.default_run || experiments[0]?.id || null;
    renderExperimentControls();
    await Promise.all([poll(), fetchComparison(true)]);
  } catch (error) {
    console.error("Dashboard bootstrap failed", error);
    poll();
  }
}

byId("experiment-select").addEventListener("change", (event) => {
  selectedRun = event.target.value;
  selectedTask = null;
  taskDetail = null;
  stateSignature = null;
  detailSignature = null;
  poll();
});

document.querySelectorAll(".view-button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".view-button").forEach((item) => item.classList.toggle("active", item === button));
  const view = button.dataset.view;
  const comparisonView = ["comparison", "semantic-temp0", "semantic-gpt56-temp0"].includes(view);
  byId("monitor-view").classList.toggle("hidden", view !== "monitor");
  byId("comparison-view").classList.toggle("hidden", !comparisonView);
  if (comparisonView) {
    applyComparisonPreset(view);
    fetchComparison(true);
  }
}));

byId("scope-select").addEventListener("change", () => fetchComparison(true));
byId("try-slider").addEventListener("input", renderComparison);

bootstrap();
setInterval(() => {
  poll();
  if (!byId("comparison-view").classList.contains("hidden")) fetchComparison();
}, 1500);
