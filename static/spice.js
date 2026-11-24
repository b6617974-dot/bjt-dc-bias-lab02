"use strict";

const get = id => document.getElementById(id);
const form = get("form");
const fields = [...form.querySelectorAll("[name]")];
const modeButtons = [...get("analysis").querySelectorAll("[data-analysis]")];
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const result = get("result");
const settings = JSON.parse(get("workbench-settings").textContent);
const componentKeys = Object.keys(settings.spice_fields).filter(key => key !== "amp" && key !== "freq");
const stimulusKeys = ["amp", "freq"];
const storageKey = "eng292121.workbench.runs.v1";
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
const biasNames = {divider: "Voltage Divider", fixed: "Fixed Bias", emitter: "Emitter Bias"};
const analyticalNames = {forward_active: "Forward Active", cutoff_estimate: "ประมาณ Cutoff",
  saturation_estimate: "ประมาณ Saturation", outside_model: "นอกขอบเขตสมมติฐาน"};
const labels = {vb: "B", vc: "C", ve: "E", vin: "Vin", vout: "Vout"};
const modeDrafts = {};
let analysis = "dc", biasMode = "divider", probe = "vb", generation = 0, timer, controller;
let latest = null, chartViews = [], activeIndex = 0;
let playback = 0, playbackStart = null, playbackOrigin = 0;
let analytical = null, baseline = null, reference = null, pinIndex = null, chartWindow = null;
let restorePoint = null, designRequest = null;
let activeStarter = null;
let experiments = loadExperiments();

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

function formValues() {
  return Object.fromEntries(fields.map(field => [field.name, field.value]));
}

function numbers(keys, values = formValues()) {
  return Object.fromEntries(keys.map(key => [key, values[key] === "" ? null : Number(values[key])]));
}

function spiceInputs(view, values) {
  return numbers(view === "tran" ? [...componentKeys, ...stimulusKeys] : componentKeys, values);
}

function biasInputs(mode, values) {
  return {mode, ...numbers(Object.keys(settings.bias_defaults[mode]), values)};
}

function setForm(values) {
  for (const field of fields) if (Object.hasOwn(values, field.name)) field.value = values[field.name];
}

function updateControls() {
  const isDc = analysis === "dc";
  const isDivider = biasMode === "divider";
  const keys = new Set(isDc ? Object.keys(settings.bias_defaults[biasMode]) : []);
  if (isDivider) for (const key of componentKeys) keys.add(key);
  if (analysis === "tran") for (const key of stimulusKeys) keys.add(key);
  for (const field of fields) {
    field.disabled = !keys.has(field.name);
    field.closest(".field-wrap").hidden = field.disabled;
  }
  get("bias-mode").hidden = !isDc;
  get("bias-mode-note").hidden = isDivider;
  get("bias-assumptions").hidden = !isDc;
  get("signal-inputs").hidden = analysis !== "tran";
  get("signal-inputs").disabled = analysis !== "tran";
  get("method-body").textContent = instructions[analysis];
  get("view-title").textContent = {dc: "จุดทำงาน DC", ac: "การตอบสนองความถี่", tran: "รูปคลื่นตามเวลา"}[analysis];
  get("measure-auto").textContent = analysis === "ac" ? "หาจุด −3 dB" : "วัดคาบ Vin";
  get("design").hidden = !isDivider;
  for (const choice of modeButtons) {
    choice.setAttribute("aria-pressed", String(choice.dataset.analysis === analysis));
    choice.disabled = !isDivider && choice.dataset.analysis !== "dc";
    choice.title = choice.disabled ? "เลือก Voltage Divider เพื่อวิเคราะห์สัญญาณ" : "";
  }
  get("schematic").hidden = !isDivider;
  for (const mode of ["fixed", "emitter"]) get("diagram-" + mode).hidden = biasMode !== mode;
  for (const button of get("probes").querySelectorAll("[data-probe]")) {
    button.hidden = !isDivider && ["vin", "vout"].includes(button.dataset.probe);
  }
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
  const diagram = get("diagram-" + biasMode);
  if (diagram) {
    for (const label of diagram.querySelectorAll("[data-input-key]")) {
      const key = label.dataset.inputKey;
      label.textContent = analytical?.schematic_inputs?.[key] ?? "—";
    }
    for (const label of diagram.querySelectorAll("[data-result-key]")) {
      label.textContent = usableBias(analytical) ? (analytical.display[label.dataset.resultKey] ?? "—") : "—";
    }
  }
  paintProbe();
}

function copyDiagram(destination) {
  const source = get(biasMode === "divider" ? "schematic" : "diagram-" + biasMode);
  const svg = source.querySelector("svg").cloneNode(true);
  svg.removeAttribute("id");
  svg.removeAttribute("aria-labelledby");
  svg.setAttribute("aria-label", "วงจร " + biasNames[biasMode]);
  for (const item of svg.querySelectorAll("[id]")) item.removeAttribute("id");
  destination.classList.toggle("bias-schematic", biasMode !== "divider");
  destination.replaceChildren(svg);
}

