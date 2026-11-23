"use strict";

const get = id => document.getElementById(id);
const form = get("form");
const fields = [...form.querySelectorAll("[name]")];
const modeButtons = [...get("analysis").querySelectorAll("[data-analysis]")];
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const result = get("result");
const plot = {left: 61, right: 420, top: 9, bottom: 117};
const dcFields = [
  ["vb_v", "VB", "V", 1], ["ve_v", "VE", "V", 1], ["vc_v", "VC", "V", 1],
  ["vce_v", "VCE", "V", 1], ["ib_a", "IB", "µA", 1e6],
  ["ic_a", "IC", "mA", 1e3], ["ie_a", "IE", "mA", 1e3],
];
const sampleColumns = {
  ac: ["frequency_hz", "gain_db", "phase_deg", "vin_re_v", "vin_im_v", "vout_re_v", "vout_im_v"],
  tran: ["time_s", "vin_v", "vout_v"],
};
const inputUnits = {vcc: "v", r1: "ohm", r2: "ohm", rc: "ohm", re: "ohm", rl: "ohm",
  cin: "f", cout: "f", amp: "v_peak", freq: "hz"};
const displayFactors = {vcc: 1, r1: .001, r2: .001, rc: .001, re: .001, rl: .001,
  cin: 1e6, cout: 1e6, amp: 1e3, freq: .001};
const statusText = {idle: "ยังไม่รัน", running: "กำลังรัน", success: "มีผล", warning: "มีผลพร้อมคำเตือน", error: "แสดงผลไม่ได้"};
const instructions = {
  dc: "อ่านแรงดันที่ขา B, C และ E เทียบกับกราวด์ แล้วดู VCE ซึ่งเป็น VC − VE",
  ac: "อ่านอัตราขยายและเฟสที่ความถี่เดียวกัน Vin อยู่ก่อน Cin และ Vout อยู่คร่อม RL หลัง Cout เฟสแสดงต่อเนื่องในช่วงข้อมูลที่ใช้ได้",
  tran: "อ่าน Vin และ Vout ที่เวลาเดียวกัน การ์ดแสดงครึ่งหนึ่งของ peak-to-peak ในช่วงกราฟทั้งหมด",
};
const saved = {dc: [], ac: [], tran: []};
const labels = {vb: "B", vc: "C", ve: "E", vin: "Vin", vout: "Vout"};
let analysis = "ac", probe = "vout", generation = 0, timer, controller;
let latest = null, chartViews = [], activeIndex = 0;
let playback = 0, playbackStart = null, playbackOrigin = 0;

