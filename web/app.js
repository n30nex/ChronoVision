const state = {
  refreshIntervalMs: 30000,
  lastUpdated: null,
  historyLimit: 12,
  historyQuery: "",
  descriptions: [],
  descriptionsLimit: 500,
  trendMode: "hourly",
  timelapse: {
    mode: "daily",
    date: "",
    index: 0,
    items: [],
    playing: false,
    timer: null,
  },
  ask: {
    enabled: true,
    lookbackHours: 24,
    maxItems: 40,
  },
};

const API_KEY_STORAGE = "snapshotVisionApiKey";

const elements = {
  health: document.getElementById("health-indicator"),
  latestImage: document.getElementById("latest-image"),
  latestTime: document.getElementById("latest-time"),
  latestDescription: document.getElementById("latest-description"),
  latestTags: document.getElementById("latest-tags"),
  previewImage: document.getElementById("preview-image"),
  previewTime: document.getElementById("preview-time"),
  activeIndicator: document.getElementById("active-indicator"),
  activeDot: document.getElementById("active-dot"),
  activeLabel: document.getElementById("active-label"),
  activeTime: document.getElementById("active-time"),
  activeTags: document.getElementById("active-tags"),
  askCard: document.getElementById("ask-card"),
  askQuery: document.getElementById("ask-query"),
  askRun: document.getElementById("ask-run"),
  askResponse: document.getElementById("ask-response"),
  askWindow: document.getElementById("ask-window"),
  trendList: document.getElementById("trend-list"),
  trendButtons: document.querySelectorAll(".pill[data-trend]"),
  lastUpdated: document.getElementById("last-updated"),
  compare10m: document.getElementById("compare-10m"),
  compareHourly: document.getElementById("compare-hourly"),
  dailyReport: document.getElementById("daily-report"),
  dailyHighlights: document.getElementById("daily-highlights"),
  dailyTags: document.getElementById("daily-tags"),
  refreshBtn: document.getElementById("refresh-btn"),
  historyList: document.getElementById("history-list"),
  historySearch: document.getElementById("history-search"),
  historyMore: document.getElementById("history-more"),
  historyCount: document.getElementById("history-count"),
  timelapseDay: document.getElementById("timelapse-day"),
  timelapseRange: document.getElementById("timelapse-range"),
  timelapseTime: document.getElementById("timelapse-time"),
  timelapseCount: document.getElementById("timelapse-count"),
  timelapseImage: document.getElementById("timelapse-image"),
  timelapseDescription: document.getElementById("timelapse-description"),
  timelapseTags: document.getElementById("timelapse-tags"),
  timelapsePlay: document.getElementById("timelapse-play"),
  timelapseButtons: document.querySelectorAll(".pill[data-mode]"),
  compareSelectA: document.getElementById("compare-a"),
  compareSelectB: document.getElementById("compare-b"),
  compareRun: document.getElementById("compare-run"),
  compareImageA: document.getElementById("compare-image-a"),
  compareImageB: document.getElementById("compare-image-b"),
  compareTimeA: document.getElementById("compare-time-a"),
  compareTimeB: document.getElementById("compare-time-b"),
  compareResult: document.getElementById("compare-result"),
  costTotalTokens: document.getElementById("cost-total-tokens"),
  costTotalUsd: document.getElementById("cost-total-usd"),
  costProviders: document.getElementById("cost-providers"),
  costDays: document.getElementById("cost-days"),
};

const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

let apiKeyPromptOpen = false;
let apiKeyLastUpdated = 0;

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

function setApiKey(value) {
  const cleaned = String(value || "").trim();
  if (!cleaned) {
    localStorage.removeItem(API_KEY_STORAGE);
    apiKeyLastUpdated = 0;
    return "";
  }
  localStorage.setItem(API_KEY_STORAGE, cleaned);
  apiKeyLastUpdated = Date.now();
  return cleaned;
}

function promptForApiKey(message = "Enter API key for Snapshot Vision:") {
  if (apiKeyPromptOpen) {
    return "";
  }
  apiKeyPromptOpen = true;
  const input = window.prompt(message);
  apiKeyPromptOpen = false;
  if (input === null) return "";
  return setApiKey(input);
}