function paintProbe() {
  let value = "—";
  const data = latest?.payload.data;
  if (data?.point && ["vb", "vc", "ve"].includes(probe)) {
    value = reading(data.point[probe + "_v"], "V");
  } else if (usableBias(analytical) && ["vb", "vc", "ve"].includes(probe)) {
    value = analytical.display[probe.toUpperCase() + "_V"] ?? "—";
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
  const [start, end] = chartWindow ?? [0, rows.length - 1];
  const shown = rows.slice(start, end + 1);
  const first = shown[0][xKey], last = shown.at(-1)[xKey];
  const overlay = (reference?.data?.samples ?? []).filter(row => row[xKey] >= first && row[xKey] <= last);
  const xMin = toX(first), xSpan = toX(last) - xMin;
  const x = row => left + (right - left) * (toX(row[xKey]) - xMin) / xSpan;
  const valid = [...shown, ...overlay].flatMap(row => series.map(key => row[key])).filter(Number.isFinite);
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
  const tracePath = (key, points) => {
    let gap = true;
    return points.map(row => {
      if (!Number.isFinite(row[key])) { gap = true; return ""; }
      const segment = (gap ? "M" : "L") + number(x(row)) + " " + number(y(row[key]));
      gap = false;
      return segment;
    }).join("");
  };
  const traces = series.map((key, index) => '<path class="trace-' + (index === 0 ? "a" : "b") + '" d="' + tracePath(key, shown) + '"/>').join("");
  const comparison = overlay.length ? series.map((key, i) => '<path class="trace-baseline' + (i ? ' secondary' : '') + '" d="' + tracePath(key, overlay) + '"/>').join("") : "";
  const gridY = axisTicks(yMin, yMax, false).map(value =>
    '<path class="grid" d="M' + left + " " + y(value) + "H" + right + '"/><text x="' + (left - 4) +
    '" y="' + (y(value) + 4) + '" text-anchor="end">' + tickLabel(value * yFactor) + "</text>").join("");
  const gridX = axisTicks(first, last, logX).map(value =>
    '<path class="grid" d="M' + x({[xKey]: value}) + " " + top + "V" + bottom + '"/><text x="' +
    x({[xKey]: value}) + '" y="' + (bottom + 16) + '" text-anchor="middle">' +
    (logX && value >= 1e6 ? value / 1e6 + "M" : logX && value >= 1e3 ? value / 1e3 + "k" : tickLabel(value * xFactor)) + "</text>").join("");
  const clipId = "spice-chart-" + chartViews.length;
  const figure = element("figure", undefined, "chart");
  figure.append(element("figcaption", title + (overlay.length ? " · เส้นประม่วงคือค่าฐาน" : "")));
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
    comparison + '<g class="context">' + traces + '</g><g class="progress" clip-path="url(#' + clipId + ')">' + traces + "</g>" +
    '<line class="pin-line" y1="' + top + '" y2="' + bottom + '" hidden/>' +
    '<line class="cursor-line" y1="' + top + '" y2="' + bottom + '"/>' +
    series.map((_, index) => '<circle class="dot-' + (index === 0 ? "a" : "b") + '" r="4.3"/>').join("");
  chartViews.push({
    x, y, series, start, end,
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
    setCursor(start + nearestIndex(shown, row => x(row), point.x));
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
  if (!rows || !Number.isInteger(index) || !rows[index]) return;
  activeIndex = index;
  const row = rows[index];
  const text = sampleText(row);
  get("cursor").value = String(index);
  get("cursor").setAttribute("aria-valuetext", text);
  get("cursor-value").textContent = text;
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
  paintMeasurement();
}

function paintMeasurement() {
  const rows = latest?.payload.data.samples;
  const pinned = rows?.[pinIndex];
  if (!pinned) return;
  const row = rows[activeIndex];
  const delta = analysis === "ac"
    ? [reading(row.frequency_hz - pinned.frequency_hz, "Hz"),
       reading(Number.isFinite(row.gain_db) && Number.isFinite(pinned.gain_db) ? row.gain_db - pinned.gain_db : NaN, "dB")]
    : [reading((row.time_s - pinned.time_s) * 1e3, "ms"),
       "Vout " + reading((row.vout_v - pinned.vout_v) * 1e3, "mV")];
  get("measurement-result").textContent = "B − A · " + delta.join(" · ");
  get("zoom-range").disabled = pinIndex === activeIndex;
  for (const chart of chartViews) {
    const inside = pinIndex >= chart.start && pinIndex <= chart.end;
    chart.pin.toggleAttribute("hidden", !inside);
    if (inside) {
      const x = chart.x(pinned);
      chart.pin.setAttribute("x1", x);
      chart.pin.setAttribute("x2", x);
    }
  }
}

function automaticMeasurement() {
  const rows = latest?.payload.data.samples;
  if (!rows) return;
  if (analysis === "tran") {
    const crossings = [];
    for (let index = 1; index < rows.length; index++) {
      const a = rows[index - 1], b = rows[index];
      if (a.vin_v < 0 && b.vin_v >= 0) {
        crossings.push(a.time_s - a.vin_v * (b.time_s - a.time_s) / (b.vin_v - a.vin_v));
      }
    }
    if (crossings.length < 2) return "ข้อมูล Vin ยังมีจุดข้ามศูนย์ขาขึ้นไม่พอสำหรับวัดคาบ";
    const start = crossings.at(-2), end = crossings.at(-1), period = end - start;
    return "คาบ Vin " + reading(period * 1e3, "ms") + " · " + reading(1 / period, "Hz")
      + " · วัดจุดข้ามศูนย์ขาขึ้น " + reading(start * 1e3, "ms") + " ถึง " + reading(end * 1e3, "ms");
  }
  const anchor = nearestIndex(rows, row => row.frequency_hz, 1000);
  const level = rows[anchor].gain_db;
  if (!Number.isFinite(level)) return "Gain อ้างอิงใกล้ 1 kHz ยังอ่านไม่ได้";
  const cutoff = level - 3;
  function crossing(direction) {
    for (let index = anchor + direction; index >= 0 && index < rows.length; index += direction) {
      const near = rows[index - direction], far = rows[index];
      if (!Number.isFinite(far.gain_db)) return "จุดข้อมูลขาดช่วง";
      if (far.gain_db <= cutoff) {
        const weight = (cutoff - near.gain_db) / (far.gain_db - near.gain_db);
        return reading(Math.exp(Math.log(near.frequency_hz)
          + weight * (Math.log(far.frequency_hz) - Math.log(near.frequency_hz))), "Hz");
      }
    }
    return "ยังไม่พบในช่วงกราฟ";
  }
  return "ระดับ −3 dB เทียบ Gain ที่ " + reading(rows[anchor].frequency_hz, "Hz")
    + " · ต่ำ " + crossing(-1) + " · สูง " + crossing(1);
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
  const chart = chartViews[0];
  const index = Math.max(chart.start, Math.min(chart.end, nearestIndex(rows, chart.x, position)));
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

function usableBias(state) {
  return state?.ok && state.calculation?.state === "match" &&
    Number.isFinite(state.results?.VCE_V) && Number.isFinite(state.results?.IC_A);
}

function renderAnalytical(state) {
  analytical = state;
  get("analytical-box").hidden = false;
  get("analytical-status").textContent = !state?.ok
    ? "ตรวจค่าที่กรอกสำหรับคำนวณมือ"
    : (analyticalNames[state.region] ?? "ผลคำนวณมือ") + " · ใช้ β และ VBE ตามที่ตั้ง";
  get("analytical-cards").replaceChildren();
  const steps = get("analytical-steps");
  steps.replaceChildren();
  if (usableBias(state)) {
    get("analytical-cards").append(metrics(dcFields.map(([key, label]) =>
      [label, state.display[key.toUpperCase()] ?? "—"])));
    if (latest?.payload.data.point) {
      const point = latest.payload.data.point;
      const delta = element("p", "ngspice − คำนวณมือ · ", "muted");
      delta.append("ΔIC " + reading((point.ic_a - state.results.IC_A) * 1e3, "mA").replace(" ", "\u00a0"),
        " · ΔVCE " + reading(point.vce_v - state.results.VCE_V, "V").replace(" ", "\u00a0"));
      get("analytical-cards").append(delta);
    }
    for (const row of state.calculation.steps) {
      const line = element("li");
      line.append(element("strong", row.formula), element("span", row.substitution), element("b", row.result));
      steps.append(line);
    }
  } else if (state?.ok) {
    get("analytical-status").textContent += " · ยังยืนยันจุดทำงานจากสมมติฐานนี้ไม่ได้";
  }
  get("analytical-worked").hidden = !steps.children.length;
  get("formula-circuit").replaceChildren();
}

function qGraph() {
  result.querySelector(".q-chart")?.remove();
  const points = [];
  const append = (point, name, style) => {
    if (Number.isFinite(point?.vce_v) && Number.isFinite(point?.ic_a)) points.push({x: point.vce_v, y: point.ic_a * 1e3, name, style});
  };
  append(latest?.payload.data.point, "ngspice", "");
  if (usableBias(analytical)) {
    append({vce_v: analytical.results.VCE_V, ic_a: analytical.results.IC_A}, "คำนวณมือ", "analytical-point");
  }
  const prior = reference?.data?.point;
  if (prior) append(prior, "ค่าฐาน", "baseline");
  if (!points.length || points.some(point => !Number.isFinite(point.y))) return;
  const xMin = Math.min(0, ...points.map(point => point.x)) * 1.1;
  const xMax = Math.max(1, ...points.map(point => point.x)) * 1.1;
  const yMin = Math.min(0, ...points.map(point => point.y)) * 1.1;
  const yMax = Math.max(.01, ...points.map(point => point.y)) * 1.16;
  if (!Number.isFinite(xMax - xMin + yMax - yMin)) return;
  const {left, right, top, bottom} = plot;
  const x = value => left + (right - left) * (value - xMin) / (xMax - xMin);
  const y = value => bottom - (bottom - top) * (value - yMin) / (yMax - yMin);
  const figure = element("figure", undefined, "chart q-chart");
  figure.append(element("figcaption", "จุดทำงาน Q · แรงดัน VCE และกระแส IC"));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "graph");
  svg.setAttribute("viewBox", "0 0 438 153");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "กราฟจุดทำงาน Q แกนนอน VCE (V) แกนตั้ง IC (mA)");
  const xTicks = axisTicks(xMin, xMax, false).map(value =>
    '<path class="grid" d="M' + x(value) + ' ' + top + 'V' + bottom + '"/><text text-anchor="middle" x="' +
    x(value) + '" y="' + (bottom + 16) + '">' + tickLabel(value) + '</text>').join("");
  const yTicks = axisTicks(yMin, yMax, false).map(value =>
    '<path class="grid" d="M' + left + ' ' + y(value) + 'H' + right + '"/><text text-anchor="end" x="' +
    (left - 5) + '" y="' + (y(value) + 4) + '">' + tickLabel(value) + '</text>').join("");
  svg.innerHTML = xTicks + yTicks + '<path class="axis" d="M' + left + ' ' + top + 'V' + bottom + 'H' + right
    + '"/><text x="4" y="146">IC (mA)</text><text x="420" y="146" text-anchor="end">VCE (V)</text>';
  const legend = element("div", undefined, "group q-legend");
  for (const point of points) {
    const circle = document.createElementNS(svg.namespaceURI, "circle");
    circle.setAttribute("class", "q-point " + point.style);
    circle.setAttribute("cx", x(point.x));
    circle.setAttribute("cy", y(point.y));
    circle.setAttribute("r", point.style === "baseline" ? 4 : 5.5);
    const title = document.createElementNS(svg.namespaceURI, "title");
    title.textContent = point.name + " · " + reading(point.x, "V") + " · " + reading(point.y, "mA");
    circle.append(title);
    svg.append(circle);
    legend.append(element("span", title.textContent, point.style));
  }
  figure.append(svg, legend);
  result.append(figure);
}

function renderPlots(data, index) {
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
  get("measure-panel").hidden = !chartViews.length;
  get("cursor").min = String(chartWindow?.[0] ?? 0);
  get("cursor").max = String(chartWindow?.[1] ?? rows.length - 1);
  const initial = index ?? (analysis === "ac" ? nearestIndex(rows, row => row.frequency_hz, 1000) : 0);
  setCursor(Math.max(Number(get("cursor").min), Math.min(Number(get("cursor").max), initial)));
}

function loadExperiments() {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    if (!Array.isArray(stored)) return [];
    return stored.filter(record => record && typeof record.name === "string" &&
      Object.hasOwn(biasNames, record.mode) && ["dc", "ac", "tran"].includes(record.analysis) &&
      (record.mode === "divider" || record.analysis === "dc") &&
      record.inputs && fields.every(field => typeof record.inputs[field.name] === "string")).slice(0, 8);
  } catch {
    return [];
  }
}

function storeExperiments() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(experiments));
    return true;
  } catch {
    return false;
  }
}

function showExperiment() {
  const selected = selectedExperiment();
  const source = selected?.model ? selected.model + " · " + selected.runId : "คำนวณมือ Lab 03";
  get("saved").textContent = selected ? source + (selected.note ? " · " + selected.note : "") : "";
}

function selectedExperiment() {
  const value = get("saved-experiments").value;
  return value === "" ? null : experiments[Number(value)];
}

function renderSaved() {
  const select = get("saved-experiments");
  const value = select.value;
  select.replaceChildren(...experiments.map((record, i) => {
    const option = element("option", record.name);
    option.value = String(i);
    return option;
  }));
  if (value !== "" && experiments[Number(value)]) select.value = value;
  get("clear-runs").disabled = !experiments.length;
  get("restore-run").disabled = !experiments.length;
  showExperiment();
}

function hasResult() {
  return Boolean(latest || usableBias(analytical));
}

function updateResultActions() {
  get("save-run").disabled = !hasResult();
  get("export-run").disabled = !hasResult();
  get("print-report").disabled = !hasResult();
  get("export-graph").disabled = !result.querySelector(".graph");
  get("baseline-toggle").disabled = !hasResult() && !baseline;
  get("baseline-toggle").setAttribute("aria-pressed", String(Boolean(baseline)));
  get("baseline-toggle").textContent = baseline ? "เลิกเทียบค่าฐาน" : "เทียบกับค่าฐาน";
}

function refreshPlots() {
  if (analysis === "dc") {
    qGraph();
  } else if (latest?.payload.data.samples) {
    stopPlayback();
    chartViews = [];
    result.replaceChildren();
    renderPlots(latest.payload.data, activeIndex);
  }
  updateResultActions();
}

function baselineNote(text) {
  const output = get("baseline-summary");
  output.textContent = text;
  output.hidden = !text;
}

function changedInputs(base, current) {
  return Object.entries(current).filter(([key, value]) => base[key] !== value)
    .map(([key, value]) => key.toUpperCase() + " " + base[key] + " → " + value + " " + get("unit-" + key).textContent);
}

function modelIdentity(item) {
  return JSON.stringify([item.sha256, item.model_name, item.kind, item.pins, item.ngspice_version]);
}

async function compareBaseline(sequence = generation, signal) {
  reference = null;
  if (!baseline) { baselineNote(""); return; }
  const savedBase = baseline;
  if (savedBase.mode !== biasMode) {
    baselineNote("ค่าฐานอยู่ในวงจร " + biasNames[savedBase.mode]);
    return;
  }
  if (!hasResult()) return;
  if (!latest && usableBias(analytical) && usableBias(savedBase.analytical)) {
    const before = savedBase.analytical.results, after = analytical.results;
    const changes = changedInputs(savedBase.analytical.input_values, analytical.input_values);
    baselineNote((changes.join(" · ") || "อินพุตเหมือนค่าฐาน") + " · คำนวณมือ · ΔIC "
      + reading((after.IC_A - before.IC_A) * 1e3, "mA") + " · ΔVCE " + reading(after.VCE_V - before.VCE_V, "V"));
    reference = {data: {point: {ic_a: before.IC_A, vce_v: before.VCE_V}}, analytical: savedBase.analytical};
    refreshPlots();
    return;
  }
  if (!latest) { baselineNote("ต้องมีผล SPICE เพื่อเทียบกับค่าฐานรอบนี้"); return; }
  const current = latest.payload;
  const view = current.analysis;
  let prior = savedBase.runs[view];
  if (!prior) {
    baselineNote("กำลังรันค่าฐานสำหรับแท็บนี้");
    try {
      const candidate = await fetchSpice("/api/spice", {analysis: view, inputs: spiceInputs(view, savedBase.inputs)}, signal);
      if (sequence !== generation || baseline !== savedBase || latest?.payload !== current) return;
      if (isResult(candidate, view)) {
        prior = candidate;
        savedBase.runs[view] = prior;
      }
    } catch {
      if (sequence !== generation || baseline !== savedBase) return;
    }
  }
  if (!prior) { baselineNote("จำลองค่าฐานสำหรับแท็บนี้ไม่สำเร็จ"); return; }
  if (modelIdentity(prior.provenance) !== modelIdentity(current.provenance)) {
    baselineNote("รุ่นโมเดลหรือ ngspice ต่างจากรอบฐาน กรุณาเก็บค่าฐานรอบใหม่เพื่อเทียบ");
    return;
  }
  const changes = changedInputs(spiceInputs(view, savedBase.inputs), spiceInputs(view));
  const before = prior.data, after = current.data;
  let delta;
  if (view === "dc") {
    delta = "ΔIC " + reading((after.point.ic_a - before.point.ic_a) * 1e3, "mA") +
      " · ΔVCE " + reading(after.point.vce_v - before.point.vce_v, "V");
  } else if (view === "ac") {
    const gainAt1k = data => data.samples.find(row => Math.abs(row.frequency_hz - 1000) < 1e-6)?.gain_db;
    const a = gainAt1k(after), b = gainAt1k(before);
    delta = "ΔGain ที่ 1 kHz " + reading(Number.isFinite(a) && Number.isFinite(b) ? a - b : NaN, "dB");
  } else {
    delta = "ΔVout ครึ่ง Vpp " + reading((after.summary.vout_pp_half_v - before.summary.vout_pp_half_v) * 1e3, "mV");
    if (after.samples.at(-1).time_s !== before.samples.at(-1).time_s) delta += " · วัดตามช่วงของแต่ละรอบ";
  }
  baselineNote((changes.join(" · ") || "อินพุตเหมือนค่าฐาน") + " · " + delta +
    " · รอบฐาน " + prior.run_id + " → " + current.run_id);
  if (prior.run_id !== current.run_id) reference = prior;
  refreshPlots();
}