function format(value) {
  if (!Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  if ((absolute > 0 && absolute < 0.001) || absolute >= 1e7) return value.toExponential(3);
  return String(Number(value.toPrecision(6)));
}

function reading(value, unit) {
  return Number.isFinite(value) ? format(value) + " " + unit : "—";
}

function inputDisplay(key, value) {
  const unit = get("unit-" + key).textContent.trim();
  return reading(value * displayFactors[key], unit);
}

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function facts(target, entries) {
  target.replaceChildren(...entries.flatMap(([label, value]) => [element("dt", label), element("dd", value)]));
}

function metrics(entries) {
  const container = element("dl", undefined, "metrics");
  for (const [label, value] of entries) {
    const card = element("div", undefined, "metric");
    card.append(element("dt", label), element("dd", value));
    container.append(card);
  }
  return container;
}

function setStatus(state, message) {
  const status = get("status");
  status.dataset.state = state;
  status.textContent = message ? statusText[state] + " · " + message : statusText[state];
  result.setAttribute("aria-busy", String(state === "running"));
}

function setFieldErrors(errors = {}) {
  for (const field of fields) {
    const message = typeof errors[field.name] === "string" ? errors[field.name] : "";
    field.setAttribute("aria-invalid", String(Boolean(message)));
    const detail = get("error-" + field.name);
    detail.textContent = message;
    detail.hidden = !message;
  }
}

function setSchematic() {
  for (const part of document.querySelectorAll("[data-part]")) {
    const key = part.dataset.part;
    const label = key.toUpperCase();
    const value = latest?.payload.inputs_si[key];
    part.textContent = value === undefined ? label : label + " · " + inputDisplay(key, value);
  }
  for (const node of document.querySelectorAll("[data-node]")) {
    node.classList.toggle("active", node.dataset.node === probe);
  }
  for (const button of get("probes").querySelectorAll("[data-probe]")) {
    button.setAttribute("aria-pressed", String(button.dataset.probe === probe));
  }
  paintProbe();
}

function paintProbe() {
  let value = "—";
  const data = latest?.payload.data;
  if (data?.point && ["vb", "vc", "ve"].includes(probe)) {
    value = reading(data.point[probe + "_v"], "V");
  }
  const row = data?.samples?.[activeIndex];
  if (row && ["vin", "vout"].includes(probe)) {
    if (analysis === "tran") {
      value = reading(row[probe + "_v"] * 1e3, "mV");
    } else {
      const imaginary = row[probe + "_im_v"];
      value = format(row[probe + "_re_v"]) + (imaginary < 0 ? " − j" : " + j") + format(Math.abs(imaginary)) + " V";
    }
  }
  get("probe-reading").textContent = labels[probe] + " · " + value;
}

function axisTicks(min, max, logarithmic) {
  if (logarithmic) {
    const first = Math.ceil(Math.log10(min) - 1e-8);
    const last = Math.floor(Math.log10(max) + 1e-8);
    if (last > first) return Array.from({length: last - first + 1}, (_, index) => 10 ** (first + index));
  }
  return Array.from({length: 5}, (_, index) => min + (max - min) * index / 4);
}

function tickLabel(value) {
  const absolute = Math.abs(value);
  if ((absolute > 0 && absolute < 0.01) || absolute >= 1e6) return value.toExponential(1);
  return String(Number(value.toPrecision(4)));
}

function makeChart(container, rows, config) {
  const {left, right, top, bottom} = plot;
  const {title, xKey, xUnit, xFactor, yUnit, yFactor, series, logX} = config;
  const toX = logX ? value => Math.log10(value) : value => value;
  const first = rows[0][xKey], last = rows.at(-1)[xKey];
  const xMin = toX(first), xSpan = toX(last) - xMin;
  const x = row => left + (right - left) * (toX(row[xKey]) - xMin) / xSpan;
  const valid = rows.flatMap(row => series.map(key => row[key])).filter(Number.isFinite);
  if (!valid.length) {
    container.append(element("p", title + " · ไม่มีจุดที่แสดงได้", "empty"));
    return;
  }
  const low = valid.reduce((min, value) => Math.min(min, value), Infinity);
  const high = valid.reduce((max, value) => Math.max(max, value), -Infinity);
  const padding = low === high ? Math.max(Math.abs(low) * .1, 1 / yFactor) : (high - low) * .08;
  const yMin = low - padding, yMax = high + padding;
  const y = value => bottom - (bottom - top) * (value - yMin) / (yMax - yMin);
  const number = value => value.toFixed(3);
  const tracePath = key => {
    let gap = true;
    return rows.map(row => {
      if (!Number.isFinite(row[key])) { gap = true; return ""; }
      const segment = (gap ? "M" : "L") + number(x(row)) + " " + number(y(row[key]));
      gap = false;
      return segment;
    }).join("");
  };
  const traces = series.map((key, index) => '<path class="trace-' + (index === 0 ? "a" : "b") + '" d="' + tracePath(key) + '"/>').join("");
  const gridY = axisTicks(yMin, yMax, false).map(value =>
    '<path class="grid" d="M' + left + " " + y(value) + "H" + right + '"/><text x="' + (left - 4) +
    '" y="' + (y(value) + 4) + '" text-anchor="end">' + tickLabel(value * yFactor) + "</text>").join("");
  const gridX = axisTicks(first, last, logX).map(value =>
    '<path class="grid" d="M' + x({[xKey]: value}) + " " + top + "V" + bottom + '"/><text x="' +
    x({[xKey]: value}) + '" y="' + (bottom + 16) + '" text-anchor="middle">' +
    (logX && value >= 1e6 ? value / 1e6 + "M" : logX && value >= 1e3 ? value / 1e3 + "k" : tickLabel(value * xFactor)) + "</text>").join("");
  const clipId = "spice-chart-" + chartViews.length;
  const figure = element("figure", undefined, "chart");
  figure.append(element("figcaption", title));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "graph");
  svg.setAttribute("viewBox", "0 0 438 153");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", title + " · แกนแนวนอน " + xUnit + " · แกนแนวตั้ง " + yUnit);
  // Chart markup contains only fixed labels and numbers derived from validated samples.
  svg.innerHTML = '<defs><clipPath id="' + clipId + '"><rect class="reveal" x="' + left +
    '" y="0" width="0" height="130"/></clipPath></defs>' + gridY + gridX +
    '<path class="axis" d="M' + left + " " + top + "V" + bottom + "H" + right + '"/>' +
    '<text x="4" y="143">' + yUnit + '</text><text x="' + right + '" y="148" text-anchor="end">' + xUnit + "</text>" +
    '<g class="context">' + traces + '</g><g class="progress" clip-path="url(#' + clipId + ')">' + traces + "</g>" +
    '<line class="pin-line" y1="' + top + '" y2="' + bottom + '" hidden/>' +
    '<line class="cursor-line" y1="' + top + '" y2="' + bottom + '"/>' +
    series.map((_, index) => '<circle class="dot-' + (index === 0 ? "a" : "b") + '" r="4.3"/>').join("");
  chartViews.push({
    x, y, series,
    pin: svg.querySelector(".pin-line"),
    cursor: svg.querySelector(".cursor-line"),
    reveal: svg.querySelector(".reveal"),
    dots: svg.querySelectorAll("circle"),
  });
  svg.addEventListener("click", event => {
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    if (point.x < left || point.x > right || point.y < top || point.y > bottom) return;
    stopPlayback();
    setCursor(nearestIndex(rows, row => x(row), point.x));
  });
  figure.append(svg);
  container.append(figure);
}