function withApiKey(url) {
  const apiKey = getApiKey();
  if (!apiKey) return url;
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set("api_key", apiKey);
    return `${parsed.pathname}${parsed.search}`;
  } catch (error) {
    return url;
  }
}

function setTextBlock(container, text, meta = null, metaClass = "subtle") {
  if (!container) return;
  container.replaceChildren();
  const message = document.createElement("p");
  message.textContent = text;
  container.appendChild(message);
  if (meta) {
    const metaEl = document.createElement("span");
    if (metaClass) {
      metaEl.className = metaClass;
    }
    metaEl.textContent = meta;
    container.appendChild(metaEl);
  }
}

async function fetchJson(url, options = {}, allowRetry = true) {
  const headers = new Headers(options.headers || {});
  const apiKey = getApiKey();
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }
  const response = await fetch(url, { cache: "no-store", ...options, headers });
  if (response.status === 401 && allowRetry) {
    const currentKey = getApiKey();
    if (currentKey && Date.now() - apiKeyLastUpdated < 5000) {
      return fetchJson(url, options, false);
    }
    const promptMessage = currentKey
      ? "API key invalid. Enter API key:"
      : "API key required. Enter API key:";
    const updatedKey = promptForApiKey(promptMessage);
    if (updatedKey) {
      return fetchJson(url, options, false);
    }
  }
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function formatTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function toDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function snapshotUrl(path) {
  if (!path) return "";
  if (path.startsWith("/data/")) return withApiKey(path);
  const trimmed = path.replace(/^\/+/, "");
  return withApiKey(`/data/${trimmed}`);
}

function setHealth(status) {
  elements.health.textContent = status;
  elements.health.classList.remove("healthy", "degraded", "unhealthy");
  elements.health.classList.add(status);
}

function renderTags(container, tags) {
  if (!container) return;
  container.innerHTML = "";
  if (!tags || typeof tags !== "object") return;
  const values = [
    ...(tags.people || []),
    ...(tags.vehicles || []),
    ...(tags.objects || []),
  ];
  if (values.length === 0) return;
  values.slice(0, 8).forEach((tag) => {
    const chip = document.createElement("span");
    chip.className = "tag";
    chip.textContent = tag;
    container.appendChild(chip);
  });
}

function renderTagSummary(container, summary) {
  if (!container) return;
  container.innerHTML = "";
  if (!summary || typeof summary !== "object") return;
  const entries = [];
  Object.entries(summary).forEach(([group, items]) => {
    if (!Array.isArray(items)) return;
    items.forEach(([label, count]) => {
      entries.push({ group, label, count });
    });
  });
  entries.slice(0, 8).forEach((entry) => {
    const chip = document.createElement("span");
    chip.className = "tag";
    chip.textContent = `${entry.group}: ${entry.label} (${entry.count})`;
    chip.dataset.tagValue = entry.label;
    chip.dataset.tagGroup = entry.group;
    container.appendChild(chip);
  });
}

function getTagValues(tags) {
  if (!tags || typeof tags !== "object") return [];
  return [
    ...(tags.people || []),
    ...(tags.vehicles || []),
    ...(tags.objects || []),
  ];
}

function tagsToText(tags) {
  return getTagValues(tags).join(" ").toLowerCase();
}

function setHistoryQuery(value) {
  const nextValue = String(value || "").trim();
  state.historyQuery = nextValue;
  state.historyLimit = 12;
  if (elements.historySearch) {
    elements.historySearch.value = nextValue;
  }
  renderHistory(state.descriptions);
}

function renderList(container, items, limit = 6) {
  container.replaceChildren();
  if (!Array.isArray(items) || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "list-item";
    const label = document.createElement("strong");
    label.textContent = "No entries yet";
    empty.appendChild(label);
    container.appendChild(empty);
    return;
  }
  const slice = items.slice(-limit).reverse();
  slice.forEach((item) => {
    const wrapper = document.createElement("div");
    wrapper.className = "list-item";
    const time = formatTime(item.timestamp || item.ts);
    const title = document.createElement("strong");
    title.textContent = item.text || "No data";
    const timestamp = document.createElement("span");
    timestamp.textContent = time;
    wrapper.appendChild(title);
    wrapper.appendChild(timestamp);
    container.appendChild(wrapper);
  });
}