function clearResult(message) {
  stopPlayback();
  latest = null;
  analytical = null;
  reference = null;
  pinIndex = null;
  chartWindow = null;
  chartViews = [];
  get("playback").hidden = true;
  get("measure-panel").hidden = true;
  get("analytical-box").hidden = true;
  get("zoom-range").disabled = true;
  get("zoom-reset").hidden = true;
  get("measurement-result").textContent = "";
  get("automatic-result").textContent = "";
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
  updateResultActions();
  if (baseline) baselineNote("เก็บค่าฐานไว้ · รอผลรอบปัจจุบัน");
}

function isResult(payload, view = analysis) {
  if (!payload?.ok || payload.analysis !== view || typeof payload.run_id !== "string" ||
      !payload.provenance || !Array.isArray(payload.warnings) || !payload.data || !payload.inputs_si) return false;
  const keys = Object.keys(spiceInputs(view));
  if (Object.keys(payload.inputs_si).length !== keys.length ||
      !keys.every(key => Number.isFinite(payload.inputs_si[key]) && payload.inputs_si[key] > 0)) return false;
  if (view === "dc") return dcFields.every(([key]) => Number.isFinite(payload.data.point?.[key]));
  const rows = payload.data.samples;
  const columns = sampleColumns[view];
  if (!Array.isArray(rows) || rows.length < 2) return false;
  return rows.every((row, index) => row &&
    columns.every(key => Number.isFinite(row[key]) || (key === "gain_db" || key === "phase_deg") && row[key] === null) &&
    (view !== "ac" || row.frequency_hz > 0) &&
    (index === 0 || rows[index - 1][columns[0]] < row[columns[0]]));
}

function showResult(payload) {
  latest = {payload};
  result.replaceChildren();
  result.dataset.runId = payload.run_id;
  renderProvenance(payload);
  captureHostedSetupRun(payload);
  if (analysis === "dc") renderDc(payload.data);
  else renderPlots(payload.data);
  get("download-csv").disabled = false;
  get("pin-point").disabled = !chartViews.length;
  setStatus(payload.warnings.length ? "warning" : "success");
  setSchematic();
  updateResultActions();
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
  invalidate("กำลังคำนวณผลของรอบนี้");
  const sequence = generation;
  const values = formValues();
  const request = new AbortController();
  controller = request;
  setStatus("running");
  try {
    const [manual, simulated] = await Promise.allSettled([
      analysis === "dc" ? fetchJson("/api/calculate", biasInputs(biasMode, values), request.signal) : null,
      biasMode === "divider" ? fetchSpice("/api/spice", {analysis, inputs: spiceInputs(analysis, values)}, request.signal) : null,
    ]);
    if (sequence !== generation) return;
    const payload = simulated.value;
    const calculated = manual.value;
    const analyticalOk = calculated?.ok === true && calculated.mode === biasMode;
    if (isResult(payload)) {
      showResult(payload);
    } else if (analyticalOk && biasMode !== "divider") {
      result.replaceChildren();
      setStatus(usableBias(calculated) ? "success" : "warning", "คำนวณมือ Lab 03");
    } else {
      result.replaceChildren(element("p", biasMode === "divider" ? "รอบนี้ยังไม่มีผล SPICE" : "รอบนี้ยังไม่มีจุดทำงาน", "empty"));
      setStatus("error", payload?.message ?? (analyticalOk ? "ใช้ผลคำนวณมือด้านล่างได้" : "ตรวจค่าที่กรอกหรือรันใหม่"));
    }
    if (analysis === "dc") renderAnalytical(calculated);
    setFieldErrors({...calculated?.errors, ...payload?.fields});
    if (calculated?.errors?.vbe || calculated?.errors?.beta) get("bias-assumptions").open = true;
    if (analysis === "dc") qGraph();
    setSchematic();
    if (analysis === "dc" && get("analytical-worked").open && usableBias(analytical)) copyDiagram(get("formula-circuit"));
    updateResultActions();
    applyRestoredCursor();
    await compareBaseline(sequence, request.signal);
  } catch {
    if (sequence !== generation) return;
    clearResult("รอบนี้ไม่มีผลให้แสดง");
    setStatus("error", "ติดต่อโปรแกรมจำลองไม่ได้ ลองรันใหม่");
  } finally {
    if (sequence === generation) controller = null;
  }
}

async function fetchJson(url, data, signal) {
  const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data), signal});
  return response.json();
}

function fetchSpice(url, data, signal) {
  return fetchJson(url, activeStarter ? {...data, model: activeStarter.model} : data, signal);
}

function beginAuto() {
  invalidate();
  if (get("live-edit").checked) timer = setTimeout(run, 420);
}

function changeMode(next) {
  if (biasMode !== next) {
    const values = formValues();
    modeDrafts[biasMode] = Object.fromEntries(Object.keys(settings.bias_defaults[biasMode])
      .map(key => [key, values[key]]));
    biasMode = next;
    const shared = Object.fromEntries(["vcc", "rc", "beta", "vbe"].map(key => [key, values[key]]));
    setForm({...modeDrafts[next] ?? settings.bias_defaults[next], ...shared});
  }
  get("bias-mode").value = next;
}

function captureExperiment() {
  if (!hasResult()) return null;
  const data = latest?.payload;
  const key = data?.data.samples && sampleColumns[analysis][0];
  return {
    name: get("experiment-name").value.trim() || biasNames[biasMode] + " · " + analysis.toUpperCase(),
    note: get("experiment-note").value.trim(),
    analysis, mode: biasMode, inputs: formValues(), probe,
    position: key ? data.data.samples[activeIndex][key] : null,
    anchor: key && pinIndex !== null ? data.data.samples[pinIndex][key] : null,
    model: data?.provenance.name ?? null, modelSha: data?.provenance.sha256 ?? null,
    modelIdentity: data ? modelIdentity(data.provenance) : null,
    runId: data?.run_id ?? null,
  };
}

function applyRestoredCursor() {
  const record = restorePoint;
  restorePoint = null;
  if (!record || !hasResult()) return;
  if (record.modelSha && (record.modelIdentity && latest
    ? modelIdentity(latest.payload.provenance) !== record.modelIdentity
    : latest?.payload.provenance.sha256 !== record.modelSha)) {
    get("saved").textContent = "เปิดอินพุตเดิมแล้ว · รอบนี้ใช้รุ่นโมเดลต่างจากหลักฐานเดิม";
  }
  if (Object.hasOwn(labels, record.probe)) {
    probe = record.probe;
    setSchematic();
  }
  const rows = latest?.payload.data.samples;
  if (!rows) return;
  const key = sampleColumns[analysis][0];
  if (Number.isFinite(record.position)) setCursor(nearestIndex(rows, row => row[key], record.position));
  if (Number.isFinite(record.anchor)) {
    pinIndex = nearestIndex(rows, row => row[key], record.anchor);
    get("pinned").textContent = "จุด A · " + sampleText(rows[pinIndex]);
    paintMeasurement();
  }
}