function nearestIndex(rows, valueOf, target) {
  let low = 0, high = rows.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (valueOf(rows[mid]) < target) low = mid + 1;
    else high = mid;
  }
  return low && target - valueOf(rows[low - 1]) <= valueOf(rows[low]) - target ? low - 1 : low;
}

function sampleText(row) {
  return analysis === "ac"
    ? [reading(row.frequency_hz, "Hz"), reading(row.gain_db, "dB"), reading(row.phase_deg, "°")].join(" · ")
    : [reading(row.time_s * 1e3, "ms"), "Vin " + reading(row.vin_v * 1e3, "mV"), "Vout " + reading(row.vout_v * 1e3, "mV")].join(" · ");
}

function setCursor(index) {
  const rows = latest?.payload.data.samples;
  if (!rows) return;
  activeIndex = index;
  const row = rows[index];
  get("cursor").value = String(index);
  get("cursor").setAttribute("aria-valuetext", sampleText(row));
  get("cursor-value").textContent = sampleText(row);
  for (const chart of chartViews) {
    const x = chart.x(row);
    chart.cursor.setAttribute("x1", x);
    chart.cursor.setAttribute("x2", x);
    chart.reveal.setAttribute("width", Math.max(0, x - plot.left));
    chart.series.forEach((key, i) => {
      const dot = chart.dots[i];
      dot.toggleAttribute("hidden", !Number.isFinite(row[key]));
      if (Number.isFinite(row[key])) {
        dot.setAttribute("cx", x);
        dot.setAttribute("cy", chart.y(row[key]));
      }
    });
  }
  paintProbe();
}

function stopPlayback() {
  cancelAnimationFrame(playback);
  playback = 0;
  playbackStart = null;
  get("play").setAttribute("aria-pressed", "false");
  get("play").textContent = "▶ เล่นกราฟ";
  result.classList.remove("is-playing");
}

function animate(time) {
  if (playbackStart === null) playbackStart = time;
  const rows = latest.payload.data.samples;
  const width = plot.right - plot.left;
  const position = plot.left + (playbackOrigin + (time - playbackStart) * width / 9500) % width;
  const index = nearestIndex(rows, chartViews[0].x, position);
  if (index !== activeIndex) setCursor(index);
  playback = requestAnimationFrame(animate);
}

function play() {
  if (playback) { stopPlayback(); return; }
  playbackOrigin = chartViews[0].x(latest.payload.data.samples[activeIndex]) - plot.left;
  get("play").setAttribute("aria-pressed", "true");
  get("play").textContent = "Ⅱ พักกราฟ";
  result.classList.add("is-playing");
  playback = requestAnimationFrame(animate);
}

