const canvas = document.getElementById("scope");
const ctx = canvas.getContext("2d");
const tickerSelect = document.getElementById("tickerSelect");
const symbolInput = document.getElementById("symbolInput");
const addSymbolButton = document.getElementById("addSymbolButton");
const timebaseSelect = document.getElementById("timebaseSelect");
const timebaseKnob = document.getElementById("timebaseKnob");
const statusTicker = document.getElementById("statusTicker");
const statusTimebase = document.getElementById("statusTimebase");
const statusPrice = document.getElementById("statusPrice");

const TOTAL_SAMPLES = 520;
const SERIES = buildSeries();
let traceStep = 0;

function buildSeries() {
  const seeds = {
    AAPL: 165,
    MSFT: 300,
    NVDA: 420,
    TSLA: 240,
    SPY: 470,
  };

  const output = {};

  Object.entries(seeds).forEach(([symbol, base]) => {
    output[symbol] = makeSyntheticSeries(base, symbol);
  });

  return output;
}

function hashSymbol(symbol) {
  return symbol.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
}

function makeSyntheticSeries(base, symbol) {
  const symbolHash = hashSymbol(symbol);
  let value = base;

  return Array.from({ length: TOTAL_SAMPLES }, (_, index) => {
    const wobble = Math.sin(index / 9 + symbolHash / 30) * 1.2 + Math.cos(index / 27 + symbolHash / 40) * 0.9;
    const drift = Math.sin(index / 5 + symbolHash / 10) * 0.85 + Math.cos(index / 13 + symbolHash / 12) * 0.55;
    value = Math.max(18, value + wobble * 0.45 + drift);
    return Number(value.toFixed(2));
  });
}

function estimateSeedPrice(symbol) {
  const symbolHash = hashSymbol(symbol);
  return 80 + (symbolHash % 420);
}

function normalizeSymbol(raw) {
  return raw.trim().toUpperCase().replace(/[^A-Z0-9.\-]/g, "").slice(0, 8);
}

function addSymbol(symbol) {
  if (SERIES[symbol]) {
    tickerSelect.value = symbol;
    return;
  }

  SERIES[symbol] = makeSyntheticSeries(estimateSeedPrice(symbol), symbol);

  const option = document.createElement("option");
  option.value = symbol;
  option.textContent = symbol;
  tickerSelect.append(option);
  tickerSelect.value = symbol;
  traceStep = 0;
}

function handleAddSymbol() {
  const symbol = normalizeSymbol(symbolInput.value);
  if (!symbol) return;

  addSymbol(symbol);
  symbolInput.value = "";
  symbolInput.focus();
}

function labelForSamples(sampleCount) {
  if (sampleCount <= 24) return "1 Day";
  if (sampleCount <= 120) return "1 Week";
  if (sampleCount <= 260) return "1 Month";
  if (sampleCount <= 390) return "3 Months";
  return "1 Year";
}

function syncTimebase(choice) {
  const value = Number(choice);
  timebaseSelect.value = String(value);
  timebaseKnob.value = String(value);
}

function getVisibleSeries() {
  const ticker = tickerSelect.value;
  const requested = Number(timebaseKnob.value);
  const data = SERIES[ticker] || SERIES.AAPL;
  return data.slice(-requested);
}

function drawGrid() {
  const { width, height } = canvas;
  ctx.strokeStyle = "rgba(80, 180, 110, 0.14)";
  ctx.lineWidth = 1;

  for (let x = 0; x <= width; x += width / 12) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }

  for (let y = 0; y <= height; y += height / 8) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function drawWave(points, max, min) {
  const { width, height } = canvas;
  const xStep = width / (points.length - 1 || 1);
  const range = Math.max(max - min, 1);

  const coords = points.map((price, index) => {
    const x = index * xStep;
    const y = height - ((price - min) / range) * (height * 0.8) - height * 0.1;
    return { x, y, price };
  });

  ctx.save();
  ctx.strokeStyle = "rgba(125, 255, 140, 0.35)";
  ctx.lineWidth = 8;
  ctx.shadowBlur = 14;
  ctx.shadowColor = "rgba(125, 255, 140, 0.45)";

  ctx.beginPath();
  coords.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();

  ctx.strokeStyle = "#92ff9d";
  ctx.lineWidth = 2;
  ctx.shadowBlur = 12;
  ctx.shadowColor = "rgba(125, 255, 140, 0.9)";
  ctx.stroke();
  ctx.restore();

  const idx = traceStep % coords.length;
  const trace = coords[idx];

  ctx.save();
  ctx.beginPath();
  ctx.arc(trace.x, trace.y, 5.5, 0, Math.PI * 2);
  ctx.fillStyle = "#b5ffbc";
  ctx.shadowBlur = 15;
  ctx.shadowColor = "#b5ffbc";
  ctx.fill();
  ctx.restore();

  statusPrice.textContent = `Signal: ${trace.price.toFixed(2)} USD`;
}

function render() {
  const data = getVisibleSeries();
  const max = Math.max(...data);
  const min = Math.min(...data);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawGrid();
  drawWave(data, max, min);

  statusTicker.textContent = `Ticker: ${tickerSelect.value}`;
  statusTimebase.textContent = `Timebase: ${labelForSamples(data.length)} (${data.length} samples)`;

  traceStep += 1;
  requestAnimationFrame(render);
}

timebaseSelect.addEventListener("change", (event) => {
  syncTimebase(event.target.value);
});

timebaseKnob.addEventListener("input", (event) => {
  const value = Number(event.target.value);
  const snap = [24, 120, 260, 390, 520].reduce((prev, curr) =>
    Math.abs(curr - value) < Math.abs(prev - value) ? curr : prev
  );
  timebaseSelect.value = String(snap);
});

addSymbolButton.addEventListener("click", handleAddSymbol);
symbolInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    handleAddSymbol();
  }
});

tickerSelect.addEventListener("change", () => {
  traceStep = 0;
});

syncTimebase(520);
render();