function chooseResultFiles(data, filename, type) {
  const blob = new Blob(data, {type});
  const url = URL.createObjectURL(blob);
  const link = element("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportRun() {
  const record = captureExperiment();
  if (!record) return;
  const evidence = {format: "eng292121-workbench-v1", ...record,
    analytical, spice: latest?.payload ?? null, baseline: reference,
    measurement: get("measurement-result").textContent,
    automatic_measurement: get("automatic-result").textContent};
  chooseResultFiles([JSON.stringify(evidence, null, 2) + "\n"], "bjt-workbench-" + (record.runId ?? record.mode) + ".json",
    "application/json");
}

function exportGraph() {
  const graphs = [...result.querySelectorAll(".graph")];
  if (!graphs.length) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 454 " + (30 + graphs.length * 176));
  const style = document.createElementNS(svg.namespaceURI, "style");
  style.textContent = "text{fill:#27433b;font:11px monospace}.axis,.grid,.trace-a,.trace-b,.trace-baseline{fill:none}.grid{stroke:#dce7e0}.axis{stroke:#829b92}.trace-a{stroke:#17645c;stroke-width:2}.trace-b{stroke:#a45131;stroke-width:2;stroke-dasharray:4 2}.trace-baseline{stroke:#6254a1;stroke-dasharray:5 4}.trace-baseline.secondary{stroke:#90576b;stroke-dasharray:2 3}.cursor-line,.pin-line{stroke:#647a71;stroke-dasharray:3 3}.q-point,.dot-a{fill:#17645c}.analytical-point,.dot-b{fill:#a45131}.q-point.baseline{fill:#6254a1}.progress,[hidden]{display:none}";
  svg.append(style);
  const addLabel = (label, y) => {
    const text = document.createElementNS(svg.namespaceURI, "text");
    text.setAttribute("x", "8");
    text.setAttribute("y", y);
    text.textContent = label;
    svg.append(text);
  };
  const source = latest?.payload;
  addLabel(source ? source.provenance.name + " · " + source.run_id : "Lab 03 · คำนวณมือ", 13);
  graphs.forEach((graph, index) => {
    const top = 24 + index * 176;
    addLabel(graph.previousElementSibling.textContent, top + 10);
    const copy = graph.cloneNode(true);
    copy.setAttribute("x", "8");
    copy.setAttribute("y", top + 14);
    copy.setAttribute("width", "438");
    copy.setAttribute("height", "153");
    svg.append(copy);
  });
  chooseResultFiles([new XMLSerializer().serializeToString(svg)], "bjt-workbench-" + analysis + ".svg", "image/svg+xml");
}

async function searchDesign() {
  designRequest?.abort();
  const request = new AbortController();
  designRequest = request;
  const inputs = spiceInputs("dc");
  const targetGain = get("target-gain").valueAsNumber;
  const maxCurrent = get("target-current").valueAsNumber;
  const status = get("design-status");
  const output = get("design-results");
  output.replaceChildren();
  if (!Number.isFinite(targetGain) || !Number.isFinite(maxCurrent) || maxCurrent <= 0) {
    status.textContent = "กรอก Gain และเพดานกระแสที่มากกว่าศูนย์";
    return;
  }
  status.textContent = "กำลังลองค่าชิ้นส่วนด้วย ngspice";
  get("design-run").disabled = true;
  try {
    const data = await fetchSpice("/api/spice/design", {inputs, target_gain_db: targetGain, max_ic_ma: maxCurrent}, request.signal);
    if (designRequest !== request) return;
    if (!data.ok) { status.textContent = data.message ?? "ค้นหาชุดค่าไม่สำเร็จ"; return; }
    const passed = data.candidates.some(candidate => candidate.passed);
    status.textContent = (passed ? "พบชุดที่เข้าเป้า" : "ยังไม่พบชุดที่เข้าเป้า") + " · ตรวจ "
      + data.evaluated + "/" + data.total + " ชุด · " + data.model_label
      + (data.model_classification === "provisional" ? " (ชั่วคราว)" : "")
      + (data.partial ? " · มีรอบที่ยังประเมินไม่ครบ" : "");
    for (const candidate of data.candidates) {
      const row = element("div", undefined, "design-candidate");
      const summary = element("div");
      summary.append(element("strong", "RC " + reading(candidate.rc_kohm, "kΩ") + " · RE " + reading(candidate.re_kohm, "kΩ")),
        element("p", (candidate.passed ? "เข้าเป้า" : "ใกล้เป้า") + " · " + reading(candidate.gain_db, "dB")
          + " · IC " + reading(candidate.ic_ma, "mA"), "muted"));
      for (const warning of candidate.warnings ?? []) summary.append(element("p", warning, "muted"));
      const receipts = element("details");
      receipts.append(element("summary", "ดูรหัสรัน"), element("p", "DC " + candidate.dc_run_id + " · AC " + candidate.ac_run_id, "muted"));
      summary.append(receipts);
      const apply = element("button", "ใช้ค่าชุดนี้");
      apply.type = "button";
      apply.addEventListener("click", () => {
        if (designRequest !== request || biasMode !== "divider" ||
            JSON.stringify(inputs) !== JSON.stringify(spiceInputs("dc"))) return;
        setForm({rc: candidate.rc_kohm, re: candidate.re_kohm});
        clearDesign();
        run();
        get("view-title").scrollIntoView({block: "nearest"});
      });
      row.append(summary, apply);
      output.append(row);
    }
  } catch {
    if (designRequest === request) status.textContent = "ติดต่อ ngspice ไม่ได้ ลองค้นหาอีกครั้ง";
  } finally {
    if (designRequest === request) get("design-run").disabled = false;
  }
}

function clearDesign() {
  designRequest?.abort();
  designRequest = null;
  get("design-run").disabled = false;
  get("design-status").textContent = "";
  get("design-results").replaceChildren();
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
    ["model_kind", provenance.kind], ["model_pins", provenance.pins?.join(" → ")],
    ["model_sha256", provenance.sha256], ["model_input_sha256", provenance.input_sha256], ["ngspice_version", provenance.ngspice_version],
    ["netlist_sha256", provenance.netlist_sha256], ["source", provenance.source],
    ...Object.entries(payload.inputs_si || {}).map(([key, value]) => ["input_" + key + "_" + inputUnits[key], value]),
  ];
  const rows = [prefix.map(([key]) => key).concat(keys)];
  for (const sample of data.samples || [data.point]) {
    rows.push(prefix.map(([, value]) => value).concat(keys.map(key => sample[key])));
  }
  const contents = rows.map(row => row.map(csvField).join(",")).join("\r\n");
  chooseResultFiles(["\uFEFF", contents, "\r\n"], "lab04-" + analysis + "-" + run_id.replace(/[^a-zA-Z0-9_-]/g, "_") + ".csv",
    "text/csv;charset=utf-8");
}

form.addEventListener("submit", event => { event.preventDefault(); run(); });
form.addEventListener("input", event => {
  if (!event.target.name) return;
  restorePoint = null;
  if (componentKeys.includes(event.target.name)) clearDesign();
  beginAuto();
});
get("live-edit").addEventListener("change", event => {
  if (!event.target.checked) clearTimeout(timer);
  else if (!hasResult() && !controller) beginAuto();
});
get("reset").addEventListener("click", () => {
  clearDesign();
  restorePoint = null;
  for (const field of fields) {
    if (!field.disabled) field.value = settings.bias_defaults[biasMode][field.name] ?? field.defaultValue;
  }
  beginAuto();
});
get("bias-mode").addEventListener("change", event => {
  restorePoint = null;
  changeMode(event.target.value);
  updateControls();
  clearDesign();
  beginAuto();
});
for (const button of modeButtons) {
  button.addEventListener("click", () => {
    if (analysis === button.dataset.analysis || button.disabled) return;
    restorePoint = null;
    analysis = button.dataset.analysis;
    probe = analysis === "dc" ? "vb" : "vout";
    updateControls();
    beginAuto();
  });
}
document.addEventListener("click", event => {
  const target = event.target.closest("[data-node], [data-probe]");
  if (target) {
    probe = target.dataset.node || target.dataset.probe;
    setSchematic();
    return;
  }
  const component = event.target.closest("[data-part], .bias-schematic [data-component]");
  if (!component) return;
  const field = get("input-" + (component.dataset.part || component.dataset.component.toLowerCase()));
  if (!field || field.disabled) return;
  if (get("circuit-dialog").open) get("circuit-dialog").close();
  field.focus();
  field.scrollIntoView({block: "nearest"});
});
function zoomCircuit() {
  copyDiagram(get("zoom-diagram"));
  get("circuit-dialog").showModal();
}
get("zoom").addEventListener("click", zoomCircuit);
get("formula-circuit").addEventListener("click", zoomCircuit);
get("analytical-worked").addEventListener("toggle", event => {
  if (event.target.open && usableBias(analytical)) copyDiagram(get("formula-circuit"));
});
get("play").addEventListener("click", play);
get("cursor").addEventListener("input", event => { stopPlayback(); setCursor(Number(event.target.value)); });
reduceMotion.addEventListener("change", event => { if (event.matches) stopPlayback(); });
get("pin-point").addEventListener("click", () => {
  if (!latest?.payload.data.samples) return;
  stopPlayback();
  const row = latest.payload.data.samples[activeIndex];
  pinIndex = activeIndex;
  get("pinned").textContent = "จุด A · " + sampleText(row);
  paintMeasurement();
});
get("measure-auto").addEventListener("click", () => {
  get("automatic-result").textContent = automaticMeasurement() ?? "";
});
get("zoom-range").addEventListener("click", () => {
  if (pinIndex === null || pinIndex === activeIndex) return;
  chartWindow = [Math.min(pinIndex, activeIndex), Math.max(pinIndex, activeIndex)];
  get("zoom-reset").hidden = false;
  refreshPlots();
});
get("zoom-reset").addEventListener("click", () => {
  chartWindow = null;
  get("zoom-reset").hidden = true;
  refreshPlots();
});
get("baseline-toggle").addEventListener("click", () => {
  if (baseline) {
    baseline = null;
    reference = null;
    baselineNote("");
    refreshPlots();
    return;
  }
  if (!hasResult()) return;
  baseline = {mode: biasMode, inputs: formValues(), analytical, runs: {}};
  if (latest) baseline.runs[analysis] = latest.payload;
  updateResultActions();
  compareBaseline(generation, controller?.signal);
});
get("save-run").addEventListener("click", () => {
  const record = captureExperiment();
  if (!record) return;
  experiments = [record, ...experiments].slice(0, 8);
  const stored = storeExperiments();
  renderSaved();
  get("saved-experiments").value = "0";
  showExperiment();
  if (!stored) get("saved").textContent += " · เก็บได้เฉพาะแท็บนี้";
});
get("saved-experiments").addEventListener("change", showExperiment);
get("restore-run").addEventListener("click", () => {
  const record = selectedExperiment();
  if (!record) return;
  clearDesign();
  changeMode(record.mode);
  setForm(record.inputs);
  analysis = record.analysis;
  get("experiment-name").value = record.name;
  get("experiment-note").value = record.note ?? "";
  restorePoint = record;
  updateControls();
  run();
  get("view-title").scrollIntoView({block: "nearest"});
});
get("clear-runs").addEventListener("click", () => {
  experiments = [];
  const stored = storeExperiments();
  renderSaved();
  if (!stored) get("saved").textContent = "ล้างรายการในแท็บนี้แล้ว แต่เข้าถึงพื้นที่ถาวรไม่ได้";
});
get("download-csv").addEventListener("click", download);
get("export-run").addEventListener("click", exportRun);
get("export-graph").addEventListener("click", exportGraph);
get("print-report").addEventListener("click", () => {
  const hiddenDetails = ["analytical-worked", "source"].map(get).filter(detail => !detail.open);
  for (const detail of hiddenDetails) detail.open = true;
  window.addEventListener("afterprint", () => { for (const detail of hiddenDetails) detail.open = false; }, {once: true});
  window.print();
});
get("design-run").addEventListener("click", searchDesign);
for (const id of ["target-gain", "target-current"]) get(id).addEventListener("input", clearDesign);

const setupLabels = {
  version: "อ่านเวอร์ชัน ngspice", divider: "วงจรแบ่งแรงดัน 10 V", dc: "DC · .op",
  ac: "AC · .ac", tran: "Transient · .tran",
};
const setupCodes = {
  engine_missing: "หา ngspice ไม่เจอ ตรวจ PATH หรือ LAB04_NGSPICE",
  engine: "เรียก ngspice ไม่สำเร็จ ลอง ngspice -v ในเทอร์มินัลเดียวกับ Flask",
  profile_unconfigured: "ยังไม่ได้ตั้ง LAB04_SPICE_PROFILE",
  profile_missing: "หา profile.json ไม่เจอ ตรวจพาธบนเครื่องที่รัน Flask",
  profile_invalid: "อ่านโปรไฟล์ไม่ได้หรือข้อมูลไม่ครบ ลองสร้าง profile.json ใหม่",
  model_path: "วางไฟล์โมเดลไว้ข้าง profile.json และใช้ชื่อไฟล์ในโปรไฟล์",
  model_missing: "หาไฟล์โมเดลที่ระบุใน profile.json ไม่เจอ",
  model_too_large: "ไฟล์โมเดลเกินขนาดที่รองรับ",
  model_checksum: "ค่า SHA-256 ต่างจากโปรไฟล์ ตรวจว่าใช้ไฟล์ต้นฉบับที่ถูกต้อง",
  model_format: "ไฟล์มีรูปแบบหรือคำสั่งที่โปรไฟล์โมเดลใช้ไม่ได้",
  model_declaration: "ชื่อหรือชนิดการประกาศโมเดลไม่ตรง ตรวจ declaration ในไฟล์",
  model_pins: "ตรวจว่าลำดับขา .SUBCKT มี B, C และ E อย่างละหนึ่งขาตามต้นทาง",
  timeout: "การตรวจหมดเวลา ลองใหม่หลังจบรอบจำลองอื่น",
  solver: "ngspice รันวงจรทดสอบไม่สำเร็จ",
  output: "ผลจาก ngspice ขาดหรืออ่านไม่ได้",
  divider_voltage: "แรงดันที่อ่านได้ต่างจากค่า 5 V ของวงจรแบ่งแรงดัน",
  busy: "กำลังมีการตรวจอีกชุด รอให้รอบนั้นเสร็จก่อน",
};
const hexSHA256 = /^[a-f\d]{64}$/i;
const setupFileLimit = 1024 * 1024;
let setupHealth = null, setupReport = null, setupBusy = false, hostedRuns = {};
let setupFile = null, setupFileRevision = 0;