function renderProvenance(payload) {
  const item = payload.provenance;
  const classification = item.classification === "provisional" ? "โมเดลชั่วคราว" : "ชุดผู้สอน";
  const badge = get("model-label");
  badge.dataset.classification = item.classification;
  badge.textContent = classification + " · " + item.name;
  badge.hidden = false;
  facts(get("provenance"), [
    ["รหัสรัน", payload.run_id], ["ประเภท", classification], ["โมเดล", item.model_name],
    ["ที่มา", item.source], ["ngspice", item.ngspice_version],
    ["SHA-256 โมเดล", item.sha256], ["SHA-256 Netlist", item.netlist_sha256],
    ...Object.entries(payload.inputs_si).map(([key, value]) => [
      get("input-" + key).parentElement.firstElementChild.textContent.trim(), inputDisplay(key, value),
    ]),
  ]);
  const warnings = get("run-warnings");
  warnings.replaceChildren(...payload.warnings.map(warning => element("li", warning)));
  warnings.hidden = !payload.warnings.length;
}

function renderDc(data) {
  result.append(metrics(dcFields.map(([key, label, unit, factor]) => [label, reading(data.point[key] * factor, unit)])));
  get("dc-checks").hidden = false;
  const checks = Object.entries(data.checks || {}).map(([name, item]) => {
    if (Number.isFinite(item)) return [name, reading(item, "A")];
    if (item && typeof item === "object") {
      const residual = item.residual_a;
      const limit = item.limit_a ?? item.tolerance_a;
      return [name, [reading(residual, "A"), "เกณฑ์ " + reading(limit, "A")].join(" · ")];
    }
    return [name, String(item)];
  });
  facts(get("check-values"), checks);
}

function renderPlots(data) {
  const rows = data.samples, container = element("div", undefined, "plots");
  if (analysis === "ac") {
    const near = rows[nearestIndex(rows, row => row.frequency_hz, 1000)];
    result.append(metrics([
      ["จุดใกล้ 1 kHz", reading(near.frequency_hz, "Hz")],
      ["อัตราขยาย", reading(near.gain_db, "dB")],
      ["เฟส", reading(near.phase_deg, "°")],
    ]));
    const common = {xKey: "frequency_hz", xUnit: "Hz", xFactor: 1, yFactor: 1, logX: true};
    makeChart(container, rows, {...common, title: "อัตราขยาย", series: ["gain_db"], yUnit: "dB"});
    makeChart(container, rows, {...common, title: "เฟส", series: ["phase_deg"], yUnit: "°"});
  } else {
    const summary = data.summary || {};
    result.append(metrics([
      ["Vin · Vpp/2", reading(summary.vin_pp_half_v * 1e3, "mV")],
      ["Vout · Vpp/2", reading(summary.vout_pp_half_v * 1e3, "mV")],
      ["ช่วงเวลา", reading(rows[0].time_s * 1e3, "ms") + "–" + reading(rows.at(-1).time_s * 1e3, "ms")],
    ]));
    makeChart(container, rows, {title: "Vin เส้นทึบ · Vout เส้นประ", xKey: "time_s", xUnit: "ms",
      xFactor: 1e3, series: ["vin_v", "vout_v"], yUnit: "mV", yFactor: 1e3, logX: false});
  }
  result.append(container);
  get("playback").hidden = !chartViews.length;
  get("cursor").max = String(rows.length - 1);
  setCursor(analysis === "ac" ? nearestIndex(rows, row => row.frequency_hz, 1000) : 0);
}