function renderHistory(descriptions) {
  const query = state.historyQuery.trim().toLowerCase();
  const filtered = descriptions.filter((item) => {
    if (!query) return true;
    const textMatch = (item.text || "").toLowerCase().includes(query);
    const tagMatch = tagsToText(item.tags).includes(query);
    return textMatch || tagMatch;
  });

  const slice = filtered.slice(-state.historyLimit).reverse();
  elements.historyList.innerHTML = "";
  elements.historyCount.textContent = `${filtered.length} items`;

  if (descriptions.length === 0) {
    elements.historyList.innerHTML = "<div class=\"history-empty\">No snapshots yet.</div>";
    elements.historyMore.disabled = true;
    return;
  }

  if (filtered.length === 0) {
    elements.historyList.innerHTML = "<div class=\"history-empty\">No matches found.</div>";
    elements.historyMore.disabled = true;
    return;
  }

  slice.forEach((item) => {
    const card = document.createElement("article");
    card.className = "history-card";

    const imageWrap = document.createElement("div");
    imageWrap.className = "history-image";

    if (item.snapshot) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = snapshotUrl(item.snapshot);
      img.alt = `Snapshot ${formatTime(item.timestamp)}`;
      imageWrap.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "history-placeholder";
      placeholder.textContent = "No Image";
      imageWrap.appendChild(placeholder);
    }

    const body = document.createElement("div");
    body.className = "history-body";

    const text = document.createElement("p");
    text.textContent = item.text || "No description available.";

    const time = document.createElement("span");
    time.className = "history-time";
    time.textContent = formatTime(item.timestamp);

    const tagsWrap = document.createElement("div");
    tagsWrap.className = "tag-list";
    renderTags(tagsWrap, item.tags);

    body.appendChild(text);
    body.appendChild(time);
    if (tagsWrap.childElementCount > 0) {
      body.appendChild(tagsWrap);
    }

    card.appendChild(imageWrap);
    card.appendChild(body);
    elements.historyList.appendChild(card);
  });

  elements.historyMore.disabled = filtered.length <= state.historyLimit;
}

function buildTimelapseDates(descriptions) {
  const dates = new Set();
  descriptions.forEach((item) => {
    if (!item.timestamp) return;
    const date = new Date(item.timestamp);
    if (!Number.isNaN(date.getTime())) {
      dates.add(toDateKey(date));
    }
  });
  return Array.from(dates).sort();
}