function setupMessage(code) {
  return Object.hasOwn(setupCodes, code) ? setupCodes[code] : "";
}

function setupProfileMatch(profile, expected) {
  return profile?.sha256 === expected?.sha256 && profile?.model_name === expected?.model_name &&
    profile?.kind === expected?.kind && JSON.stringify(profile?.pins ?? []) === JSON.stringify(expected?.pins ?? []);
}

function captureHostedSetupRun(payload) {
  if (setupHealth?.mode !== "hosted" || !setupProfileMatch(payload.provenance, setupHealth.profile)) return;
  const version = payload.provenance.ngspice_version;
  if (Object.values(hostedRuns).some(current => current !== version)) hostedRuns = {};
  hostedRuns[payload.analysis] = version;
  renderSetup();
}

function renderSetup() {
  const badge = get("setup-indicator");
  const local = setupHealth?.mode === "local";
  const hosted = setupHealth?.mode === "hosted";
  const engine = setupHealth?.engine;
  const profile = setupHealth?.profile;
  const configured = engine?.status === "available" && profile?.status === "available";
  const build = hosted && setupHealth.verification?.source === "build" ? setupHealth.verification : null;
  const report = setupReport ?? build;
  const steps = Array.isArray(report?.steps) ? report.steps : [];
  const failed = report?.ok === false;
  const verified = configured && report?.ok !== false && Object.keys(setupLabels).every(id =>
    steps.some(step => step.id === id && step.status === "PASS"));
  const currentVersion = report?.engine_version ?? setupHealth?.version ??
    Object.values(hostedRuns)[0];
  const readMessage = get("setup-read-message").textContent;

  get("setup-local").hidden = !local;
  get("setup-hosted-note").hidden = !hosted;
  get("setup-check").hidden = !local;
  get("setup-check").disabled = setupBusy;
  get("setup-refresh").disabled = setupBusy;
  get("setup-report-source").hidden = !build;
  badge.dataset.state = verified ? "ready" : failed || (!configured && (setupHealth || readMessage)) ? "warning" : "pending";
  badge.textContent = verified ? "ตรวจครบแล้ว" : setupBusy ? "กำลังตรวจ" :
    failed ? "พบขั้นที่ต้องแก้" : configured ? "พบเครื่องมือและโมเดล" :
    setupHealth || readMessage ? "ตรวจการตั้งค่า" : "กำลังอ่านสถานะ";

  const details = [];
  if (setupHealth) details.push(["สภาพแวดล้อม", hosted ? "ออนไลน์" : "เครื่องที่รัน Flask"]);
  if (engine) details.push(["ngspice", engine.status === "available"
    ? (engine.resolution === "path" ? "พบผ่าน PATH" : "พบตามค่าตั้ง") + (currentVersion ? " · รุ่น " + currentVersion : "")
    : setupMessage(engine.code) || "ยังไม่พร้อม"]);
  if (profile) {
    if (profile.status === "available") {
      const source = {instructor: "ระบุแหล่งที่มาจากผู้สอน", provisional: "โมเดลชั่วคราว"};
      details.push(["โมเดล", [profile.name, source[profile.classification], profile.model_name].filter(Boolean).join(" · ")]);
      if (profile.sha256) details.push(["SHA-256", profile.sha256]);
      if (Array.isArray(profile.pins) && profile.pins.length) details.push(["ผังขา", profile.pins.join(" → ")]);
    } else details.push(["โมเดล", setupMessage(profile.code) || "ยังไม่พร้อม"]);
  }
  if (setupHealth?.commit) details.push(["Commit", setupHealth.commit]);
  if (hosted && !steps.length) {
    const modes = Object.keys(hostedRuns).map(mode => setupLabels[mode]);
    details.push(["ผลตรวจการทำงาน", modes.length ? "ยืนยันจากผลรันในหน้านี้ · " + modes.join(", ") : "ยังไม่มีผลตรวจแสดง"]);
  }
  facts(get("setup-facts"), details);

  renderSetupSteps(get("setup-steps"), steps);
}

function renderSetupSteps(list, steps) {
  list.replaceChildren();
  for (const [id, label] of Object.entries(setupLabels)) {
    const step = steps.find(item => item?.id === id);
    if (!step || !["PASS", "FAIL", "NOT RUN"].includes(step.status)) continue;
    const row = element("li");
    const pill = element("strong", step.status, "setup-badge");
    pill.dataset.state = step.status === "PASS" ? "ready" : step.status === "FAIL" ? "warning" : "pending";
    const details = [label, step.version, Number.isFinite(step.value_v) ? reading(step.value_v, "V") : "",
      step.run_id ? "รอบ " + step.run_id : "", setupMessage(step.code)].filter(Boolean).join(" · ");
    row.append(pill, element("span", details));
    list.append(row);
  }
  list.hidden = !list.children.length;
}

async function refreshSetup() {
  if (setupBusy) return;
  setupBusy = true;
  setupReport = null;
  const message = get("setup-read-message");
  message.textContent = "";
  get("setup-check-message").textContent = "";
  renderSetup();
  try {
    const response = await fetch("/api/spice/status", {cache: "no-store"});
    const status = await response.json();
    if (!response.ok || !["local", "hosted"].includes(status.mode) || !status.engine || !status.profile)
      throw new Error("unexpected setup status");
    if (!setupProfileMatch(status.profile, setupHealth?.profile)) hostedRuns = {};
    setupHealth = status;
    if (status.mode === "hosted" && latest) captureHostedSetupRun(latest.payload);
  } catch {
    setupHealth = null;
    hostedRuns = {};
    message.textContent = "อ่านสถานะไม่ได้ ลองกดอ่านสถานะใหม่";
  } finally {
    setupBusy = false;
    renderSetup();
  }
}

async function checkSetup() {
  if (setupBusy || setupHealth?.mode !== "local") return;
  setupBusy = true;
  setupReport = null;
  const message = get("setup-check-message");
  message.textContent = "กำลังทดสอบ ngspice และวงจรอ้างอิง";
  renderSetup();
  try {
    const report = await fetchJson("/api/spice/check", {});
    if (!Array.isArray(report.steps)) {
      message.textContent = setupMessage(report.code) || "เริ่มตรวจไม่ได้ ลองเปิด Workbench บนเครื่องที่รัน Flask";
      return;
    }
    setupReport = report;
    message.textContent = report.ok === true ? "จบชุดตรวจพร้อมใช้" : "ตรวจแล้วพบขั้นที่ต้องแก้ ดูสถานะรายขั้น";
  } catch {
    message.textContent = "ติดต่อ Flask ไม่ได้ ลองตรวจความพร้อมอีกครั้ง";
  } finally {
    setupBusy = false;
    renderSetup();
  }
}