function renderSaved() {
  const target = get("saved"), entries = saved[analysis];
  target.replaceChildren();
  get("clear-runs").disabled = !entries.length;
  get("save-run").disabled = !latest || entries.some(entry => entry.payload.run_id === latest.payload.run_id);
  if (!entries.length) return;
  const group = element("div", undefined, "saved-runs");
  entries.forEach(({payload}, index) => {
    const card = element("div");
    card.append(element("strong", "รอบ " + (index + 1) + " · " + payload.provenance.name),
      element("p", payload.run_id, "muted"));
    group.append(card);
  });
  target.append(group);
  if (entries.length !== 2) return;
  const table = element("table", undefined, "compare");
  table.append(element("caption", "ค่าที่เปลี่ยนระหว่างสองรอบ"));
  const header = element("tr");
  for (const label of ["รายการ", "รอบ 1", "รอบ 2"]) {
    const cell = element("th", label);
    cell.scope = "col";
    header.append(cell);
  }
  table.createTHead().append(header);
  const body = table.createTBody();
  let changed = 0;
  for (const field of fields) {
    const [before, after] = entries.map(entry => entry.payload.inputs_si[field.name]);
    if (before === after) continue;
    const row = element("tr", undefined, "changed"), label = element("th", field.name.toUpperCase());
    label.scope = "row";
    row.append(label, element("td", inputDisplay(field.name, before)), element("td", inputDisplay(field.name, after)));
    body.append(row);
    changed++;
  }
  if (changed) target.append(table);
  else target.append(element("p", "อินพุตของสองรอบตรงกัน", "muted"));
  const values = entries.map(({payload: {data}}) => {
    if (analysis === "dc") return "IC " + reading(data.point.ic_a * 1e3, "mA") + " · VCE " + reading(data.point.vce_v, "V");
    if (analysis === "tran") return "Vout · Vpp/2 " + reading(data.summary?.vout_pp_half_v * 1e3, "mV");
    return sampleText(data.samples[nearestIndex(data.samples, row => row.frequency_hz, 1000)]);
  });
  target.append(element("p", "ผลรอบ 1 · " + values[0], "muted"), element("p", "ผลรอบ 2 · " + values[1], "muted"));
}

function clearResult(message) {
  stopPlayback();
  latest = null;
  chartViews = [];
  get("playback").hidden = true;
  get("model-label").hidden = true;
  get("run-warnings").hidden = true;
  get("run-warnings").replaceChildren();
  get("dc-checks").hidden = true;
  get("check-values").replaceChildren();
  get("provenance").replaceChildren();
  get("pinned").textContent = "";
  get("pin-point").disabled = true;
  get("download-csv").disabled = true;
  delete result.dataset.runId;
  result.replaceChildren(element("p", message, "empty"));
  setSchematic();
  renderSaved();
}

function isResult(payload) {
  if (!payload?.ok || payload.analysis !== analysis || typeof payload.run_id !== "string" ||
      !payload.provenance || !Array.isArray(payload.warnings) || !payload.data || !payload.inputs_si) return false;
  const keys = fields.filter(field => !field.matches(":disabled")).map(field => field.name);
  if (Object.keys(payload.inputs_si).length !== keys.length ||
      !keys.every(key => Number.isFinite(payload.inputs_si[key]) && payload.inputs_si[key] > 0)) return false;
  if (analysis === "dc") return dcFields.every(([key]) => Number.isFinite(payload.data.point?.[key]));
  const rows = payload.data.samples;
  const columns = sampleColumns[analysis];
  if (!Array.isArray(rows) || rows.length < 2) return false;
  return rows.every((row, index) => row &&
    columns.every(key => Number.isFinite(row[key]) || (key === "gain_db" || key === "phase_deg") && row[key] === null) &&
    (analysis !== "ac" || row.frequency_hz > 0) &&
    (index === 0 || rows[index - 1][columns[0]] < row[columns[0]]));
}

function showResult(payload) {
  latest = {payload};
  result.replaceChildren();
  result.dataset.runId = payload.run_id;
  renderProvenance(payload);
  if (analysis === "dc") renderDc(payload.data);
  else renderPlots(payload.data);
  get("download-csv").disabled = false;
  get("pin-point").disabled = !chartViews.length;
  setStatus(payload.warnings.length ? "warning" : "success");
  setSchematic();
  renderSaved();
}

function invalidate(message = "ปรับค่า แล้วกดรันการจำลองเพื่อดูผล") {
  generation++;
  clearTimeout(timer);
  controller?.abort();
  controller = null;
  clearResult(message);
  setFieldErrors();
  setStatus("idle");
}

async function run() {
  invalidate("กำลังอ่านผลจาก ngspice");
  const sequence = generation;
  const formInputs = Object.fromEntries(fields
    .filter(field => !field.matches(":disabled"))
    .map(field => [field.name, Number.isNaN(field.valueAsNumber) ? null : field.valueAsNumber]));
  const request = new AbortController();
  controller = request;
  setStatus("running");
  try {
    const response = await fetch("/api/spice", {
      method: "POST", headers: {"Content-Type": "application/json"}, signal: request.signal,
      body: JSON.stringify({analysis, inputs: formInputs}),
    });
    const payload = await response.json();
    if (sequence !== generation) return;
    if (response.ok && isResult(payload)) {
      showResult(payload);
    } else {
      clearResult("รอบนี้ไม่มีผลให้แสดง");
      setStatus("error", typeof payload?.message === "string" ? payload.message : "ข้อมูลผลจำลองไม่ครบ");
      setFieldErrors(payload?.fields || {});
    }
  } catch {
    if (sequence !== generation) return;
    clearResult("รอบนี้ไม่มีผลให้แสดง");
    setStatus("error", "ติดต่อโปรแกรมจำลองไม่ได้ ลองรันใหม่");
  } finally {
    if (sequence === generation) controller = null;
  }
}