function buildTimelapseItems(descriptions, mode, dateKey) {
  const filtered = descriptions.filter((item) => {
    if (!item.timestamp) return false;
    const date = new Date(item.timestamp);
    if (Number.isNaN(date.getTime())) return false;
    return toDateKey(date) === dateKey;
  });

  const sorted = filtered
    .slice()
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  if (mode === "hourly") {
    const byHour = new Map();
    sorted.forEach((item) => {
      const date = new Date(item.timestamp);
      const key = `${toDateKey(date)}-${date.getHours()}`;
      byHour.set(key, item);
    });
    return Array.from(byHour.values()).sort(
      (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
    );
  }

  return sorted;
}

function updateActiveNow(latestDescription) {
  if (!elements.activeIndicator || !elements.activeLabel || !elements.activeDot) return;
  if (!latestDescription) {
    elements.activeIndicator.textContent = "Offline";
    elements.activeLabel.textContent = "No recent tags";
    if (elements.activeTime) {
      elements.activeTime.textContent = "--";
    }
    elements.activeDot.className = "status-dot idle";
    if (elements.activeTags) {
      elements.activeTags.innerHTML = "<span class=\"subtle\">No tags yet.</span>";
    }
    return;
  }

  const peopleTags = latestDescription.tags?.people || [];
  const hasPeople = Array.isArray(peopleTags) && peopleTags.length > 0;
  elements.activeIndicator.textContent = hasPeople ? "People" : "Clear";
  elements.activeLabel.textContent = hasPeople ? "People present" : "No people detected";
  if (elements.activeTime) {
    elements.activeTime.textContent = formatTime(latestDescription.timestamp);
  }
  elements.activeDot.className = `status-dot ${hasPeople ? "active" : "idle"}`;
  if (elements.activeTags) {
    renderTags(elements.activeTags, latestDescription.tags);
    if (elements.activeTags.childElementCount === 0) {
      elements.activeTags.innerHTML = "<span class=\"subtle\">No tags yet.</span>";
    }
  }
}

function getTrendWindow(mode) {
  const now = new Date();
  if (mode === "daily") {
    const end = new Date(now);
    end.setHours(0, 0, 0, 0);
    const bucketCount = 7;
    const bucketMs = 24 * 60 * 60 * 1000;
    const start = new Date(end.getTime() - (bucketCount - 1) * bucketMs);
    return { start, bucketMs, bucketCount };
  }
  const end = new Date(now);
  end.setMinutes(0, 0, 0);
  const bucketCount = 24;
  const bucketMs = 60 * 60 * 1000;
  const start = new Date(end.getTime() - (bucketCount - 1) * bucketMs);
  return { start, bucketMs, bucketCount };
}

function buildTrendData(descriptions, mode) {
  const { start, bucketMs, bucketCount } = getTrendWindow(mode);
  const tagBuckets = {};
  const tagTotals = {};

  descriptions.forEach((item) => {
    if (!item.timestamp) return;
    const ts = new Date(item.timestamp);
    if (Number.isNaN(ts.getTime())) return;
    const index = Math.floor((ts.getTime() - start.getTime()) / bucketMs);
    if (index < 0 || index >= bucketCount) return;
    const uniqueTags = new Set(getTagValues(item.tags));
    uniqueTags.forEach((tag) => {
      const label = String(tag || "").toLowerCase();
      if (!label) return;
      if (!tagBuckets[label]) {
        tagBuckets[label] = new Array(bucketCount).fill(0);
      }
      tagBuckets[label][index] += 1;
      tagTotals[label] = (tagTotals[label] || 0) + 1;
    });
  });

  const tagsSorted = Object.entries(tagTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([tag]) => tag);

  const labels = [];
  for (let i = 0; i < bucketCount; i += 1) {
    const bucketDate = new Date(start.getTime() + i * bucketMs);
    if (mode === "daily") {
      labels.push(bucketDate.toLocaleDateString(undefined, { month: "short", day: "numeric" }));
    } else {
      labels.push(bucketDate.toLocaleTimeString(undefined, { hour: "numeric" }));
    }
  }

  return { tags: tagsSorted, buckets: tagBuckets, totals: tagTotals, labels };
}

function buildSparkline(values) {
  const max = Math.max(...values, 1);
  const width = 100;
  const height = 30;
  const padding = 3;
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - padding - (value / max) * (height - padding * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const path = `M 0 ${height} L ${points.join(" ")} L ${width} ${height} Z`;
  return { points: points.join(" "), path };
}

function renderTrendList() {
  if (!elements.trendList) return;
  const data = buildTrendData(state.descriptions, state.trendMode);
  if (!data.tags.length) {
    elements.trendList.innerHTML = "<div class=\"trend-empty\">No tag trends yet.</div>";
    return;
  }
  elements.trendList.innerHTML = "";
  data.tags.forEach((tag) => {
    const values = data.buckets[tag] || [];
    const total = data.totals[tag] || 0;
    const row = document.createElement("div");
    row.className = "trend-row";
    row.dataset.tagValue = tag;

    const tagLabel = document.createElement("div");
    tagLabel.className = "trend-tag";
    tagLabel.textContent = tag;

    const meta = document.createElement("div");
    meta.className = "trend-meta";
    meta.textContent = `${total} in window`;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "sparkline");
    svg.setAttribute("viewBox", "0 0 100 30");
    svg.setAttribute("preserveAspectRatio", "none");
    const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    const { points, path } = buildSparkline(values);
    area.setAttribute("d", path);
    area.setAttribute("fill", "rgba(23, 107, 107, 0.18)");
    line.setAttribute("points", points);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "rgba(23, 107, 107, 0.9)");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(area);
    svg.appendChild(line);

    row.appendChild(tagLabel);
    row.appendChild(svg);
    row.appendChild(meta);
    elements.trendList.appendChild(row);
  });
}