function setupDeclarations(text) {
  const declarations = [];
  const namePattern = /^[a-z0-9_][a-z0-9_.-]*$/i;
  for (const raw of text.split(/\r\n|\n|\r/)) {
    const line = raw.trim();
    const model = /^\.model\s+(\S+)\s+npn(?=[\s(]|$)/i.exec(line);
    if (model && namePattern.test(model[1])) {
      declarations.push({kind: "model", name: model[1]});
      continue;
    }
    const [command, name, ...nodes] = line.split(/\s+/);
    if (command.toLowerCase() === ".subckt" && namePattern.test(name ?? "") &&
        nodes.length === 3 && new Set(nodes.map(node => node.toLowerCase())).size === 3)
      declarations.push({kind: "subckt", name, nodes});
  }
  return declarations;
}

function selectedSetupDeclaration() {
  const choice = get("setup-model-declaration").value;
  return choice === "" ? null : setupFile?.declarations[Number(choice)];
}

function setupProfile() {
  const state = setupFile;
  const model = selectedSetupDeclaration();
  const label = get("setup-model-label").value.trim();
  const source = get("setup-model-source").value.trim();
  const sha256 = state?.hash ?? (state?.manual ? get("setup-hash-input").value.trim().toLowerCase() : "");
  if (!model || !label || !source || !hexSHA256.test(sha256)) return null;
  const profile = {id: model.name.toLowerCase() + "-" + sha256.slice(0, 12), name: label,
    classification: get("setup-classification").value, source, model_file: state.name,
    model_name: model.name, kind: model.kind, sha256};
  if (model.kind === "subckt") {
    const pins = [...get("setup-pin-options").querySelectorAll("select")].map(select => select.value);
    if (!get("setup-pin-confirm").checked || !["B", "C", "E"].every(pin => pins.includes(pin))) return null;
    profile.pins = pins;
  }
  return profile;
}

function updateSetupProfile() {
  get("setup-instructor-note").hidden = get("setup-classification").value !== "instructor";
  get("setup-profile-download").disabled = !setupProfile();
}

function updateSetupPins() {
  const model = selectedSetupDeclaration();
  const holder = get("setup-pin-options");
  holder.replaceChildren();
  get("setup-pin-confirm").checked = false;
  get("setup-pin-field").hidden = model?.kind !== "subckt";
  for (const node of model?.nodes ?? []) {
    const label = element("label", "ขา " + node);
    const select = element("select");
    select.append(new Option("เลือก B/C/E", ""), ...["B", "C", "E"].map(pin => new Option(pin, pin)));
    label.append(select);
    holder.append(label);
  }
  updateSetupProfile();
}

async function readSetupModel(file) {
  const ticket = ++setupFileRevision;
  const message = get("setup-profile-message");
  setupFile = null;
  get("setup-profile-download").disabled = true;
  get("setup-model-fields").hidden = true;
  get("setup-hash-value").textContent = "";
  get("setup-hash-input").value = "";
  get("setup-model-source").value = "";
  get("setup-classification").value = "provisional";
  message.textContent = "";
  if (!file) return;
  if (file.size === 0 || file.size > setupFileLimit) {
    message.textContent = "เลือกไฟล์โมเดลที่มีข้อมูลและขนาดไม่เกิน 1 MiB";
    return;
  }
  if (/[.\s]$|[<>:"/\\|?*\x00-\x1f]/.test(file.name)) {
    message.textContent = "แก้ชื่อไฟล์โมเดลให้เป็นชื่อปกติ แล้วเลือกไฟล์อีกครั้ง";
    return;
  }
  message.textContent = "กำลังอ่านไฟล์บนเครื่อง";
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (ticket !== setupFileRevision) return;
    if (bytes.some(byte => byte === 0 || byte > 127)) {
      message.textContent = "ไฟล์นี้อ่านเป็นข้อความ SPICE แบบ ASCII ไม่ได้";
      return;
    }
    const declarations = setupDeclarations(new TextDecoder().decode(bytes));
    if (!declarations.length) {
      message.textContent = "ไม่พบ .MODEL NPN หรือ .SUBCKT ที่มีขาสามขาในไฟล์นี้";
      return;
    }
    let hash = null;
    if (window.isSecureContext && window.crypto?.subtle) {
      try {
        const digest = await window.crypto.subtle.digest("SHA-256", bytes);
        hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
      } catch {
        // The command below remains usable when the browser cannot calculate the digest.
      }
    }
    if (ticket !== setupFileRevision) return;
    setupFile = {name: file.name, declarations, hash, manual: hash === null};
    get("setup-model-declaration").replaceChildren(
      ...(declarations.length === 1 ? [] : [new Option("เลือกชื่อโมเดล", "")]),
      ...declarations.map((model, index) => new Option(model.name + " · " +
        (model.kind === "model" ? ".MODEL NPN" : ".SUBCKT"), String(index))),
    );
    get("setup-model-label").value = declarations.length === 1 ? declarations[0].name : "";
    get("setup-manual-hash").hidden = hash !== null;
    get("setup-hash-value").textContent = hash ? "SHA-256 · " + hash : "";
    get("setup-model-fields").hidden = false;
    updateSetupPins();
    message.textContent = hash ? "ตรวจชื่อและแหล่งที่มาก่อนดาวน์โหลด" : "คำนวณ SHA-256 ด้วยคำสั่งด้านบนเพื่อสร้างโปรไฟล์";
  } catch {
    if (ticket === setupFileRevision) message.textContent = "เปิดไฟล์โมเดลไม่ได้ ลองเลือกไฟล์อีกครั้ง";
  }
}

// Read and inspect selected files in the browser. Only the selected model reaches Flask.
const starterLimits = {
    files: 96,
    selectedBytes: 12 * 1024 * 1024,
    expandedBytes: 16 * 1024 * 1024,
    textBytes: 256 * 1024,
    modelChars: 8500,
};

function starterPath(path) {
    if (typeof path !== 'string' || path.length > 512 || /[\\:\u0000-\u001f\u007f]/.test(path)) {
        throw new Error('พบชื่อไฟล์ที่อ่านไม่ได้หรือมีเส้นทางที่ไม่รองรับ');
    }
    const parts = path.normalize('NFC').split('/');
    if (parts.some(part => !part.trim() || part === '.' || part === '..')) {
        throw new Error('พบเส้นทางไฟล์ที่ออกนอกชุดที่เลือก');
    }
    return parts.join('/');
}

function starterFileKind(path) {
    if (/\.zip$/i.test(path)) return 'archive';
    if (/\.(?:pdf|docx?|odt|rtf|pptx?|xlsx?|md|html?|png|jpe?g|webp|svg|gif|bmp|ico)$/i.test(path)) return 'document';
    if (/\.(?:raw|log|csv|tsv|dat|out)$/i.test(path)) return 'output';
    if (/\.(?:exe|msi|dll|so|dylib|bin|7z|rar|tar|gz|bz2|xz)$/i.test(path)) return 'binary';
    return 'text';
}

function starterDecode(data) {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(data);
    if (/[\u0000-\u0008\u000b\u000e-\u001f\u007f]/.test(text)) throw new Error('Not text');
    return text;
}

function starterChecksum(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) {
        crc ^= byte;
        for (let bit = 0; bit < 8; bit += 1) {
            crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
        }
    }
    return (~crc) >>> 0;
}

function starterZipEntries(bytes) {
    const badZip = () => new Error('อ่าน ZIP ไม่ได้ ไฟล์อาจไม่สมบูรณ์หรือใช้รูปแบบที่ไม่รองรับ');
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const u16 = at => view.getUint16(at, true);
    const u32 = at => view.getUint32(at, true);
    let end = bytes.length - 22;
    const minEnd = Math.max(0, end - 65535);
    while (end >= minEnd && (u32(end) !== 0x06054b50 || end + 22 + u16(end + 20) !== bytes.length)) end -= 1;
    if (end < minEnd) throw badZip();
    const count = u16(end + 10);
    const central = u32(end + 16);
    if (u16(end + 4) || u16(end + 6) || u16(end + 8) !== count || central + u32(end + 12) !== end) throw badZip();
    if (count > starterLimits.files) throw new Error('ZIP มีรายการเกิน 96 รายการ');

    const members = [];
    const paths = new Set();
    let at = central;
    for (let index = 0; index < count; index += 1) {
        if (at + 46 > end || u32(at) !== 0x02014b50) throw badZip();
        const flags = u16(at + 8);
        const method = u16(at + 10);
        const crc = u32(at + 16);
        const packed = u32(at + 20);
        const size = u32(at + 24);
        const nameSize = u16(at + 28);
        const nameAt = at + 46;
        const nameEnd = nameAt + nameSize;
        const local = u32(at + 42);
        const mode = (u32(at + 38) >>> 16) & 0xf000;
        const next = nameEnd + u16(at + 30) + u16(at + 32);
        if (next > end || u16(at + 34) || (flags & ~(method === 8 ? 0x080e : 0x0808)) || ![0, 8].includes(method)) throw badZip();
        const name = starterDecode(bytes.subarray(nameAt, nameEnd));
        const directory = name.endsWith('/');
        const path = starterPath(directory ? name.slice(0, -1) : name);
        const pathKey = path.toLowerCase();
        if (paths.has(pathKey)) throw badZip();
        paths.add(pathKey);
        if ((mode && mode !== (directory ? 0x4000 : 0x8000)) || (directory && size)) throw badZip();
        if (local + 30 > central || u32(local) !== 0x04034b50 || u16(local + 6) !== flags || u16(local + 8) !== method || u16(local + 26) !== nameSize) throw badZip();
        const localName = local + 30;
        const dataAt = localName + nameSize + u16(local + 28);
        let dataEnd = dataAt + packed;
        if (dataEnd > central || (method === 0 && packed !== size)) throw badZip();
        if (!bytes.subarray(nameAt, nameEnd).every((byte, i) => byte === bytes[localName + i])) throw badZip();
        const matchesValues = offset => u32(offset) === crc && u32(offset + 4) === packed && u32(offset + 8) === size;
        if (flags & 8) {
            if (dataEnd + 16 <= central && u32(dataEnd) === 0x08074b50 && matchesValues(dataEnd + 4)) dataEnd += 16;
            else if (dataEnd + 12 <= central && matchesValues(dataEnd)) dataEnd += 12;
            else throw badZip();
        } else if (!matchesValues(local + 14)) {
            throw badZip();
        }
        members.push({ path, directory, method, crc, packed, size, local, dataAt, dataEnd });
        at = next;
    }
    if (at !== end) throw badZip();
    let previousEnd = 0;
    for (const entry of [...members].sort((a, b) => a.local - b.local)) {
        if (entry.local < previousEnd) throw badZip();
        previousEnd = entry.dataEnd;
    }
    return members;
}

async function starterUnpack(data, member) {
    if (member.method === 0) return data;
    let decompressor;
    try {
        decompressor = new DecompressionStream('deflate-raw');
    } catch {
        throw new Error('เบราว์เซอร์นี้อ่าน ZIP แบบบีบอัดไม่ได้ กรุณาแตก ZIP แล้วเลือกไฟล์หรือโฟลเดอร์');
    }
    const reader = new Blob([data]).stream().pipeThrough(decompressor).getReader();
    const result = new Uint8Array(member.size);
    let offset = 0;
    try {
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            if (offset + value.length > result.length) {
                await reader.cancel();
                throw new Error('Unexpected expanded size');
            }
            result.set(value, offset);
            offset += value.length;
        }
        if (offset !== result.length) throw new Error('Unexpected expanded size');
    } catch {
        throw new Error('แตกข้อมูลใน ZIP ไม่สำเร็จ');
    } finally {
        reader.releaseLock();
    }
    return result;
}

async function readStarterEntries(files) {
    const selected = Array.from(files);
    if (selected.length > starterLimits.files || selected.reduce((sum, file) => sum + file.size, 0) > starterLimits.selectedBytes) {
        throw new Error('เลือกได้ไม่เกิน 96 ไฟล์ ขนาดรวมไม่เกิน 12 MiB');
    }
    const entries = [];
    const paths = new Set();
    const selectedPaths = new Set();
    let expandedBytes = 0;
    async function add(path, size, read) {
        expandedBytes += size;
        if (entries.length >= starterLimits.files || expandedBytes > starterLimits.expandedBytes) throw new Error('ชุดที่คลายแล้วเกิน 96 ไฟล์หรือ 16 MiB');
        const key = path.toLowerCase();
        if (paths.has(key)) throw new Error(`ชื่อไฟล์ซ้ำในชุดที่เลือก · ${path}`);
        paths.add(key);
        let kind = starterFileKind(path);
        let text = null;
        if (kind === 'text' && size <= starterLimits.textBytes) {
            const data = await read();
            try {
                text = starterDecode(data);
            } catch {
                kind = 'binary';
            }
        } else if (kind === 'text') {
            kind = 'binary';
        }
        entries.push({ path, text, size, kind });
    }

    for (const file of selected) {
        const path = starterPath(file.webkitRelativePath || file.name);
        const pathKey = path.toLowerCase();
        if (selectedPaths.has(pathKey)) throw new Error(`ชื่อไฟล์ซ้ำในชุดที่เลือก · ${path}`);
        selectedPaths.add(pathKey);
        const read = async () => {
            const bytes = new Uint8Array(await file.arrayBuffer());
            if (bytes.length !== file.size) throw new Error(`ขนาดไฟล์ไม่ตรง · ${path}`);
            return bytes;
        };
        if (starterFileKind(path) !== 'archive') {
            await add(path, file.size, read);
            continue;
        }
        const bytes = await read();
        const members = starterZipEntries(bytes).filter(member => !member.directory);
        if (entries.length + members.length > starterLimits.files || expandedBytes + members.reduce((sum, member) => sum + member.size, 0) > starterLimits.expandedBytes) {
            throw new Error('ชุดที่คลายแล้วเกิน 96 ไฟล์หรือ 16 MiB');
        }
        for (const member of members) {
            await add(starterPath(`${path}/${member.path}`), member.size, async () => {
                const data = await starterUnpack(bytes.subarray(member.dataAt, member.dataAt + member.packed), member);
                if (starterChecksum(data) !== member.crc) throw new Error(`ข้อมูลใน ZIP ไม่ตรงกับรายการไฟล์ · ${member.path}`);
                return data;
            });
        }
        if (!members.length) await add(path, 0, read);
    }
    return entries;
}