function beginAuto() {
  invalidate();
  if (get("live-edit").checked) timer = setTimeout(run, 420);
}

function csvField(value) {
  if (value == null) return "";
  if (typeof value === "number") return String(value);
  const text = String(value);
  // Keep provenance as text when the CSV is opened in a spreadsheet.
  const safe = /^\s*[=+\-@\t\r]/.test(text) ? "'" + text : text;
  return '"' + safe.replace(/"/g, '""') + '"';
}

function download() {
  const {payload} = latest;
  const {run_id, provenance, data} = payload;
  const keys = analysis === "dc" ? dcFields.map(([key]) => key) : sampleColumns[analysis];
  const prefix = [
    ["run_id", run_id], ["analysis", analysis], ["name", provenance.name],
    ["model_name", provenance.model_name], ["classification", provenance.classification],
    ["model_sha256", provenance.sha256], ["ngspice_version", provenance.ngspice_version],
    ["netlist_sha256", provenance.netlist_sha256], ["source", provenance.source],
    ...Object.entries(payload.inputs_si || {}).map(([key, value]) => ["input_" + key + "_" + inputUnits[key], value]),
  ];
  const rows = [prefix.map(([key]) => key).concat(keys)];
  for (const sample of data.samples || [data.point]) {
    rows.push(prefix.map(([, value]) => value).concat(keys.map(key => sample[key])));
  }
  const contents = rows.map(row => row.map(csvField).join(",")).join("\r\n");
  const blob = new Blob(["\uFEFF", contents, "\r\n"], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = element("a");
  link.href = url;
  link.download = "lab04-" + analysis + "-" + run_id.replace(/[^a-zA-Z0-9_-]/g, "_") + ".csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

form.addEventListener("submit", event => { event.preventDefault(); run(); });
form.addEventListener("input", event => { if (event.target.name) beginAuto(); });
get("live-edit").addEventListener("change", event => { if (!event.target.checked) clearTimeout(timer); });
get("reset").addEventListener("click", () => {
  for (const field of fields) field.value = field.defaultValue;
  beginAuto();
});
for (const button of modeButtons) {
  button.addEventListener("click", () => {
    if (analysis === button.dataset.analysis) return;
    analysis = button.dataset.analysis;
    for (const choice of modeButtons) choice.setAttribute("aria-pressed", String(choice === button));
    get("signal-inputs").hidden = analysis !== "tran";
    get("signal-inputs").disabled = analysis !== "tran";
    get("method-body").textContent = instructions[analysis];
    probe = analysis === "dc" ? "vb" : "vout";
    beginAuto();
  });
}
document.addEventListener("click", event => {
  const target = event.target.closest("[data-node], [data-probe]");
  if (!target) return;
  probe = target.dataset.node || target.dataset.probe;
  setSchematic();
});
get("zoom").addEventListener("click", () => get("circuit-dialog").showModal());
get("play").addEventListener("click", play);
get("cursor").addEventListener("input", event => { stopPlayback(); setCursor(Number(event.target.value)); });
reduceMotion.addEventListener("change", event => { if (event.matches) stopPlayback(); });
get("pin-point").addEventListener("click", () => {
  const row = latest.payload.data.samples[activeIndex];
  get("pinned").textContent = "จุดที่ปัก · " + sampleText(row);
  for (const chart of chartViews) {
    chart.pin.setAttribute("x1", chart.x(row));
    chart.pin.setAttribute("x2", chart.x(row));
    chart.pin.removeAttribute("hidden");
  }
});
get("save-run").addEventListener("click", () => {
  saved[analysis] = [...saved[analysis], latest].slice(-2);
  renderSaved();
});
get("clear-runs").addEventListener("click", () => { saved[analysis] = []; renderSaved(); });
get("download-csv").addEventListener("click", download);
get("method-body").textContent = instructions[analysis];
get("run").disabled = false;
setSchematic();