function setTrendMode(mode) {
  state.trendMode = mode;
  elements.trendButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.trend === mode);
  });
  renderTrendList();
}

function updateTimelapseRangeFill(maxIndex, index) {
  if (!elements.timelapseRange) return;
  const clampedMax = Math.max(maxIndex, 0);
  const percent = clampedMax === 0 ? 0 : Math.round((index / clampedMax) * 100);
  elements.timelapseRange.style.setProperty("--range-fill", `${percent}%`);
}

function renderTimelapse(indexOverride = null) {
  const items = state.timelapse.items;
  if (items.length === 0) {
    elements.timelapseRange.max = 0;
    elements.timelapseRange.value = 0;
    state.timelapse.index = 0;
    updateTimelapseRangeFill(0, 0);
    elements.timelapseImage.removeAttribute("src");
    elements.timelapseTime.textContent = "--";
    elements.timelapseCount.textContent = "0 / 0";
    elements.timelapseDescription.textContent = "No snapshots for this day.";
    if (elements.timelapseTags) {
      elements.timelapseTags.innerHTML = "";
    }
    return;
  }
  const maxIndex = Math.max(items.length - 1, 0);
  let nextIndex = state.timelapse.index;
  if (typeof indexOverride === "number" && !Number.isNaN(indexOverride)) {
    nextIndex = indexOverride;
  }
  nextIndex = Math.min(Math.max(nextIndex, 0), maxIndex);
  state.timelapse.index = nextIndex;
  elements.timelapseRange.max = maxIndex;
  elements.timelapseRange.value = nextIndex;
  updateTimelapseRangeFill(maxIndex, nextIndex);

  const item = items[nextIndex];
  elements.timelapseImage.src = snapshotUrl(item.snapshot);
  elements.timelapseTime.textContent = formatTime(item.timestamp);
  elements.timelapseCount.textContent = `${nextIndex + 1} / ${items.length}`;
  elements.timelapseDescription.textContent = item.text || "No description.";
  if (elements.timelapseTags) {
    renderTags(elements.timelapseTags, item.tags);
  }
}

function setTimelapseMode(mode) {
  state.timelapse.mode = mode;
  elements.timelapseButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  updateTimelapseData();
}

function updateTimelapseData() {
  const dates = buildTimelapseDates(state.descriptions);
  if (dates.length === 0) {
    elements.timelapseDay.innerHTML = "";
    state.timelapse.items = [];
    renderTimelapse();
    return;
  }

  if (!state.timelapse.date || !dates.includes(state.timelapse.date)) {
    state.timelapse.date = dates[dates.length - 1];
  }

  elements.timelapseDay.innerHTML = "";
  dates.forEach((date) => {
    const option = document.createElement("option");
    option.value = date;
    option.textContent = date;
    if (date === state.timelapse.date) {
      option.selected = true;
    }
    elements.timelapseDay.appendChild(option);
  });

  state.timelapse.items = buildTimelapseItems(
    state.descriptions,
    state.timelapse.mode,
    state.timelapse.date
  );
  state.timelapse.index = 0;
  renderTimelapse();
}

function pauseTimelapse() {
  if (!state.timelapse.playing) {
    return;
  }
  state.timelapse.playing = false;
  elements.timelapsePlay.textContent = "Play";
  if (state.timelapse.timer) {
    clearInterval(state.timelapse.timer);
    state.timelapse.timer = null;
  }
}

function toggleTimelapse() {
  if (state.timelapse.playing) {
    pauseTimelapse();
    return;
  }

  state.timelapse.playing = true;
  elements.timelapsePlay.textContent = "Pause";
  if (state.timelapse.timer) {
    clearInterval(state.timelapse.timer);
  }
  state.timelapse.timer = setInterval(() => {
    if (state.timelapse.items.length === 0) {
      toggleTimelapse();
      return;
    }
    state.timelapse.index += 1;
    if (state.timelapse.index >= state.timelapse.items.length) {
      state.timelapse.index = 0;
    }
    renderTimelapse();
  }, 1200);
}