function starterReferences(entry) {
    const references = [];
    for (const line of (entry.text || '').split(/\r\n?|\n/)) {
        const directive = /^\s*\.(include|inc|lib)\s+(?:"([^"]+)"|'([^']+)'|(\S+))(.*)$/i.exec(line);
        if (!directive) continue;
        const [, command, doubleQuoted, singleQuoted, bare, remainder] = directive;
        if (command.toLowerCase() === 'lib' && !/^\s+[^$;\s]/.test(remainder)) continue;
        references.push({ reference: doubleQuoted || singleQuoted || bare, library: command.toLowerCase() === 'lib' });
    }
    return references;
}

function starterLookup(entries, entry, reference) {
    const relative = reference.replace(/\\/g, '/');
    if (relative.startsWith('/') || /[:\u0000-\u001f\u007f]/.test(relative)) return { status: 'outside' };
    const parts = entry.path.split('/').slice(0, -1);
    const rootDepth = parts.reduce((depth, part, index) => /\.zip$/i.test(part) ? index + 1 : depth, 0);
    for (const part of relative.normalize('NFC').split('/')) {
        if (part === '.') continue;
        if (!part.trim()) return { status: 'outside' };
        if (part === '..') {
            if (parts.length <= rootDepth) return { status: 'outside' };
            parts.pop();
        } else {
            parts.push(part);
        }
    }
    const path = parts.join('/').toLowerCase();
    const exact = entries.filter(candidate => candidate.path.toLowerCase() === path);
    if (exact.length === 1) return { entry: exact[0] };
    return { status: exact.length ? 'ambiguous' : 'missing' };
}

function starterIncludeIssues(entries, entry) {
    return starterReferences(entry).flatMap(({ reference }) => {
        const match = starterLookup(entries, entry, reference);
        return match.entry?.kind === 'text' ? [] : [{ reference, status: match.status || 'missing', path: entry.path }];
    });
}

function starterDeclarations(entry) {
    const models = [];
    const subcircuits = [];
    const lines = (entry.text || '').split(/\r\n?|\n/).map(line => line.trim().replace(/\s+(?:\$|\/\/).*$/, ''))
        .filter(line => line && !line.startsWith('*') && !line.startsWith('$') && !line.startsWith('//'));
    let subcircuit = null;
    let librarySection = false;
    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index].trim();
        const lib = /^\.lib\s+\S+\s*(?:[$;].*)?$/i.test(line);
        if (!subcircuit && lib) librarySection = true;
        if (!subcircuit && /^\.endl(?:\s|$)/i.test(line)) librarySection = false;
        const model = /^\.model\s+([^\s(]+)\s+npn(?=\s|\(|$)/i.exec(line);
        if (model) {
            const start = index;
            while (/^\s*\+/.test(lines[index + 1] || '')) index += 1;
            const item = { name: model[1], text: lines.slice(start, index + 1).join('\n').trim(), librarySection };
            (subcircuit ? subcircuit.localModels : models).push(item);
        }
        const begin = /^\.subckt\s+(\S+)(.*)$/i.exec(line);
        if (begin) {
            if (subcircuit) subcircuit.nested = true;
            else subcircuit = { name: begin[1], nodes: begin[2].trim().split(/\s+/).filter(Boolean), start: index, localModels: [], librarySection };
        }
        if (subcircuit && /^\.ends(?:\s|$)/i.test(line)) {
            subcircuits.push({ ...subcircuit, text: lines.slice(subcircuit.start, index + 1).join('\n').trim() });
            subcircuit = null;
        }
    }
    if (subcircuit) subcircuits.push({ ...subcircuit, unclosed: true });
    return { models, subcircuits };
}

function starterModels(entries) {
    const declarations = new Map(entries.filter(entry => entry.kind === 'text').map(entry => [entry, starterDeclarations(entry)]));
    const references = new Map([...declarations.keys()].map(entry => [entry, starterReferences(entry)]));
    const candidates = [];
    function add(entry, { name, nodes = [], text }, kind, dependencies = [], missing = [], error = null) {
        if (candidates.length >= 128) throw new Error('พบโมเดลเกิน 128 รายการ กรุณาเลือกเฉพาะชุดวงจรที่จะใช้');
        if (!error && !/^[a-z0-9][a-z0-9_.-]{0,63}$/i.test(name)) error = 'ชื่อโมเดลใช้ได้เฉพาะอักขระ ASCII ตามรูปแบบ SPICE และไม่เกิน 64 ตัวอักษร';
        if (!error && (!text || text.length > starterLimits.modelChars || /[^\x09\x0a\x20-\x7e]/.test(text))) {
            error = 'โมเดลที่เลือกต้องเป็นข้อความ ASCII ขนาดไม่เกิน 8,500 ตัวอักษร';
        }
        candidates.push({ id: String(candidates.length), path: entry.path, name, kind, nodes, dependencies, missing, error, text: error ? null : text });
    }

    for (const [entry, { models, subcircuits }] of declarations) {
        for (const model of models) add(entry, model, 'model');
        for (const circuit of subcircuits) {
            if (circuit.unclosed || circuit.nested || circuit.nodes.length !== 3 || new Set(circuit.nodes.map(node => node.toLowerCase())).size !== 3) {
                add(entry, circuit, 'subckt', [], [], 'ต้องเป็น subcircuit สามขาที่ปิดด้วย .ENDS และไม่มี subcircuit ซ้อน');
                continue;
            }
            const transistor = circuit.text.split('\n').map(line => /^\s*Q\S+\s+\S+\s+\S+\s+\S+\s+(\S+)\s*(?:[$;].*)?$/i.exec(line)).filter(Boolean);
            if (transistor.length !== 1 || starterReferences(circuit).length) {
                add(entry, circuit, 'subckt', [], [], 'ต้องมี Q แบบ NPN หนึ่งตัวและไม่มีคำสั่งอ้างไฟล์ในตัว subcircuit');
                continue;
            }
            const requiredName = transistor[0][1].toLowerCase();
            const files = [entry];
            const missing = [];
            for (const file of files) {
                for (const { reference, library } of references.get(file)) {
                    const match = starterLookup(entries, file, reference);
                    if (library || !declarations.has(match.entry)) missing.push(reference);
                    else if (!files.includes(match.entry)) files.push(match.entry);
                }
            }
            const local = circuit.localModels.filter(model => model.name.toLowerCase() === requiredName);
            const external = files.flatMap(file => declarations.get(file).models.filter(model => !model.librarySection && model.name.toLowerCase() === requiredName).map(model => ({ model, file })));
            if (local.length === 1 || (!local.length && external.length === 1 && !missing.length)) {
                const dependency = local.length ? null : external[0];
                const dependencies = dependency && dependency.file !== entry ? [dependency.file.path] : [];
                const text = dependency ? `${circuit.text}\n${dependency.model.text}` : circuit.text;
                add(entry, { ...circuit, text }, 'subckt', dependencies);
            } else {
                const error = local.length > 1 || external.length > 1 ? 'พบโมเดล NPN ชื่อนี้มากกว่าหนึ่งรายการ' : `ยังยืนยันโมเดล NPN ที่ Q อ้างถึงไม่ได้ · ${transistor[0][1]}`;
                add(entry, circuit, 'subckt', [], [...new Set(missing.length ? missing : [transistor[0][1]])], error);
            }
        }
    }
    return candidates;
}

const starterContexts = {
  text: "ข้อความ SPICE หรือไฟล์ประกอบ", document: "เอกสารประกอบ", output: "ข้อมูลผลตัวอย่าง",
  binary: "ไฟล์ที่ใช้ประกอบการอ่าน", archive: "ไฟล์ ZIP ที่ซ้อนอยู่",
};
const starterIncludeLabels = {missing: "ขาดไฟล์", ambiguous: "พบไฟล์ชื่อเดียวกัน", outside: "พาธอยู่นอกชุดที่เลือก"};
let starterEntries = [], starterCandidates = [];
let starterRead = null, starterCheck = null;

function starterSelection() {
  return starterCandidates.find(item => item.id === get("starter-model").value);
}

function starterSubmission() {
  const selected = starterSelection();
  const name = get("starter-name").value.trim();
  const source = get("starter-source").value.trim();
  if (!selected?.text || selected.error || !name || !source) return null;
  const {kind, text} = selected;
  const model = {kind, text, name, source, model_name: selected.name, classification: get("starter-classification").value};
  if (kind === "subckt") {
    const pins = [...get("starter-pin-options").querySelectorAll("select")].map(select => select.value);
    if (!get("starter-pin-confirm").checked || !["B", "C", "E"].every(pin => pins.includes(pin))) return null;
    model.pins = pins;
  }
  return model;
}

function refreshStarterButton() {
  const button = get("starter-check-use");
  button.disabled = Boolean(starterRead || starterCheck) || !starterSubmission();
  button.textContent = starterCheck ? "กำลังทดสอบโมเดล" : "ทดสอบและใช้โมเดลนี้";
}

function clearStarterCheck() {
  starterCheck?.abort();
  starterCheck = null;
  get("starter-check-status").textContent = "";
  renderSetupSteps(get("starter-steps"), []);
}

function renderStarterCandidate() {
  clearStarterCheck();
  const selected = starterSelection();
  const detail = get("starter-model-detail");
  detail.textContent = selected ? [selected.path, selected.error, ...selected.missing.map(file => "ขาดไฟล์ " + file),
    ...selected.dependencies.map(file => "ใช้ไฟล์ " + file)].filter(Boolean).join(" · ") : "";
  get("starter-name").value = selected?.name.slice(0, 120) ?? "";
  get("starter-pin-field").hidden = selected?.kind !== "subckt";
  get("starter-pin-confirm").checked = false;
  const holder = get("starter-pin-options");
  holder.replaceChildren();
  for (const node of selected?.nodes ?? []) {
    const label = element("label", "ขา " + node);
    const select = element("select");
    select.append(new Option("เลือก B/C/E", ""), ...["B", "C", "E"].map(pin => new Option(pin, pin)));
    label.append(select);
    holder.append(label);
  }
  refreshStarterButton();
}

function renderStarterEntries() {
  const issues = [];
  const rows = starterEntries.map(entry => {
    const notes = entry.kind === "text" ? starterIncludeIssues(starterEntries, entry) : [];
    issues.push(...notes);
    return element("li", [entry.path, starterContexts[entry.kind], ...notes.map(note =>
      starterIncludeLabels[note.status] + " " + note.reference)].join(" · "));
  });
  get("starter-files-list").replaceChildren(...rows);
  const inspection = get("starter-inspection");
  inspection.hidden = !rows.length;
  inspection.open = Boolean(rows.length && (!starterCandidates.length || issues.length));
  get("starter-clear-intake").hidden = !rows.length;
  get("starter-inspection-title").textContent = "ไฟล์และการตรวจเบื้องต้น · " + rows.length + " ไฟล์";
  get("starter-form").hidden = !starterCandidates.length;
  get("starter-model").replaceChildren(
    ...(starterCandidates.length > 1 ? [new Option("เลือกชื่อโมเดล", "")] : []),
    ...starterCandidates.map(item => new Option(item.name + " · " +
      (item.kind === "model" ? ".MODEL NPN" : ".SUBCKT") + " · " + item.path, item.id)),
  );
  renderStarterCandidate();
}

