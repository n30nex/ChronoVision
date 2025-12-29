const state = {
  refreshIntervalMs: 30000,
  lastUpdated: null,
  historyLimit: 12,
  historyQuery: "",
  descriptions: [],
  descriptionsLimit: 500,
  compare10m: [],
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
const ACTIVE_WINDOW_MINUTES = 20;
const ACTIVE_WINDOW_MAX_ITEMS = 5;

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
  activeChange: document.getElementById("active-change"),
  activeStability: document.getElementById("active-stability"),
  activeLastSeen: document.getElementById("active-last-seen"),
  activeTagsLabel: document.getElementById("active-tags-label"),
  askCard: document.getElementById("ask-card"),
  askQuery: document.getElementById("ask-query"),
  askRun: document.getElementById("ask-run"),
  askResponse: document.getElementById("ask-response"),
  askWindow: document.getElementById("ask-window"),
  rangeStart: document.getElementById("range-start"),
  rangeEnd: document.getElementById("range-end"),
  rangeRun: document.getElementById("range-run"),
  rangeMeta: document.getElementById("range-meta"),
  rangeResponse: document.getElementById("range-response"),
  rangePresetButtons: document.querySelectorAll("[data-range-hours]"),
  storyArc: document.getElementById("story-arc"),
  storyArcRefresh: document.getElementById("story-arc-refresh"),
  highlightReel: document.getElementById("highlight-reel"),
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

function formatDateTimeLocal(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  const pad = (value) => String(value).padStart(2, "0");
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hour = pad(date.getHours());
  const minute = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function getLatestDescriptionTime() {
  const latest = state.descriptions[state.descriptions.length - 1];
  return parseTimestamp(latest?.timestamp) || new Date();
}

function parseTimestamp(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function formatRelativeTime(value) {
  const date = parseTimestamp(value);
  if (!date) return "--";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 60000) return "just now";
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function formatDurationMinutes(minutes) {
  if (!Number.isFinite(minutes) || minutes < 1) return "under 1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
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

function renderTagList(container, tags) {
  if (!container) return;
  container.innerHTML = "";
  if (!Array.isArray(tags) || tags.length === 0) return;
  tags.slice(0, 8).forEach((tag) => {
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

function getRecentDescriptions(descriptions, windowMinutes, maxItems) {
  if (!Array.isArray(descriptions) || descriptions.length === 0) return [];
  const latest = descriptions[descriptions.length - 1];
  const latestTime = parseTimestamp(latest?.timestamp) || new Date();
  const windowStart = new Date(latestTime.getTime() - windowMinutes * 60000);
  const recent = [];
  for (let i = descriptions.length - 1; i >= 0 && recent.length < maxItems; i -= 1) {
    const item = descriptions[i];
    const ts = parseTimestamp(item?.timestamp);
    if (ts && ts < windowStart) {
      break;
    }
    recent.push(item);
  }
  if (recent.length === 0) {
    return descriptions.slice(-maxItems);
  }
  return recent.reverse();
}

function buildRecentTagSummary(items) {
  const counts = new Map();
  const groupCounts = { people: 0, vehicles: 0, objects: 0 };
  items.forEach((item) => {
    const tags = item?.tags || {};
    if (Array.isArray(tags.people) && tags.people.length > 0) {
      groupCounts.people += 1;
    }
    if (Array.isArray(tags.vehicles) && tags.vehicles.length > 0) {
      groupCounts.vehicles += 1;
    }
    if (Array.isArray(tags.objects) && tags.objects.length > 0) {
      groupCounts.objects += 1;
    }
    const uniqueTags = new Set(
      getTagValues(tags)
        .map((tag) => String(tag || "").toLowerCase())
        .filter(Boolean)
    );
    uniqueTags.forEach((tag) => {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    });
  });

  const topTags = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([tag]) => tag);

  return { topTags, groupCounts };
}

function getLastSeen(descriptions) {
  const result = { people: null, vehicles: null, objects: null };
  if (!Array.isArray(descriptions)) return result;
  for (let i = descriptions.length - 1; i >= 0; i -= 1) {
    const tags = descriptions[i]?.tags || {};
    if (!result.people && Array.isArray(tags.people) && tags.people.length > 0) {
      result.people = descriptions[i]?.timestamp || null;
    }
    if (!result.vehicles && Array.isArray(tags.vehicles) && tags.vehicles.length > 0) {
      result.vehicles = descriptions[i]?.timestamp || null;
    }
    if (!result.objects && Array.isArray(tags.objects) && tags.objects.length > 0) {
      result.objects = descriptions[i]?.timestamp || null;
    }
    if (result.people && result.vehicles && result.objects) {
      break;
    }
  }
  return result;
}

function isNoChangeText(text) {
  const value = String(text || "").toLowerCase();
  return (
    value.includes("no significant change") ||
    value.includes("no meaningful change") ||
    value.includes("no change")
  );
}

function getLatestCompare(compareItems) {
  if (!Array.isArray(compareItems) || compareItems.length === 0) return null;
  const withTs = compareItems.filter((item) => item?.timestamp);
  if (withTs.length === 0) {
    return compareItems[compareItems.length - 1];
  }
  return withTs
    .slice()
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
    .pop();
}

function getStabilitySummary(compareItems) {
  if (!Array.isArray(compareItems) || compareItems.length === 0) {
    return "Stability unknown";
  }
  const items = compareItems.slice();
  items.sort((a, b) => {
    const aTime = parseTimestamp(a?.timestamp);
    const bTime = parseTimestamp(b?.timestamp);
    if (!aTime || !bTime) return 0;
    return aTime - bTime;
  });
  let count = 0;
  let firstNoChange = null;
  let lastNoChange = null;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (!isNoChangeText(items[i]?.text)) {
      break;
    }
    count += 1;
    const ts = parseTimestamp(items[i]?.timestamp);
    if (ts) {
      if (!lastNoChange) {
        lastNoChange = ts;
      }
      firstNoChange = ts;
    }
  }
  if (count === 0) {
    return "Recent change detected";
  }
  let minutes = 0;
  if (firstNoChange && lastNoChange) {
    minutes = Math.round((lastNoChange - firstNoChange) / 60000);
  }
  if (!minutes || minutes < 1) {
    minutes = count * 10;
  }
  return `Stable for ${formatDurationMinutes(minutes)}`;
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

function renderStoryArc(container, data) {
  if (!container) return;
  container.replaceChildren();
  const bullets = data?.bullets;
  if (!Array.isArray(bullets) || bullets.length === 0) {
    const empty = document.createElement("div");
    empty.className = "story-arc-item";
    empty.textContent = "No story arc yet.";
    container.appendChild(empty);
    return;
  }
  bullets.forEach((bullet) => {
    const item = document.createElement("div");
    item.className = "story-arc-item";
    item.textContent = bullet;
    container.appendChild(item);
  });
}

function renderHighlightReel(container, data) {
  if (!container) return;
  container.replaceChildren();
  const items = data?.items;
  if (!Array.isArray(items) || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "highlight-card";
    const body = document.createElement("div");
    body.className = "highlight-body";
    body.textContent = "No highlights yet.";
    empty.appendChild(body);
    container.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "highlight-card";

    if (item.snapshot) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = snapshotUrl(item.snapshot);
      img.alt = `Highlight ${formatTime(item.timestamp)}`;
      card.appendChild(img);
    }

    const body = document.createElement("div");
    body.className = "highlight-body";

    const meta = document.createElement("span");
    meta.className = "highlight-meta";
    meta.textContent = formatTime(item.timestamp);

    const text = document.createElement("p");
    text.textContent = item.text || "No description available.";

    body.appendChild(meta);
    body.appendChild(text);

    if (item.compare_text) {
      const compare = document.createElement("div");
      compare.className = "highlight-compare";
      compare.textContent = item.compare_text;
      body.appendChild(compare);
    }

    const tagsWrap = document.createElement("div");
    tagsWrap.className = "tag-list";
    renderTags(tagsWrap, item.tags);
    if (tagsWrap.childElementCount > 0) {
      body.appendChild(tagsWrap);
    }

    card.appendChild(body);
    container.appendChild(card);
  });
}

async function refreshStoryArc() {
  if (!elements.storyArc) return;
  try {
    const data = await fetchJson("/api/story/daily");
    renderStoryArc(elements.storyArc, data);
  } catch (error) {
    renderStoryArc(elements.storyArc, { bullets: [] });
  }
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
    if (elements.activeChange) {
      elements.activeChange.textContent = "--";
    }
    if (elements.activeStability) {
      elements.activeStability.textContent = "--";
    }
    if (elements.activeLastSeen) {
      elements.activeLastSeen.textContent = "--";
    }
    if (elements.activeTagsLabel) {
      elements.activeTagsLabel.textContent = "Top tags";
    }
    return;
  }

  const recentDescriptions = getRecentDescriptions(
    state.descriptions,
    ACTIVE_WINDOW_MINUTES,
    ACTIVE_WINDOW_MAX_ITEMS
  );
  const { topTags, groupCounts } = buildRecentTagSummary(recentDescriptions);
  const hasPeople = groupCounts.people > 0;
  const hasVehicles = groupCounts.vehicles > 0;
  const hasObjects = groupCounts.objects > 0;
  const hasActivity = hasPeople || hasVehicles || hasObjects;
  elements.activeIndicator.textContent = hasPeople
    ? "People"
    : hasVehicles
      ? "Vehicles"
      : hasActivity
        ? "Activity"
        : "Clear";
  elements.activeLabel.textContent = hasPeople
    ? "People present"
    : hasVehicles
      ? "Vehicle activity"
      : hasActivity
        ? "Activity detected"
        : "No activity detected";
  if (elements.activeTime) {
    elements.activeTime.textContent = formatTime(latestDescription.timestamp);
  }
  elements.activeDot.className = `status-dot ${hasActivity ? "active" : "idle"}`;
  if (elements.activeTags) {
    renderTagList(elements.activeTags, topTags);
    if (elements.activeTags.childElementCount === 0) {
      elements.activeTags.innerHTML = "<span class=\"subtle\">No tags yet.</span>";
    }
  }
  if (elements.activeTagsLabel) {
    elements.activeTagsLabel.textContent = `Top tags (last ${ACTIVE_WINDOW_MINUTES} min, ${recentDescriptions.length} snapshots)`;
  }
  if (elements.activeChange) {
    const latestCompare = getLatestCompare(state.compare10m);
    if (latestCompare?.text) {
      const compareTime = latestCompare.timestamp ? formatTime(latestCompare.timestamp) : "";
      elements.activeChange.textContent = compareTime
        ? `${latestCompare.text} (${compareTime})`
        : latestCompare.text;
    } else {
      elements.activeChange.textContent = "No recent comparison";
    }
  }
  if (elements.activeStability) {
    elements.activeStability.textContent = getStabilitySummary(state.compare10m);
  }
  if (elements.activeLastSeen) {
    const lastSeen = getLastSeen(state.descriptions);
    const parts = [
      `People ${formatRelativeTime(lastSeen.people)}`,
      `Vehicles ${formatRelativeTime(lastSeen.vehicles)}`,
      `Objects ${formatRelativeTime(lastSeen.objects)}`,
    ];
    elements.activeLastSeen.textContent = parts.join(", ");
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
  setRangeDefaults(state.descriptions);
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
  if (elements.rangeStart) {
    elements.rangeStart.disabled = !enabled;
  }
  if (elements.rangeEnd) {
    elements.rangeEnd.disabled = !enabled;
  }
  if (elements.rangeRun) {
    elements.rangeRun.disabled = !enabled;
  }
  if (!enabled && elements.rangeResponse) {
    setTextBlock(
      elements.rangeResponse,
      "Range summaries are disabled. Set ASK_ENABLED=true in .env to enable them."
    );
  }
}

function getRangeBounds() {
  if (!elements.rangeStart || !elements.rangeEnd) return null;
  const startValue = elements.rangeStart.value;
  const endValue = elements.rangeEnd.value;
  if (!startValue || !endValue) return null;
  const start = new Date(startValue);
  const end = new Date(endValue);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  return { start, end };
}

function updateRangeMetaPreview() {
  if (!elements.rangeMeta) return;
  const bounds = getRangeBounds();
  if (!bounds) {
    elements.rangeMeta.textContent = "Select start and end";
    return;
  }
  if (bounds.end <= bounds.start) {
    elements.rangeMeta.textContent = "End must be after start";
    return;
  }
  const count = state.descriptions.filter((item) => {
    const ts = parseTimestamp(item.timestamp);
    if (!ts) return false;
    return ts >= bounds.start && ts <= bounds.end;
  }).length;
  elements.rangeMeta.textContent = `${count} snapshots in range`;
}

function setRangePreset(hours) {
  if (!elements.rangeStart || !elements.rangeEnd) return;
  const endDate = getLatestDescriptionTime();
  const startDate = new Date(endDate.getTime() - hours * 60 * 60 * 1000);
  elements.rangeEnd.value = formatDateTimeLocal(endDate);
  elements.rangeStart.value = formatDateTimeLocal(startDate);
  updateRangeMetaPreview();
}

function setRangeDefaults(descriptions) {
  if (!elements.rangeStart || !elements.rangeEnd) return;
  const latest = descriptions[descriptions.length - 1];
  const latestDate = parseTimestamp(latest?.timestamp) || new Date();
  const endValue = formatDateTimeLocal(latestDate);
  const startDate = new Date(latestDate.getTime() - 2 * 60 * 60 * 1000);
  const startValue = formatDateTimeLocal(startDate);
  if (!elements.rangeEnd.value) {
    elements.rangeEnd.value = endValue;
  }
  if (!elements.rangeStart.value) {
    elements.rangeStart.value = startValue;
  }
  updateRangeMetaPreview();
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

async function runRangeSummary() {
  if (!elements.rangeResponse || !elements.rangeRun) return;
  const bounds = getRangeBounds();
  if (!bounds) {
    setTextBlock(elements.rangeResponse, "Select both start and end times.");
    return;
  }
  if (bounds.end <= bounds.start) {
    setTextBlock(elements.rangeResponse, "End time must be after start time.");
    return;
  }
  elements.rangeRun.disabled = true;
  setTextBlock(elements.rangeResponse, "Summarizing range...");
  try {
    const result = await fetchJson("/api/summary/range", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start: bounds.start.toISOString(),
        end: bounds.end.toISOString(),
      }),
    });
    const answer = result.answer || "No summary returned.";
    const windowLabel = result.window?.label || "Selected range";
    const snapshots = typeof result.window?.items === "number" ? result.window.items : null;
    const comparisons = typeof result.window?.comparisons === "number" ? result.window.comparisons : null;
    const metaParts = [windowLabel];
    if (snapshots !== null) {
      metaParts.push(`${snapshots} snapshots`);
    }
    if (comparisons !== null) {
      metaParts.push(`${comparisons} comparisons`);
    }
    setTextBlock(elements.rangeResponse, answer, metaParts.join(" | "), "subtle");
  } catch (error) {
    setTextBlock(elements.rangeResponse, "Range summary failed. Check logs for details.");
  } finally {
    elements.rangeRun.disabled = false;
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
    const [
      health,
      latest,
      compare10m,
      compareHourly,
      dailyReports,
      usageSummary,
      storyArc,
      highlightReel,
    ] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/snapshots/latest"),
      fetchJson("/api/compare/10m"),
      fetchJson("/api/compare/hourly"),
      fetchJson("/api/reports/daily"),
      fetchJson("/api/usage/summary"),
      fetchJson("/api/story/daily"),
      fetchJson("/api/highlights/daily"),
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
    state.compare10m = Array.isArray(compare10m) ? compare10m : [];

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
    renderStoryArc(elements.storyArc, storyArc);
    renderHighlightReel(elements.highlightReel, highlightReel);

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

if (elements.rangeRun) {
  elements.rangeRun.addEventListener("click", runRangeSummary);
}

if (elements.rangeStart) {
  elements.rangeStart.addEventListener("change", updateRangeMetaPreview);
}

if (elements.rangeEnd) {
  elements.rangeEnd.addEventListener("change", updateRangeMetaPreview);
}

if (elements.rangePresetButtons && elements.rangePresetButtons.length > 0) {
  elements.rangePresetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const hours = Number(button.dataset.rangeHours || 0);
      if (!Number.isFinite(hours) || hours <= 0) {
        return;
      }
      setRangePreset(hours);
    });
  });
}

if (elements.storyArcRefresh) {
  elements.storyArcRefresh.addEventListener("click", () => {
    refreshStoryArc();
  });
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