function populateCompareOptions(descriptions) {
  const options = descriptions.slice().reverse();
  elements.compareSelectA.innerHTML = "";
  elements.compareSelectB.innerHTML = "";
  options.forEach((item, index) => {
    const label = `${formatTime(item.timestamp)} - ${(item.text || "").slice(0, 40)}`;
    const optionA = document.createElement("option");
    optionA.value = item.snapshot || "";
    optionA.textContent = label;
    optionA.dataset.timestamp = item.timestamp || "";
    const optionB = optionA.cloneNode(true);
    if (index === 0) {
      optionA.selected = true;
    }
    if (index === 1) {
      optionB.selected = true;
    }
    elements.compareSelectA.appendChild(optionA);
    elements.compareSelectB.appendChild(optionB);
  });
  updateComparePreview();
}

function updateComparePreview() {
  const optionA = elements.compareSelectA.selectedOptions[0];
  const optionB = elements.compareSelectB.selectedOptions[0];
  if (optionA) {
    elements.compareImageA.src = snapshotUrl(optionA.value);
    elements.compareTimeA.textContent = formatTime(optionA.dataset.timestamp);
  }
  if (optionB) {
    elements.compareImageB.src = snapshotUrl(optionB.value);
    elements.compareTimeB.textContent = formatTime(optionB.dataset.timestamp);
  }
}

async function runCompare() {
  const snapshotA = elements.compareSelectA.value;
  const snapshotB = elements.compareSelectB.value;
  if (!snapshotA || !snapshotB) {
    setTextBlock(elements.compareResult, "Select two snapshots first.");
    return;
  }
  if (snapshotA === snapshotB) {
    setTextBlock(elements.compareResult, "Please choose two different snapshots.");
    return;
  }
  setTextBlock(elements.compareResult, "Running comparison...");
  try {
    const result = await fetchJson("/api/compare/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot_a: snapshotA, snapshot_b: snapshotB }),
    });
    const message = result.text || "No comparison text returned.";
    setTextBlock(elements.compareResult, message, formatTime(result.timestamp), "subtle");
  } catch (error) {
    setTextBlock(elements.compareResult, "Comparison failed. Check logs.");
  }
}

function renderUsageSummary(summary) {
  if (!summary) return;
  elements.costTotalTokens.textContent = summary.totals.total_tokens.toLocaleString();
  elements.costTotalUsd.textContent = usdFormatter.format(summary.totals.cost_usd || 0);

  elements.costProviders.replaceChildren();
  Object.entries(summary.by_provider || {}).forEach(([provider, data]) => {
    const row = document.createElement("div");
    row.className = "cost-provider";
    const label = document.createElement("strong");
    label.textContent = provider;
    const value = document.createElement("span");
    value.textContent = `${data.total_tokens.toLocaleString()} tokens / ${usdFormatter.format(
      data.cost_usd || 0
    )}`;
    row.appendChild(label);
    row.appendChild(value);
    elements.costProviders.appendChild(row);
  });

  elements.costDays.replaceChildren();
  (summary.by_day || []).forEach((day) => {
    const row = document.createElement("div");
    row.className = "cost-day";
    const label = document.createElement("span");
    label.textContent = day.date;
    const value = document.createElement("span");
    value.textContent = `${day.total_tokens.toLocaleString()} tokens / ${usdFormatter.format(
      day.cost_usd || 0
    )}`;
    row.appendChild(label);
    row.appendChild(value);
    elements.costDays.appendChild(row);
  });
}

function loadPreview() {
  if (!elements.previewImage || !elements.previewTime) return;
  elements.previewTime.textContent = "Capturing...";
  elements.previewImage.src = withApiKey(`/api/preview?ts=${Date.now()}`);
}