async function addStarterEntries(load, source = "") {
  if (starterRead) {
    get("starter-intake-status").textContent = "รอให้อ่านไฟล์ชุดปัจจุบันเสร็จก่อน แล้วเพิ่มไฟล์ชุดถัดไป";
    return false;
  }
  clearStarterCheck();
  const request = new AbortController();
  starterRead = request;
  const message = get("starter-intake-status");
  message.textContent = "กำลังอ่านไฟล์ในเบราว์เซอร์";
  get("starter-clear-intake").hidden = false;
  refreshStarterButton();
  try {
    const loaded = await readStarterEntries(await load(request.signal));
    if (starterRead !== request) return false;
    const merged = new Map(starterEntries.map(entry => [entry.path.toLowerCase(), entry]));
    for (const entry of loaded) {
      const existing = merged.get(entry.path.toLowerCase());
      if (existing && (entry.path !== existing.path || entry.text !== existing.text || entry.kind !== existing.kind || entry.size !== existing.size))
        throw new Error("พบไฟล์พาธซ้ำที่อ่านได้ต่างกัน · " + entry.path + " ล้างรายการก่อนเลือกไฟล์ชุดใหม่");
      merged.set(entry.path.toLowerCase(), entry);
    }
    const entries = [...merged.values()];
    if (entries.length > 96 || entries.reduce((total, entry) => total + entry.size, 0) > 16 * 1024 * 1024)
      throw new Error("ชุดที่เปิดได้รวมไม่เกิน 96 ไฟล์และ 16 MiB หลังแตก ZIP");
    const candidates = starterModels(entries);
    starterEntries = entries;
    starterCandidates = candidates;
    if (source && !get("starter-source").value.trim()) get("starter-source").value = source.slice(0, 250);
    renderStarterEntries();
    message.textContent = starterCandidates.length ? "พบ " + starterCandidates.length + " โมเดล เลือกแล้วตรวจแหล่งที่มาก่อนทดสอบ" :
      "ยังไม่พบ .MODEL NPN หรือ .SUBCKT สามขาในไฟล์ที่อ่านได้";
    return true;
  } catch (error) {
    if (starterRead === request) message.textContent = error instanceof Error ? error.message : "อ่านไฟล์ Starter Kit ไม่สำเร็จ";
    return false;
  } finally {
    if (starterRead === request) {
      starterRead = null;
      get("starter-clear-intake").hidden = !starterEntries.length;
      refreshStarterButton();
    }
  }
}

async function readStarterUrl(url, signal) {
  const limit = 12 * 1024 * 1024;
  const unavailable = "อ่านไฟล์จากลิงก์นี้ไม่ได้ ใช้ลิงก์ไฟล์ปลายทางโดยตรงหรือดาวน์โหลดมาเลือกจากเครื่อง";
  let response;
  try {
    response = await fetch(url, {signal, credentials: "omit", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer"});
  } catch {
    throw new Error(unavailable);
  }
  if (!response.ok || !response.body || /text\/html/i.test(response.headers.get("Content-Type") ?? "")) throw new Error(unavailable);
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) {
        await reader.cancel();
        throw new Error("ไฟล์จากลิงก์มีขนาดเกิน 12 MiB");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const filename = url.pathname.split("/").at(-1);
  return [new File(chunks, filename || "linked-model.cir")];
}

function changeStarterModel(starter) {
  activeStarter = starter;
  get("starter-active-model").textContent = starter ? "โมเดลที่ใช้ในแท็บนี้ · " + starter.receipt.profile.name : "โมเดลที่ใช้ · โมเดลตั้งต้นของระบบ";
  get("starter-reset-model").hidden = !starter;
  get("starter-download-receipt").hidden = !starter;
  clearDesign();
  baseline = null;
  reference = null;
  restorePoint = null;
  baselineNote("");
  beginAuto();
}

async function checkStarterModel(event) {
  event.preventDefault();
  const model = starterSubmission();
  if (!model || starterCheck || starterRead) return;
  clearStarterCheck();
  const request = new AbortController();
  starterCheck = request;
  const status = get("starter-check-status");
  status.textContent = "กำลังตรวจด้วย ngspice ทั้ง DC, AC และ Transient";
  refreshStarterButton();
  try {
    const report = await fetchJson("/api/spice/import/check", {model}, request.signal);
    if (request !== starterCheck) return;
    const steps = Array.isArray(report.steps) ? report.steps : [];
    renderSetupSteps(get("starter-steps"), steps);
    if (report.ok !== true) {
      status.textContent = report.message || setupMessage(report.code) || "โมเดลยังไม่ผ่านชุดตรวจ ดูผลรายขั้นด้านล่าง";
      return;
    }
    const profile = report.profile;
    if (typeof report.engine_version !== "string" || !report.engine_version ||
      steps.length !== Object.keys(setupLabels).length || !Object.keys(setupLabels).every(id =>
      steps.filter(step => step?.id === id && step.status === "PASS").length === 1) ||
      profile?.name !== model.name || profile?.model_name?.toLowerCase() !== model.model_name.toLowerCase() ||
      profile.kind !== model.kind || profile.classification !== model.classification || !hexSHA256.test(profile.sha256) ||
      JSON.stringify(profile.pins ?? []) !== JSON.stringify(model.pins ?? []))
      throw new Error("หลักฐานจากเครื่องจำลองไม่ครบหรือต่างจากโมเดลที่เลือก");
    if (window.isSecureContext && window.crypto?.subtle) {
      const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(model.text));
      if (request !== starterCheck) return;
      const hash = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, "0")).join("");
      if (hash !== profile.input_sha256) throw new Error("รหัส SHA-256 ของข้อมูลที่ส่งต่างจากหลักฐานที่ได้รับ");
    }
    const {name, model_name, kind, classification, sha256, input_sha256, pins} = profile;
    const receipt = {ok: true, engine_version: report.engine_version,
      profile: {name, model_name, kind, classification, source: model.source, sha256, input_sha256, pins},
      steps: steps.map(({id, status, code, version, value_v, run_id}) => ({id, status, code, version, value_v, run_id}))};
    changeStarterModel({model, receipt});
    status.textContent = "ผ่านชุดตรวจและเลือกใช้ในแท็บนี้แล้ว · ngspice รุ่น " + report.engine_version;
  } catch (error) {
    if (request === starterCheck) status.textContent = error instanceof TypeError || error instanceof SyntaxError ?
      "ติดต่อเครื่องจำลองไม่สำเร็จ ลองตรวจอีกครั้ง" : error.message;
  } finally {
    if (request === starterCheck) {
      starterCheck = null;
      refreshStarterButton();
    }
  }
}

for (const id of ["starter-files", "starter-folder"]) get(id).addEventListener("change", event => {
  const files = [...event.target.files];
  event.target.value = "";
  if (files.length) addStarterEntries(() => files);
});
const starterDrop = get("starter-drop");
starterDrop.addEventListener("dragover", event => {
  event.preventDefault();
  starterDrop.dataset.drag = "";
});
starterDrop.addEventListener("dragleave", event => {
  if (!starterDrop.contains(event.relatedTarget)) delete starterDrop.dataset.drag;
});
starterDrop.addEventListener("drop", event => {
  event.preventDefault();
  delete starterDrop.dataset.drag;
  const files = [...event.dataTransfer.files];
  if (files.length) addStarterEntries(() => files);
});
get("starter-add-paste").addEventListener("click", async () => {
  const field = get("starter-paste");
  const value = field.value;
  if (!value.trim()) return;
  const file = new File([value], "pasted-" + (starterEntries.length + 1) + ".cir");
  if (await addStarterEntries(() => [file]) && field.value === value) field.value = "";
});
get("starter-add-url").addEventListener("click", () => {
  const field = get("starter-url");
  const message = get("starter-intake-status");
  let url;
  try {
    url = new URL(field.value.trim());
  } catch {
    message.textContent = "กรอกลิงก์ HTTPS ของไฟล์ให้ครบ";
    return;
  }
  if (url.protocol !== "https:" || url.username || url.password) {
    message.textContent = "ใช้ลิงก์ HTTPS ที่เปิดไฟล์ได้โดยไม่ต้องลงชื่อเข้าใช้";
    return;
  }
  addStarterEntries(signal => readStarterUrl(url, signal), url.origin + url.pathname);
});
get("starter-clear-intake").addEventListener("click", () => {
  starterRead?.abort();
  starterRead = null;
  starterEntries = [];
  starterCandidates = [];
  for (const id of ["starter-source", "starter-paste", "starter-url"]) get(id).value = "";
  get("starter-classification").value = "provisional";
  renderStarterEntries();
  get("starter-intake-status").textContent = "";
});
get("starter-form").addEventListener("input", event => {
  if (event.target === get("starter-model")) renderStarterCandidate();
  else {
    clearStarterCheck();
    if (event.target.closest("#starter-pin-options")) get("starter-pin-confirm").checked = false;
    refreshStarterButton();
  }
});
get("starter-form").addEventListener("submit", checkStarterModel);
get("starter-reset-model").addEventListener("click", () => {
  clearStarterCheck();
  changeStarterModel(null);
  refreshStarterButton();
});
get("starter-download-receipt").addEventListener("click", () => {
  if (activeStarter) chooseResultFiles([JSON.stringify(activeStarter.receipt, null, 2) + "\n"], "lab04-starter-check.json", "application/json");
});

get("setup-refresh").addEventListener("click", refreshSetup);
get("setup-check").addEventListener("click", checkSetup);
get("setup-model-file").addEventListener("change", event => readSetupModel(event.target.files[0]));
get("setup-model-declaration").addEventListener("change", updateSetupPins);
get("setup-profile-form").addEventListener("input", updateSetupProfile);
get("setup-profile-form").addEventListener("submit", event => {
  event.preventDefault();
  const profile = setupProfile();
  if (!profile || setupHealth?.mode !== "local") return;
  chooseResultFiles([JSON.stringify(profile, null, 2) + "\n"], "profile.json", "application/json");
  get("setup-profile-message").textContent = "วาง profile.json ไว้ข้างไฟล์โมเดล จากนั้นทำขั้น 3";
});
for (const button of document.querySelectorAll("[data-copy-setup]")) {
  button.addEventListener("click", async () => {
    const command = get(button.dataset.copySetup);
    const message = get("setup-copy-message");
    try {
      await navigator.clipboard.writeText(command.textContent);
      message.textContent = "คัดลอกคำสั่งแล้ว แทนพาธตัวอย่างด้วยตำแหน่งจริง";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(command);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      message.textContent = "เลือกคำสั่งไว้แล้ว ใช้คำสั่งคัดลอกของเบราว์เซอร์";
    }
  });
}

get("run").disabled = false;
updateControls();
renderSaved();
setSchematic();
refreshSetup();
beginAuto();