async function loadDescriptions() {
  const params = new URLSearchParams();
  if (state.descriptionsLimit) {
    params.set("limit", String(state.descriptionsLimit));
  }
  const url = params.toString() ? `/api/descriptions?${params}` : "/api/descriptions";
  const descriptions = await fetchJson(url);
  state.descriptions = Array.isArray(descriptions) ? descriptions : [];

  const latestDescription = state.descriptions[state.descriptions.length - 1];
  elements.latestDescription.textContent =
    latestDescription?.text || "No description yet.";
  renderTags(elements.latestTags, latestDescription?.tags);
  updateActiveNow(latestDescription);
  renderTrendList();

  renderHistory(state.descriptions);
  updateTimelapseData();
  populateCompareOptions(state.descriptions);
}

function updateAskUi() {
  if (!elements.askCard || !elements.askQuery || !elements.askRun || !elements.askResponse) {
    return;
  }
  const enabled = state.ask.enabled;
  elements.askQuery.disabled = !enabled;
  elements.askRun.disabled = !enabled;
  if (elements.askWindow) {
    elements.askWindow.textContent = `Last ${state.ask.lookbackHours} hours`;
  }
  if (!enabled) {
    setTextBlock(elements.askResponse, "Ask is disabled. Set ASK_ENABLED=true in .env to enable it.");
  }
}

async function runAsk() {
  if (!elements.askQuery || !elements.askResponse || !elements.askRun) return;
  const query = elements.askQuery.value.trim();
  if (!query) {
    setTextBlock(elements.askResponse, "Enter a question to ask the feed.");
    return;
  }
  elements.askRun.disabled = true;
  setTextBlock(elements.askResponse, "Asking Gemini...");
  try {
    const result = await fetchJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const answer = result.answer || "No answer returned.";
    const windowLabel = result.window?.label || `Last ${state.ask.lookbackHours} hours`;
    const items = typeof result.window?.items === "number" ? result.window.items : null;
    const meta = items === null ? windowLabel : `${windowLabel} | ${items} snapshots`;
    setTextBlock(elements.askResponse, answer, meta, "subtle");
  } catch (error) {
    setTextBlock(elements.askResponse, "Ask failed. Check logs for details.");
  } finally {
    elements.askRun.disabled = false;
  }
}

async function loadConfig() {
  try {
    const config = await fetchJson("/api/config");
    if (config.ui_refresh_interval_sec) {
      state.refreshIntervalMs = config.ui_refresh_interval_sec * 1000;
    }
    if (typeof config.ask_enabled === "boolean") {
      state.ask.enabled = config.ask_enabled;
    }
    if (Number.isFinite(config.ask_lookback_hours)) {
      state.ask.lookbackHours = config.ask_lookback_hours;
    }
    if (Number.isFinite(config.ask_max_items)) {
      state.ask.maxItems = config.ask_max_items;
    }
    updateAskUi();
  } catch (error) {
    console.warn("Config load failed", error);
  }
}

async function loadData() {
  try {
    const [health, latest, compare10m, compareHourly, dailyReports, usageSummary] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/snapshots/latest"),
      fetchJson("/api/compare/10m"),
      fetchJson("/api/compare/hourly"),
      fetchJson("/api/reports/daily"),
      fetchJson("/api/usage/summary"),
    ]);

    setHealth(health.status || "degraded");

    if (latest.snapshot) {
      elements.latestImage.src = snapshotUrl(latest.snapshot);
      elements.latestTime.textContent = formatTime(latest.timestamp);
    } else {
      elements.latestImage.removeAttribute("src");
      elements.latestTime.textContent = "--";
    }

    renderList(elements.compare10m, compare10m);
    renderList(elements.compareHourly, compareHourly);

    await loadDescriptions();

    const latestReport = dailyReports[dailyReports.length - 1];
    if (latestReport) {
      const summaryText = latestReport.summary || latestReport.text || "";
      setTextBlock(
        elements.dailyReport,
        summaryText || "No daily report yet.",
        formatTime(latestReport.timestamp),
        null
      );
      elements.dailyHighlights.innerHTML = "";
      if (Array.isArray(latestReport.highlights) && latestReport.highlights.length > 0) {
        latestReport.highlights.forEach((item) => {
          const entry = document.createElement("div");
          entry.className = "highlight-item";
          entry.textContent = item;
          elements.dailyHighlights.appendChild(entry);
        });
      } else {
        elements.dailyHighlights.innerHTML = "<div class=\"highlight-item\">No highlights yet.</div>";
      }
      renderTagSummary(elements.dailyTags, latestReport.tags);
      if (elements.dailyTags.childElementCount === 0) {
        elements.dailyTags.innerHTML = "<span class=\"subtle\">No tags yet.</span>";
      }
    } else {
      setTextBlock(elements.dailyReport, "No daily report yet.", null, null);
      elements.dailyHighlights.innerHTML = "";
      elements.dailyTags.innerHTML = "<span class=\"subtle\">No tags yet.</span>";
    }

    renderUsageSummary(usageSummary);

    state.lastUpdated = new Date();
    elements.lastUpdated.textContent = `Updated: ${state.lastUpdated.toLocaleTimeString()}`;
  } catch (error) {
    setHealth("degraded");
    elements.latestDescription.textContent = "Unable to load data.";
    console.error(error);
  }
}

async function init() {
  await loadConfig();
  updateAskUi();
  await loadData();
  loadPreview();
  setInterval(loadData, state.refreshIntervalMs);
}

elements.refreshBtn.addEventListener("click", () => {
  loadData();
  loadPreview();
});

elements.historySearch.addEventListener("input", (event) => {
  setHistoryQuery(event.target.value);
});

elements.historyMore.addEventListener("click", async () => {
  state.historyLimit += 12;
  if (state.historyLimit > state.descriptionsLimit) {
    state.descriptionsLimit = state.historyLimit;
    await loadDescriptions();
  } else {
    renderHistory(state.descriptions);
  }
});

elements.timelapseDay.addEventListener("change", (event) => {
  state.timelapse.date = event.target.value;
  state.timelapse.index = 0;
  renderTimelapse();
});

elements.timelapseRange.addEventListener("input", () => {
  pauseTimelapse();
  renderTimelapse(Number(elements.timelapseRange.value));
});

elements.timelapseRange.addEventListener("pointerdown", (event) => {
  if (state.timelapse.items.length === 0) return;
  const rect = elements.timelapseRange.getBoundingClientRect();
  if (rect.width === 0) return;
  const percent = (event.clientX - rect.left) / rect.width;
  const maxIndex = Number(elements.timelapseRange.max) || 0;
  const nextIndex = Math.round(Math.min(Math.max(percent, 0), 1) * maxIndex);
  elements.timelapseRange.value = nextIndex;
  pauseTimelapse();
  renderTimelapse(nextIndex);
});

elements.timelapsePlay.addEventListener("click", toggleTimelapse);

elements.timelapseButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.mode === state.timelapse.mode) {
      return;
    }
    setTimelapseMode(button.dataset.mode);
  });
});

elements.trendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.trend === state.trendMode) {
      return;
    }
    setTrendMode(button.dataset.trend);
  });
});

if (elements.trendList) {
  elements.trendList.addEventListener("click", (event) => {
    const row = event.target.closest(".trend-row");
    if (!row || !row.dataset.tagValue) {
      return;
    }
    setHistoryQuery(row.dataset.tagValue);
  });
}

if (elements.dailyTags) {
  elements.dailyTags.addEventListener("click", (event) => {
    const chip = event.target.closest(".tag");
    if (!chip || !chip.dataset.tagValue) {
      return;
    }
    setHistoryQuery(chip.dataset.tagValue);
  });
}

elements.compareSelectA.addEventListener("change", updateComparePreview);
elements.compareSelectB.addEventListener("change", updateComparePreview);
elements.compareRun.addEventListener("click", runCompare);

if (elements.askRun) {
  elements.askRun.addEventListener("click", runAsk);
}

if (elements.previewImage && elements.previewTime) {
  elements.previewImage.addEventListener("load", () => {
    elements.previewTime.textContent = `Captured: ${new Date().toLocaleTimeString()}`;
  });

  elements.previewImage.addEventListener("error", () => {
    elements.previewImage.removeAttribute("src");
    elements.previewTime.textContent = "Preview unavailable";
  });
}

init();
