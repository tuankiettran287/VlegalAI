import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import resvgPackage from "@resvg/resvg-js";

const { Resvg } = resvgPackage;
const require = createRequire(import.meta.url);
const iconSets = {
  logos: require("@iconify-json/logos/icons.json"),
  lucide: require("@iconify-json/lucide/icons.json"),
  simple: require("@iconify-json/simple-icons/icons.json"),
};

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const kitDir = path.resolve(scriptDir, "..");
const svgDir = path.join(kitDir, "images", "svg");
const pngDir = path.join(kitDir, "images", "png");

const C = {
  page: "#F7F6EF",
  gridMinor: "#E7E6DF",
  gridMajor: "#D8D7D0",
  ink: "#242424",
  line: "#4B5563",
  muted: "#667085",
  white: "#FFFFFF",
  blue: "#6F8FF7",
  blueSoft: "#EEF3FF",
  magenta: "#D96FC7",
  magentaSoft: "#FFF1FB",
  teal: "#069A8E",
  tealSoft: "#EAF9F6",
  orange: "#E58A3A",
  orangeSoft: "#FFF6EA",
  purple: "#8B69D4",
  purpleSoft: "#F5F0FF",
  green: "#4A9B73",
  greenSoft: "#EFF8F2",
  red: "#C95F67",
  redSoft: "#FFF0F1",
  graySoft: "#F3F4F6",
};

const icons = {
  fastapi: { set: "logos", name: "fastapi-icon", color: "#009688" },
  postgresql: { set: "logos", name: "postgresql", color: "#4169E1" },
  neo4j: { set: "logos", name: "neo4j", color: "#018BFF" },
  react: { set: "logos", name: "react", color: "#149ECA" },
  typescript: { set: "logos", name: "typescript-icon", color: "#3178C6" },
  docker: { set: "logos", name: "docker-icon", color: "#2496ED" },
  google: { set: "logos", name: "google-icon", color: "#4285F4" },
  redis: { set: "logos", name: "redis", color: "#DC382D" },
  sqlite: { set: "simple", name: "sqlite", color: "#0F80CC" },
  python: { set: "simple", name: "python", color: "#3776AB" },
  celery: { set: "simple", name: "celery", color: "#37814A" },
  caddy: { set: "simple", name: "caddy", color: "#1F88C0" },
  qwen: { set: "simple", name: "alibabacloud", color: "#FF6A00" },
  huggingface: { set: "simple", name: "huggingface", color: "#FF9D00" },
  users: { set: "lucide", name: "users", color: C.ink },
  monitor: { set: "lucide", name: "monitor", color: C.ink },
  smartphone: { set: "lucide", name: "smartphone", color: C.ink },
  server: { set: "lucide", name: "server", color: C.ink },
  workflow: { set: "lucide", name: "workflow", color: C.ink },
  search: { set: "lucide", name: "search", color: C.teal },
  brain: { set: "lucide", name: "brain-circuit", color: C.purple },
  database: { set: "lucide", name: "database", color: C.blue },
  file: { set: "lucide", name: "file-text", color: C.ink },
  files: { set: "lucide", name: "files", color: C.ink },
  shield: { set: "lucide", name: "shield-check", color: C.green },
  lock: { set: "lucide", name: "lock-keyhole", color: C.green },
  message: { set: "lucide", name: "message-square-text", color: C.blue },
  history: { set: "lucide", name: "history", color: C.blue },
  network: { set: "lucide", name: "network", color: C.purple },
  refresh: { set: "lucide", name: "refresh-cw", color: C.teal },
  clock: { set: "lucide", name: "clock-3", color: C.orange },
  filter: { set: "lucide", name: "list-filter", color: C.teal },
  merge: { set: "lucide", name: "git-merge", color: C.purple },
  link: { set: "lucide", name: "link", color: C.teal },
  download: { set: "lucide", name: "download", color: C.blue },
  globe: { set: "lucide", name: "globe", color: C.blue },
  scale: { set: "lucide", name: "scale", color: C.purple },
  key: { set: "lucide", name: "key-round", color: C.orange },
  check: { set: "lucide", name: "circle-check", color: C.green },
  browser: { set: "lucide", name: "panel-top", color: C.ink },
  box: { set: "lucide", name: "box", color: C.ink },
};

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function iconData(key) {
  const spec = icons[key];
  if (!spec) throw new Error(`Unknown icon key: ${key}`);
  const collection = iconSets[spec.set];
  const icon = collection.icons[spec.name];
  if (!icon) throw new Error(`Missing icon ${spec.set}:${spec.name}`);
  return {
    body: icon.body.replaceAll("currentColor", spec.color),
    width: icon.width ?? collection.width ?? 24,
    height: icon.height ?? collection.height ?? 24,
  };
}

function icon(key, x, y, size, label = "") {
  const data = iconData(key);
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 ${data.width} ${data.height}" preserveAspectRatio="xMidYMid meet" overflow="visible"${label ? ` aria-label="${escapeXml(label)}"` : ' aria-hidden="true"'}>
${label ? `<title>${escapeXml(label)}</title>` : ""}
${data.body}
</svg>`;
}

function lineText(x, y, value, options = {}) {
  const {
    size = 18,
    weight = 500,
    fill = C.ink,
    anchor = "start",
    family = "DejaVu Sans, sans-serif",
    style = "",
  } = options;
  return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="${family}" font-size="${size}" font-weight="${weight}" fill="${fill}"${style ? ` style="${style}"` : ""}>${escapeXml(value)}</text>`;
}

function textBlock(x, y, lines, options = {}) {
  const {
    size = 16,
    weight = 400,
    fill = C.ink,
    anchor = "middle",
    lineHeight = Math.round(size * 1.28),
    family = "DejaVu Sans, sans-serif",
  } = options;
  const content = lines
    .map(
      (line, index) =>
        `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeXml(line)}</tspan>`,
    )
    .join("");
  return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="${family}" font-size="${size}" font-weight="${weight}" fill="${fill}">${content}</text>`;
}

function groupBox({
  x,
  y,
  w,
  h,
  title,
  color = C.blue,
  fill = "none",
  dash = "9 7",
  titleAlign = "center",
}) {
  const titleX = titleAlign === "left" ? x + 18 : x + w / 2;
  const anchor = titleAlign === "left" ? "start" : "middle";
  return `<g>
  <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${color}" stroke-width="2" stroke-dasharray="${dash}"/>
  <rect x="${titleX - (titleAlign === "left" ? 8 : Math.max(72, title.length * 5.6))}" y="${y - 13}" width="${titleAlign === "left" ? Math.max(150, title.length * 10) : Math.max(144, title.length * 11.2)}" height="26" fill="${C.page}"/>
  ${lineText(titleX, y + 6, title, { size: 18, weight: 700, anchor })}
</g>`;
}

function sectionBox({ x, y, w, h, title, color = C.line }) {
  return `<g>
  <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${C.white}" fill-opacity="0.58" stroke="${color}" stroke-width="1.4" stroke-dasharray="4 4"/>
  ${lineText(x + 12, y + 23, title, { size: 14, weight: 700 })}
</g>`;
}

function nodeBox({
  x,
  y,
  w,
  h,
  title,
  lines = [],
  iconKey = null,
  stroke = C.line,
  fill = C.white,
  titleSize = 16,
  bodySize = 12,
  dashed = false,
  align = "center",
}) {
  const iconSpace = iconKey ? 42 : 0;
  const titleX = align === "left" ? x + 14 + iconSpace : x + w / 2 + iconSpace / 3;
  const anchor = align === "left" ? "start" : "middle";
  const titleY = lines.length ? y + 28 : y + h / 2 + 6;
  const bodyY = titleY + 24;
  return `<g>
  <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${fill}" stroke="${stroke}" stroke-width="1.6"${dashed ? ' stroke-dasharray="6 5"' : ""}/>
  ${iconKey ? icon(iconKey, x + 12, y + (h - 28) / 2, 28) : ""}
  ${lineText(titleX, titleY, title, { size: titleSize, weight: 700, anchor })}
  ${lines.length ? textBlock(titleX, bodyY, lines, { size: bodySize, weight: 400, fill: C.muted, anchor, lineHeight: bodySize + 5 }) : ""}
</g>`;
}

function logoLabel(key, x, y, size, label, sublabel = "") {
  return `<g>
  ${icon(key, x - size / 2, y, size, label)}
  ${lineText(x, y + size + 20, label, { size: 13, weight: 600, anchor: "middle" })}
  ${sublabel ? lineText(x, y + size + 36, sublabel, { size: 10, weight: 400, fill: C.muted, anchor: "middle" }) : ""}
</g>`;
}

function databaseNode({ x, y, w = 180, h = 140, title, iconKey, lines = [] }) {
  const top = 18;
  return `<g>
  <rect x="${x}" y="${y + top}" width="${w}" height="${h - top * 2}" fill="${C.white}" stroke="${C.line}" stroke-width="1.7"/>
  <ellipse cx="${x + w / 2}" cy="${y + top}" rx="${w / 2}" ry="${top}" fill="${C.white}" stroke="${C.line}" stroke-width="1.7"/>
  <ellipse cx="${x + w / 2}" cy="${y + h - top}" rx="${w / 2}" ry="${top}" fill="${C.white}" stroke="${C.line}" stroke-width="1.7"/>
  ${icon(iconKey, x + w / 2 - 27, y + 35, 54)}
  ${lineText(x + w / 2, y + 105, title, { size: 16, weight: 700, anchor: "middle" })}
  ${lines.length ? textBlock(x + w / 2, y + 124, lines, { size: 11, fill: C.muted, anchor: "middle", lineHeight: 14 }) : ""}
</g>`;
}

function diamond({ x, y, w, h, title, lines = [], stroke = C.line, fill = C.white }) {
  const points = `${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}`;
  return `<g>
  <polygon points="${points}" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/>
  ${lineText(x + w / 2, y + h / 2 - (lines.length ? 6 : -5), title, { size: 15, weight: 700, anchor: "middle" })}
  ${lines.length ? textBlock(x + w / 2, y + h / 2 + 16, lines, { size: 11, fill: C.muted, anchor: "middle", lineHeight: 14 }) : ""}
</g>`;
}

const edgeStyles = {
  ink: { color: C.line, marker: "arrow-ink", dash: "" },
  data: { color: C.teal, marker: "arrow-data", dash: "" },
  async: { color: C.purple, marker: "arrow-async", dash: "7 6" },
  subtle: { color: "#89919D", marker: "arrow-subtle", dash: "4 5" },
};

function edge(points, options = {}) {
  const { kind = "ink", label = "", labelX = null, labelY = null, width = 1.6 } = options;
  const style = edgeStyles[kind];
  const path = points.map(([px, py], index) => `${index === 0 ? "M" : "L"} ${px} ${py}`).join(" ");
  return `<g>
  <path d="${path}" fill="none" stroke="${style.color}" stroke-width="${width}"${style.dash ? ` stroke-dasharray="${style.dash}"` : ""} marker-end="url(#${style.marker})"/>
  ${label && labelX !== null && labelY !== null ? edgeLabel(labelX, labelY, label) : ""}
</g>`;
}

function edgeLabel(x, y, value) {
  const width = Math.max(54, value.length * 7.2 + 16);
  return `<g>
  <rect x="${x - width / 2}" y="${y - 13}" width="${width}" height="22" rx="2" fill="${C.page}" fill-opacity="0.96"/>
  ${lineText(x, y + 3, value, { size: 11, weight: 500, fill: C.muted, anchor: "middle" })}
</g>`;
}

function tableBox({ x, y, w, title, fields, color = C.blue }) {
  const headerH = 36;
  const rowH = 23;
  const h = headerH + fields.length * rowH + 12;
  const compact = w < 180;
  const fieldSize = compact ? 9.8 : 12;
  const typeSize = compact ? 8.6 : 11;
  const fieldX = x + (compact ? 43 : 48);
  const rows = fields
    .map(([tag, name, type], index) => {
      const yy = y + headerH + 20 + index * rowH;
      return `<g>
      ${tag ? `<rect x="${x + 10}" y="${yy - 13}" width="28" height="17" rx="2" fill="${tag === "PK" ? C.blueSoft : C.graySoft}" stroke="${tag === "PK" ? color : C.gridMajor}"/>${lineText(x + 24, yy, tag, { size: 9, weight: 700, fill: tag === "PK" ? color : C.muted, anchor: "middle" })}` : ""}
      ${lineText(fieldX, yy, name, { size: fieldSize, weight: 500 })}
      ${compact ? "" : lineText(x + w - 8, yy, type, { size: typeSize, weight: 400, fill: C.muted, anchor: "end" })}
    </g>`;
    })
    .join("");
  return {
    h,
    svg: `<g>
    <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${C.white}" stroke="${color}" stroke-width="1.5"/>
    <rect x="${x}" y="${y}" width="${w}" height="${headerH}" fill="${C.blueSoft}" stroke="${color}" stroke-width="1.5"/>
    ${icon("postgresql", x + 10, y + 7, 22)}
    ${lineText(x + 42, y + 24, title, { size: compact ? 11 : 14, weight: 700 })}
    ${rows}
  </g>`,
  };
}

function frame({ title, subtitle, body, width = 1920, height = 1080 }) {
  const gridX = 70;
  const gridY = 150;
  const gridW = width - 120;
  const gridH = height - 185;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
<title>${escapeXml(title)}</title>
<desc>${escapeXml(subtitle)}</desc>
<defs>
  <pattern id="minor-grid" width="12" height="12" patternUnits="userSpaceOnUse">
    <path d="M 12 0 L 0 0 0 12" fill="none" stroke="${C.gridMinor}" stroke-width="0.65"/>
  </pattern>
  <pattern id="major-grid" width="60" height="60" patternUnits="userSpaceOnUse">
    <rect width="60" height="60" fill="url(#minor-grid)"/>
    <path d="M 60 0 L 0 0 0 60" fill="none" stroke="${C.gridMajor}" stroke-width="0.9"/>
  </pattern>
  <marker id="arrow-ink" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 Z" fill="${C.line}"/></marker>
  <marker id="arrow-data" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 Z" fill="${C.teal}"/></marker>
  <marker id="arrow-async" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 Z" fill="${C.purple}"/></marker>
  <marker id="arrow-subtle" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 Z" fill="#89919D"/></marker>
</defs>
<rect x="0" y="0" width="${width}" height="${height}" fill="${C.page}"/>
${lineText(42, 96, title, { size: 76, weight: 400, family: "DejaVu Serif, serif" })}
${lineText(46, 128, subtitle, { size: 14, weight: 400, fill: C.muted })}
<rect x="${gridX}" y="${gridY}" width="${gridW}" height="${gridH}" fill="url(#major-grid)" stroke="${C.gridMajor}" stroke-width="1"/>
${body}
</svg>`;
}

function renderSystemDesign() {
  const body = [];

  body.push(groupBox({ x: 280, y: 190, w: 390, h: 520, title: "Frontend", color: C.blue }));
  body.push(groupBox({ x: 710, y: 190, w: 790, h: 520, title: "Backend & AI", color: C.magenta }));
  body.push(groupBox({ x: 1540, y: 190, w: 280, h: 520, title: "Data Stores", color: C.blue, dash: "4 5" }));
  body.push(groupBox({ x: 680, y: 790, w: 760, h: 210, title: "Controlled External Services", color: C.orange, dash: "6 5" }));
  body.push(groupBox({ x: 1480, y: 790, w: 340, h: 210, title: "Build & Operations", color: C.purple, dash: "6 5" }));

  body.push(icon("users", 115, 360, 100));
  body.push(lineText(165, 480, "Users", { size: 20, weight: 700, anchor: "middle" }));
  body.push(lineText(165, 505, "Citizen / Legal Professional", { size: 12, weight: 400, fill: C.muted, anchor: "middle" }));

  body.push(logoLabel("react", 380, 220, 44, "React"));
  body.push(logoLabel("typescript", 465, 220, 44, "TypeScript"));
  body.push(logoLabel("caddy", 555, 220, 44, "Caddy"));
  body.push(logoLabel("docker", 630, 220, 44, "Docker"));

  body.push(nodeBox({ x: 335, y: 330, w: 280, h: 105, title: "Web Application", lines: ["Saved workspace · guest sessionStorage"], iconKey: "monitor", stroke: C.blue }));
  body.push(nodeBox({ x: 335, y: 485, w: 280, h: 100, title: "Caddy Edge", lines: ["TLS · security headers · /api routing"], iconKey: "caddy", stroke: C.blue }));
  body.push(nodeBox({ x: 335, y: 625, w: 280, h: 60, title: "Frontend Container", iconKey: "docker", stroke: C.blue }));

  body.push(logoLabel("fastapi", 860, 210, 48, "FastAPI"));
  body.push(logoLabel("celery", 955, 210, 48, "Celery"));
  body.push(logoLabel("qwen", 1050, 210, 48, "Qwen3"));
  body.push(logoLabel("huggingface", 1145, 210, 48, "BGE-M3"));
  body.push(logoLabel("google", 1240, 210, 48, "OIDC"));
  body.push(logoLabel("docker", 1335, 210, 48, "Docker"));

  body.push(sectionBox({ x: 750, y: 330, w: 330, h: 165, title: "Presentation Layer", color: C.magenta }));
  body.push(nodeBox({ x: 785, y: 380, w: 125, h: 70, title: "Auth & CRUD", lines: ["OIDC · sessions"], stroke: C.magenta }));
  body.push(nodeBox({ x: 930, y: 380, w: 125, h: 70, title: "Chat API", lines: ["/api/chat"], stroke: C.magenta }));

  body.push(sectionBox({ x: 750, y: 525, w: 330, h: 150, title: "Business Services", color: C.magenta }));
  body.push(nodeBox({ x: 780, y: 570, w: 130, h: 70, title: "Legal Tools", lines: ["contracts · articles"], stroke: C.magenta }));
  body.push(nodeBox({ x: 925, y: 570, w: 130, h: 70, title: "Chat Service", lines: ["memory · cache"], stroke: C.magenta }));

  body.push(sectionBox({ x: 1120, y: 330, w: 340, h: 345, title: "Local AI Runtime", color: C.purple }));
  body.push(nodeBox({ x: 1150, y: 380, w: 125, h: 75, title: "Qwen3-14B", lines: ["generation"], iconKey: "qwen", stroke: C.purple }));
  body.push(nodeBox({ x: 1300, y: 380, w: 125, h: 75, title: "BGE-M3", lines: ["1024-d vectors"], iconKey: "huggingface", stroke: C.purple }));
  body.push(nodeBox({ x: 1150, y: 500, w: 125, h: 75, title: "Celery Worker", lines: ["verification"], iconKey: "celery", stroke: C.purple }));
  body.push(nodeBox({ x: 1300, y: 500, w: 125, h: 75, title: "Celery Beat", lines: ["24-hour jobs"], iconKey: "clock", stroke: C.purple }));
  body.push(nodeBox({ x: 1150, y: 605, w: 275, h: 45, title: "Read-only model volumes", iconKey: "box", stroke: C.purple }));

  body.push(databaseNode({ x: 1585, y: 280, w: 190, h: 160, title: "PostgreSQL 16", iconKey: "postgresql", lines: ["pgvector · BM25 · system of record"] }));
  body.push(databaseNode({ x: 1585, y: 480, w: 190, h: 150, title: "Neo4j 5.26", iconKey: "neo4j", lines: ["legal graph projection"] }));
  body.push(nodeBox({ x: 1585, y: 650, w: 190, h: 40, title: "Docker volumes", iconKey: "docker", stroke: C.blue }));

  body.push(logoLabel("google", 765, 825, 48, "Google OIDC"));
  body.push(logoLabel("search", 925, 825, 48, "Tavily"));
  body.push(logoLabel("huggingface", 1085, 825, 48, "Hugging Face"));
  body.push(logoLabel("scale", 1270, 825, 48, "Official Legal Sources"));

  body.push(logoLabel("sqlite", 1545, 825, 48, "SQLite"));
  body.push(logoLabel("file", 1645, 825, 48, "JSONL"));
  body.push(logoLabel("python", 1740, 825, 48, "Alembic"));
  body.push(nodeBox({ x: 1515, y: 925, w: 270, h: 50, title: "Reindex · migrate · model init", iconKey: "workflow", stroke: C.purple }));

  body.push(edge([[215, 405], [280, 405], [280, 382], [335, 382]], { kind: "ink", label: "HTTPS", labelX: 270, labelY: 390 }));
  body.push(edge([[475, 435], [475, 485]], { kind: "ink" }));
  body.push(edge([[475, 585], [475, 625]], { kind: "ink" }));
  body.push(edge([[615, 535], [690, 535], [690, 415], [785, 415]], { kind: "data", label: "/api/*", labelX: 690, labelY: 397 }));
  body.push(edge([[910, 415], [930, 415]], { kind: "data" }));
  body.push(edge([[992, 450], [992, 570]], { kind: "ink" }));
  body.push(edge([[910, 605], [925, 605]], { kind: "ink" }));
  body.push(edge([[1055, 605], [1100, 605], [1100, 418], [1150, 418]], { kind: "data" }));
  body.push(edge([[1055, 605], [1100, 605], [1100, 538], [1150, 538]], { kind: "async" }));
  body.push(edge([[1275, 418], [1300, 418]], { kind: "data" }));
  body.push(edge([[1080, 410], [1520, 410], [1520, 360], [1585, 360]], { kind: "ink", label: "SQL / vectors", labelX: 1450, labelY: 395 }));
  body.push(edge([[1080, 600], [1505, 600], [1505, 555], [1585, 555]], { kind: "data", label: "node_id / chunk_id", labelX: 1450, labelY: 584 }));
  body.push(edge([[1212, 575], [1212, 790], [925, 790], [925, 825]], { kind: "async", label: "freshness", labelX: 1135, labelY: 775 }));
  body.push(edge([[1338, 455], [1338, 790], [1085, 790], [1085, 825]], { kind: "subtle", label: "model init", labelX: 1260, labelY: 775 }));
  body.push(edge([[1270, 873], [1270, 900], [1420, 900], [1420, 360], [1585, 360]], { kind: "subtle", label: "verified sources", labelX: 1475, labelY: 882 }));
  body.push(edge([[1645, 873], [1645, 925]], { kind: "subtle" }));
  body.push(edge([[1650, 925], [1500, 925], [1500, 555], [1585, 555]], { kind: "async", label: "projection sync", labelX: 1518, labelY: 735 }));

  return frame({
    title: "System design",
    subtitle: "VLegalAI · containerized HybridRAG and GraphRAG legal intelligence platform",
    body: body.join("\n"),
  });
}

function stageLabel(number, x, y, title, color = C.blue) {
  return `<g>
  <circle cx="${x}" cy="${y}" r="18" fill="${color}"/>
  ${lineText(x, y + 6, number, { size: 15, weight: 800, fill: C.white, anchor: "middle" })}
  ${lineText(x + 28, y + 6, title, { size: 18, weight: 700 })}
</g>`;
}

function noteBox({ x, y, w, h, title, lines = [], color = C.orange, iconKey = "shield" }) {
  return `<g>
  <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${C.page}" stroke="${color}" stroke-width="1.5" stroke-dasharray="5 4"/>
  ${icon(iconKey, x + 14, y + 14, 28)}
  ${lineText(x + 52, y + 28, title, { size: 14, weight: 700 })}
  ${textBlock(x + 18, y + 54, lines, { size: 11, weight: 400, fill: C.muted, anchor: "start", lineHeight: 16 })}
</g>`;
}

function renderPostgresqlErd() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 790, h: 770, title: "Identity & Conversation", color: C.blue }));
  body.push(groupBox({ x: 910, y: 195, w: 540, h: 770, title: "Legal Registry & Retrieval", color: C.teal }));
  body.push(groupBox({ x: 1480, y: 195, w: 350, h: 770, title: "Product & Runtime", color: C.orange }));

  body.push(logoLabel("postgresql", 145, 215, 44, "PostgreSQL 16", "system of record"));
  body.push(noteBox({
    x: 610,
    y: 815,
    w: 240,
    h: 115,
    title: "Protected fields",
    lines: ["AES-256-GCM ciphertext", "SHA-256 integrity hashes", "Ownership enforced by user_id"],
    color: C.green,
    iconKey: "lock",
  }));

  const appUser = tableBox({
    x: 115, y: 300, w: 225, title: "APP_USER", color: C.blue,
    fields: [
      ["PK", "id", "uuid"],
      ["UK", "email", "varchar"],
      ["", "display_name", "varchar"],
      ["", "role", "varchar"],
      ["", "is_active", "bool"],
      ["", "last_login_at", "timestamptz"],
    ],
  });
  const sso = tableBox({
    x: 380, y: 270, w: 225, title: "SSO_IDENTITY", color: C.blue,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "user_id", "uuid"],
      ["", "issuer", "varchar"],
      ["", "subject", "varchar"],
      ["", "provider", "varchar"],
      ["", "claims", "jsonb"],
    ],
  });
  const conversation = tableBox({
    x: 115, y: 565, w: 225, title: "CONVERSATION", color: C.blue,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "user_id", "uuid"],
      ["", "title", "varchar"],
      ["", "status", "varchar"],
      ["", "retrieval_mode", "varchar"],
      ["", "updated_at", "timestamptz"],
    ],
  });
  const message = tableBox({
    x: 380, y: 505, w: 225, title: "CHAT_MESSAGE", color: C.blue,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "conversation_id", "uuid"],
      ["", "role", "varchar"],
      ["", "content_ciphertext", "text"],
      ["", "content_hash", "varchar"],
      ["", "sources", "jsonb"],
      ["", "verification", "jsonb"],
      ["", "token_count", "int"],
    ],
  });
  const summary = tableBox({
    x: 640, y: 505, w: 215, title: "CONVERSATION_SUMMARY", color: C.blue,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "conversation_id", "uuid"],
      ["", "summary_ciphertext", "text"],
      ["", "summary_hash", "varchar"],
      ["", "source_message_count", "int"],
      ["", "embedding_model", "varchar"],
      ["", "embedding", "vector(1024)"],
    ],
  });

  const legalDoc = tableBox({
    x: 935, y: 260, w: 235, title: "LEGAL_DOCUMENT", color: C.teal,
    fields: [
      ["PK", "id", "uuid"],
      ["UK", "external_doc_id", "varchar"],
      ["", "code", "varchar"],
      ["", "title", "text"],
      ["", "status", "varchar"],
      ["", "checksum", "varchar"],
      ["", "version", "int"],
      ["", "verified_at", "timestamptz"],
      ["", "verification_payload", "jsonb"],
    ],
  });
  const legalChunk = tableBox({
    x: 1190, y: 260, w: 235, title: "LEGAL_CHUNK", color: C.teal,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "document_id", "uuid"],
      ["UK", "external_chunk_id", "varchar"],
      ["", "node_id", "varchar"],
      ["", "chunk_type", "varchar"],
      ["", "citation", "text"],
      ["", "text", "text"],
      ["", "text_hash", "varchar"],
      ["", "ordinal", "int"],
      ["", "version", "int"],
    ],
  });
  const graphChunk = tableBox({
    x: 935, y: 610, w: 235, title: "GRAPHRAG_CHUNK", color: C.teal,
    fields: [
      ["PK", "chunk_id", "varchar"],
      ["", "doc_id", "varchar"],
      ["", "node_id", "varchar"],
      ["", "chunk_type", "varchar"],
      ["", "citation", "text"],
      ["", "text", "text"],
      ["", "law_code", "varchar"],
      ["", "law_version", "int"],
      ["", "embedding_model", "varchar"],
      ["", "embedding", "vector(1024)"],
    ],
  });
  const answerCache = tableBox({
    x: 1190, y: 630, w: 235, title: "LEGAL_ANSWER_CACHE", color: C.teal,
    fields: [
      ["PK", "id", "uuid"],
      ["UK", "query_hash", "varchar"],
      ["", "query_ciphertext", "text"],
      ["", "answer_ciphertext", "text"],
      ["", "query_embedding", "vector(1024)"],
      ["", "sources", "jsonb"],
      ["", "verification", "jsonb"],
      ["", "law_fingerprint", "varchar"],
      ["", "expires_at", "timestamptz"],
      ["", "hit_count", "bigint"],
    ],
  });

  const artifact = tableBox({
    x: 1500, y: 245, w: 145, title: "ARTIFACT", color: C.orange,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "user_id", "uuid"],
      ["", "kind", "varchar"],
      ["", "content_ciphertext", "text"],
      ["", "metadata", "jsonb"],
    ],
  });
  const article = tableBox({
    x: 1665, y: 245, w: 145, title: "ARTICLE", color: C.orange,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "author_id", "uuid"],
      ["UK", "slug", "varchar"],
      ["", "content", "text"],
      ["", "web_sources", "jsonb"],
    ],
  });
  const packet = tableBox({
    x: 1500, y: 485, w: 145, title: "SIGNATURE_PACKET", color: C.orange,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "user_id", "uuid"],
      ["", "document_ciphertext", "text"],
      ["", "document_hash", "varchar"],
      ["", "signers", "jsonb"],
      ["", "audit_log", "jsonb"],
    ],
  });
  const feedback = tableBox({
    x: 1665, y: 485, w: 145, title: "USER_FEEDBACK", color: C.orange,
    fields: [
      ["PK", "id", "uuid"],
      ["FK", "user_id", "uuid"],
      ["", "message_ciphertext", "text"],
      ["", "page", "varchar"],
      ["", "created_at", "timestamptz"],
    ],
  });
  const rateLimit = tableBox({
    x: 1535, y: 745, w: 240, title: "GUEST_RATE_LIMIT", color: C.orange,
    fields: [
      ["PK", "subject_hash", "varchar"],
      ["PK", "window_kind", "varchar"],
      ["PK", "window_start", "timestamptz"],
      ["", "request_count", "int"],
    ],
  });

  body.push(edge([[340, 360], [360, 360], [360, 335], [380, 335]], { kind: "ink", label: "1 : N", labelX: 360, labelY: 345 }));
  body.push(edge([[225, 450], [225, 565]], { kind: "ink", label: "owns", labelX: 225, labelY: 520 }));
  body.push(edge([[340, 650], [360, 650], [360, 590], [380, 590]], { kind: "ink", label: "1 : N", labelX: 360, labelY: 635 }));
  body.push(edge([[340, 680], [620, 680], [620, 590], [640, 590]], { kind: "ink", label: "1 : 0..1", labelX: 620, labelY: 665 }));
  body.push(edge([[1170, 350], [1190, 350]], { kind: "data", label: "1 : N", labelX: 1180, labelY: 332 }));
  body.push(edge([[1305, 530], [1305, 600], [1050, 600], [1050, 610]], { kind: "subtle", label: "external_chunk_id", labelX: 1175, labelY: 588 }));
  body.push(lineText(1655, 712, "user_id / author_id → APP_USER.id", { size: 11, weight: 600, fill: C.muted, anchor: "middle" }));
  body.push(edge([[1485, 325], [1500, 325]], { kind: "subtle" }));
  body.push(edge([[1650, 325], [1665, 325]], { kind: "subtle" }));
  body.push(edge([[1485, 565], [1500, 565]], { kind: "subtle" }));
  body.push(edge([[1650, 565], [1665, 565]], { kind: "subtle" }));

  body.push(appUser.svg, sso.svg, conversation.svg, message.svg, summary.svg);
  body.push(legalDoc.svg, legalChunk.svg, graphChunk.svg, answerCache.svg);
  body.push(artifact.svg, article.svg, packet.svg, feedback.svg, rateLimit.svg);

  return frame({
    title: "PostgreSQL ERD",
    subtitle: "VLegalAI · ownership, encrypted chat memory, legal corpus, semantic cache and product records",
    body: body.join("\n"),
  });
}

function renderDatabaseDesign() {
  const body = [];

  body.push(groupBox({ x: 90, y: 205, w: 300, h: 710, title: "Access Layer", color: C.blue }));
  body.push(groupBox({ x: 430, y: 205, w: 900, h: 710, title: "PostgreSQL 16 + pgvector — System of Record", color: C.teal }));
  body.push(groupBox({ x: 1370, y: 205, w: 450, h: 430, title: "Neo4j 5.26 — Graph Projection", color: C.purple }));
  body.push(groupBox({ x: 1370, y: 690, w: 450, h: 225, title: "Build Artifacts", color: C.orange }));

  body.push(logoLabel("react", 160, 235, 44, "Browser"));
  body.push(nodeBox({ x: 120, y: 340, w: 240, h: 90, title: "Guest sessionStorage", lines: ["completed guest messages only"], iconKey: "browser", stroke: C.blue }));
  body.push(logoLabel("fastapi", 170, 485, 48, "FastAPI"));
  body.push(nodeBox({ x: 120, y: 585, w: 240, h: 85, title: "SQLAlchemy / API", lines: ["transactions · ownership · encryption"], iconKey: "server", stroke: C.blue }));
  body.push(logoLabel("celery", 170, 720, 48, "Celery Worker + Beat"));

  body.push(logoLabel("postgresql", 500, 225, 46, "PostgreSQL"));
  body.push(sectionBox({ x: 470, y: 315, w: 390, h: 250, title: "Identity, Chat & Product", color: C.teal }));
  body.push(nodeBox({ x: 500, y: 365, w: 155, h: 70, title: "Identity", lines: ["app_user", "sso_identity"], iconKey: "key", stroke: C.teal }));
  body.push(nodeBox({ x: 675, y: 365, w: 155, h: 70, title: "Chat Memory", lines: ["conversation · message", "summary vector(1024)"], iconKey: "message", stroke: C.teal }));
  body.push(nodeBox({ x: 500, y: 465, w: 330, h: 65, title: "Product Content", lines: ["artifact · article · signature_packet · user_feedback"], iconKey: "files", stroke: C.teal }));

  body.push(sectionBox({ x: 890, y: 315, w: 400, h: 250, title: "Legal Retrieval", color: C.teal }));
  body.push(nodeBox({ x: 920, y: 365, w: 155, h: 70, title: "Legal Registry", lines: ["legal_document", "legal_chunk"], iconKey: "scale", stroke: C.teal }));
  body.push(nodeBox({ x: 1095, y: 365, w: 165, h: 70, title: "GraphRAG Chunks", lines: ["HNSW cosine", "GIN lexical"], iconKey: "search", stroke: C.teal }));
  body.push(nodeBox({ x: 920, y: 465, w: 340, h: 65, title: "Semantic Answer Cache", lines: ["exact hash + vector(1024) · law fingerprint · TTL"], iconKey: "refresh", stroke: C.teal }));

  body.push(sectionBox({ x: 470, y: 610, w: 820, h: 255, title: "Runtime & Protection", color: C.green }));
  body.push(nodeBox({ x: 500, y: 665, w: 230, h: 80, title: "Runtime Coordination", lines: ["guest_rate_limit · advisory locks", "Celery broker / results"], iconKey: "clock", stroke: C.green }));
  body.push(nodeBox({ x: 760, y: 665, w: 230, h: 80, title: "Application Encryption", lines: ["AES-256-GCM ciphertext", "SHA-256 integrity hash"], iconKey: "lock", stroke: C.green }));
  body.push(nodeBox({ x: 1020, y: 665, w: 240, h: 80, title: "Database Controls", lines: ["FK / unique constraints", "transactions · indexed ownership"], iconKey: "shield", stroke: C.green }));
  body.push(noteBox({
    x: 550, y: 775, w: 660, h: 65, title: "Durability boundary",
    lines: ["PostgreSQL is authoritative. Neo4j, SQLite and JSONL are projections or build artifacts."],
    color: C.green, iconKey: "check",
  }));

  body.push(logoLabel("neo4j", 1450, 235, 46, "Neo4j"));
  body.push(nodeBox({ x: 1410, y: 340, w: 170, h: 80, title: ":LegalNode", lines: ["unique node_id"], iconKey: "network", stroke: C.purple }));
  body.push(nodeBox({ x: 1600, y: 340, w: 180, h: 80, title: ":LegalChunk", lines: ["unique chunk_id"], iconKey: "file", stroke: C.purple }));
  body.push(nodeBox({ x: 1410, y: 470, w: 370, h: 105, title: "Typed Relationships", lines: ["CHUNK_OF · BELONGS_TO · CITES · GUIDES", "AMENDS · REPLACES · semantic / risk / process"], iconKey: "merge", stroke: C.purple }));

  body.push(logoLabel("sqlite", 1435, 725, 42, "SQLite", "docs · nodes · edges · chunks · FTS5"));
  body.push(logoLabel("file", 1585, 725, 42, "JSONL", "bulk interchange"));
  body.push(logoLabel("python", 1740, 725, 42, "Reindex", "bootstrap only"));

  body.push(edge([[360, 630], [410, 630], [410, 400], [500, 400]], { kind: "data", label: "SQL", labelX: 410, labelY: 615 }));
  body.push(edge([[360, 630], [410, 630], [410, 500], [500, 500]], { kind: "data" }));
  body.push(edge([[215, 430], [215, 585]], { kind: "subtle", label: "history per request", labelX: 280, labelY: 530 }));
  body.push(edge([[1210, 565], [1340, 565], [1340, 380], [1410, 380]], { kind: "async", label: "chunk_id · node_id · doc_id", labelX: 1350, labelY: 545 }));
  body.push(edge([[1580, 380], [1600, 380]], { kind: "async", label: "CHUNK_OF", labelX: 1590, labelY: 360 }));
  body.push(edge([[1495, 420], [1495, 470]], { kind: "async" }));
  body.push(edge([[1435, 790], [1340, 790], [1340, 475], [1260, 475]], { kind: "subtle", label: "bulk upsert", labelX: 1345, labelY: 775 }));
  body.push(edge([[1435, 790], [1360, 790], [1360, 520], [1410, 520]], { kind: "async", label: "bulk graph sync", labelX: 1380, labelY: 775 }));
  body.push(edge([[1585, 770], [1480, 770]], { kind: "subtle" }));

  return frame({
    title: "Database design",
    subtitle: "VLegalAI · authoritative relational store with graph and build-time projections",
    body: body.join("\n"),
  });
}

function renderApplicationWorkflow() {
  const body = [];

  body.push(icon("users", 95, 250, 74));
  body.push(lineText(132, 345, "User", { size: 18, weight: 700, anchor: "middle" }));
  body.push(nodeBox({ x: 215, y: 255, w: 190, h: 80, title: "Open VLegalAI", lines: ["React workspace"], iconKey: "react", stroke: C.blue }));
  body.push(diamond({ x: 455, y: 245, w: 180, h: 100, title: "Google session", lines: ["available?"], stroke: C.orange }));

  body.push(groupBox({ x: 90, y: 440, w: 820, h: 435, title: "Guest Workspace", color: C.blue }));
  body.push(stageLabel("1", 130, 500, "Temporary legal research", C.blue));
  body.push(nodeBox({ x: 125, y: 545, w: 185, h: 85, title: "Browser Memory", lines: ["sessionStorage", "completed messages"], iconKey: "browser", stroke: C.blue }));
  body.push(nodeBox({ x: 345, y: 545, w: 185, h: 85, title: "Ask Question", lines: ["send recent history"], iconKey: "message", stroke: C.blue }));
  body.push(nodeBox({ x: 565, y: 545, w: 185, h: 85, title: "Guest Rate Limit", lines: ["hashed ID + IP", "minute / hour windows"], iconKey: "clock", stroke: C.blue }));
  body.push(nodeBox({ x: 675, y: 700, w: 190, h: 90, title: "Temporary Answer", lines: ["grounded + verified", "no conversation rows"], iconKey: "check", stroke: C.blue }));
  body.push(noteBox({
    x: 125, y: 700, w: 470, h: 115, title: "Guest persistence boundary",
    lines: ["Chat stays in the browser.", "Only rate-limit counters are written to PostgreSQL.", "Refresh / close clears the temporary workspace."],
    color: C.blue, iconKey: "lock",
  }));

  body.push(groupBox({ x: 950, y: 195, w: 880, h: 680, title: "Authenticated Workspace", color: C.magenta }));
  body.push(stageLabel("2", 990, 250, "Google OIDC + durable workspace", C.magenta));
  body.push(logoLabel("google", 1045, 300, 44, "Google OIDC", "Authorization Code + PKCE"));
  body.push(nodeBox({ x: 1165, y: 295, w: 210, h: 85, title: "Account Session", lines: ["upsert user + SSO identity", "HttpOnly cookie"], iconKey: "key", stroke: C.magenta }));
  body.push(diamond({ x: 1430, y: 285, w: 180, h: 105, title: "Choose", lines: ["workspace"], stroke: C.magenta }));

  body.push(nodeBox({ x: 995, y: 465, w: 185, h: 90, title: "Saved Chat", lines: ["decrypt summary", "+ recent messages"], iconKey: "message", stroke: C.magenta }));
  body.push(nodeBox({ x: 1205, y: 465, w: 185, h: 90, title: "Contracts", lines: ["draft · review", "compare · save artifact"], iconKey: "files", stroke: C.magenta }));
  body.push(nodeBox({ x: 1415, y: 465, w: 185, h: 90, title: "Articles", lines: ["web research", "reviewer saves"], iconKey: "globe", stroke: C.magenta }));
  body.push(nodeBox({ x: 1625, y: 465, w: 165, h: 90, title: "Signature", lines: ["packet · signers", "audit log"], iconKey: "file", stroke: C.magenta }));

  body.push(sectionBox({ x: 990, y: 630, w: 800, h: 190, title: "Shared Legal Intelligence", color: C.teal }));
  body.push(nodeBox({ x: 1025, y: 685, w: 195, h: 85, title: "HybridRAG", lines: ["dense + BM25 + graph"], iconKey: "search", stroke: C.teal }));
  body.push(nodeBox({ x: 1250, y: 685, w: 195, h: 85, title: "Freshness Check", lines: ["official sources", "status verdict"], iconKey: "shield", stroke: C.teal }));
  body.push(nodeBox({ x: 1475, y: 685, w: 280, h: 85, title: "Persist Owned Result", lines: ["encrypted answer · sources · verification", "rolling summary + vector"], iconKey: "postgresql", stroke: C.teal }));

  body.push(edge([[405, 295], [455, 295]], { kind: "ink" }));
  body.push(edge([[545, 345], [545, 415], [220, 415], [220, 545]], { kind: "ink", label: "No", labelX: 520, labelY: 405 }));
  body.push(edge([[635, 295], [925, 295], [925, 325], [1000, 325]], { kind: "data", label: "Yes", labelX: 900, labelY: 280 }));
  body.push(edge([[310, 587], [345, 587]], { kind: "data" }));
  body.push(edge([[530, 587], [565, 587]], { kind: "data" }));
  body.push(edge([[750, 587], [790, 587], [790, 700]], { kind: "data", label: "HybridRAG", labelX: 800, labelY: 640 }));
  body.push(edge([[1090, 325], [1165, 337]], { kind: "data" }));
  body.push(edge([[1375, 337], [1430, 337]], { kind: "data" }));
  body.push(edge([[1520, 390], [1520, 430], [1085, 430], [1085, 465]], { kind: "ink" }));
  body.push(edge([[1520, 430], [1298, 430], [1298, 465]], { kind: "ink" }));
  body.push(edge([[1520, 430], [1508, 430], [1508, 465]], { kind: "ink" }));
  body.push(edge([[1520, 430], [1708, 430], [1708, 465]], { kind: "ink" }));
  body.push(edge([[1085, 555], [1085, 685]], { kind: "data" }));
  body.push(edge([[1298, 555], [1298, 630], [1120, 630], [1120, 685]], { kind: "data" }));
  body.push(edge([[1508, 555], [1508, 630], [1348, 630], [1348, 685]], { kind: "data" }));
  body.push(edge([[1708, 555], [1708, 685]], { kind: "data" }));
  body.push(edge([[1220, 727], [1250, 727]], { kind: "data" }));
  body.push(edge([[1445, 727], [1475, 727]], { kind: "data" }));

  return frame({
    title: "Application workflow",
    subtitle: "VLegalAI · guest and authenticated journeys converge on the same verified legal intelligence",
    body: body.join("\n"),
  });
}

function renderLegalDataPipeline() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 1740, h: 310, title: "Bootstrap / Reindex Pipeline", color: C.blue }));
  body.push(stageLabel("1", 130, 245, "Build a deterministic legal corpus", C.blue));

  body.push(nodeBox({ x: 120, y: 315, w: 180, h: 90, title: "Curated DOCX", lines: ["Vietnamese legal corpus", "source-controlled input"], iconKey: "file", stroke: C.blue }));
  body.push(nodeBox({ x: 345, y: 315, w: 190, h: 90, title: "Hierarchy Parser", lines: ["document → chapter → section", "article → clause → point"], iconKey: "workflow", stroke: C.blue }));
  body.push(nodeBox({ x: 580, y: 315, w: 190, h: 90, title: "Graph Extraction", lines: ["structure · terminology · domain", "time · risk · precedent"], iconKey: "network", stroke: C.purple }));
  body.push(nodeBox({ x: 815, y: 315, w: 185, h: 90, title: "Chunk Builder", lines: ["article · clause · point", "sliding · semantic"], iconKey: "files", stroke: C.blue }));
  body.push(nodeBox({ x: 1045, y: 315, w: 180, h: 90, title: "BGE-M3 Embed", lines: ["normalized vector(1024)", "pinned checkpoint"], iconKey: "huggingface", stroke: C.purple }));
  body.push(databaseNode({ x: 1270, y: 290, w: 170, h: 140, title: "SQLite + FTS5", iconKey: "sqlite", lines: ["staging + JSONL"] }));
  body.push(nodeBox({ x: 1490, y: 285, w: 145, h: 75, title: "PostgreSQL", lines: ["graphrag_chunk", "HNSW + GIN"], iconKey: "postgresql", stroke: C.teal }));
  body.push(nodeBox({ x: 1655, y: 285, w: 145, h: 75, title: "Neo4j", lines: ["nodes · chunks", "typed relations"], iconKey: "neo4j", stroke: C.purple }));
  body.push(noteBox({
    x: 1490, y: 390, w: 310, h: 75, title: "Projection sync",
    lines: ["Stable doc_id · node_id · chunk_id preserve cross-store identity."],
    color: C.green, iconKey: "check",
  }));

  body.push(edge([[300, 360], [345, 360]], { kind: "data" }));
  body.push(edge([[535, 360], [580, 360]], { kind: "data" }));
  body.push(edge([[770, 360], [815, 360]], { kind: "data" }));
  body.push(edge([[1000, 360], [1045, 360]], { kind: "data" }));
  body.push(edge([[1225, 360], [1270, 360]], { kind: "data" }));
  body.push(edge([[1440, 335], [1490, 335]], { kind: "data", label: "upsert", labelX: 1465, labelY: 318 }));
  body.push(edge([[1440, 380], [1465, 380], [1465, 380], [1655, 330]], { kind: "async", label: "MERGE", labelX: 1545, labelY: 370 }));

  body.push(groupBox({ x: 90, y: 565, w: 1740, h: 405, title: "Freshness-Driven Incremental Pipeline", color: C.orange }));
  body.push(stageLabel("2", 130, 615, "Verify, version and re-project changed laws", C.orange));

  body.push(nodeBox({ x: 120, y: 675, w: 165, h: 80, title: "Trigger", lines: ["query-time check", "or nightly Celery"], iconKey: "clock", stroke: C.orange }));
  body.push(nodeBox({ x: 325, y: 675, w: 170, h: 80, title: "Candidates", lines: ["retrieve legal sources"], iconKey: "search", stroke: C.orange }));
  body.push(diamond({ x: 535, y: 665, w: 165, h: 100, title: "verified_at", lines: ["within TTL?"], stroke: C.orange }));
  body.push(nodeBox({ x: 745, y: 675, w: 170, h: 80, title: "Official Search", lines: ["Tavily allowlist", "PDF · DOCX · HTML"], iconKey: "globe", stroke: C.orange }));
  body.push(nodeBox({ x: 955, y: 675, w: 170, h: 80, title: "Qwen Verdict", lines: ["in force · amended", "expired · replaced"], iconKey: "qwen", stroke: C.orange }));
  body.push(diamond({ x: 1165, y: 665, w: 170, h: 100, title: "Source", lines: ["changed?"], stroke: C.orange }));

  body.push(nodeBox({ x: 555, y: 835, w: 180, h: 75, title: "Reuse Metadata", lines: ["current status + evidence"], iconKey: "check", stroke: C.green }));
  body.push(nodeBox({ x: 955, y: 835, w: 180, h: 75, title: "Metadata Update", lines: ["status · URL · verified_at", "evidence JSON"], iconKey: "refresh", stroke: C.green }));
  body.push(nodeBox({ x: 1375, y: 665, w: 175, h: 80, title: "Download & Clean", lines: ["checksum · version", "normalized text"], iconKey: "download", stroke: C.orange }));
  body.push(nodeBox({ x: 1585, y: 665, w: 185, h: 80, title: "Article Split", lines: ["article / clause", "overlapping fallback"], iconKey: "files", stroke: C.orange }));
  body.push(nodeBox({ x: 1280, y: 835, w: 175, h: 75, title: "PostgreSQL Upsert", lines: ["document · chunks", "vectors + indexes"], iconKey: "postgresql", stroke: C.teal }));
  body.push(nodeBox({ x: 1490, y: 835, w: 150, h: 75, title: "Neo4j MERGE", lines: ["nodes · relations"], iconKey: "neo4j", stroke: C.purple }));
  body.push(nodeBox({ x: 1675, y: 835, w: 120, h: 75, title: "Re-run", lines: ["invalidate", "retrieve again"], iconKey: "refresh", stroke: C.purple }));

  body.push(edge([[285, 715], [325, 715]], { kind: "data" }));
  body.push(edge([[495, 715], [535, 715]], { kind: "data" }));
  body.push(edge([[700, 715], [745, 715]], { kind: "data", label: "No", labelX: 722, labelY: 697 }));
  body.push(edge([[915, 715], [955, 715]], { kind: "data" }));
  body.push(edge([[1125, 715], [1165, 715]], { kind: "data" }));
  body.push(edge([[615, 765], [615, 835]], { kind: "ink", label: "Yes", labelX: 640, labelY: 805 }));
  body.push(edge([[1250, 765], [1250, 872], [955, 872]], { kind: "ink", label: "No content change", labelX: 1130, labelY: 857 }));
  body.push(edge([[1335, 715], [1375, 705]], { kind: "data", label: "Changed", labelX: 1355, labelY: 690 }));
  body.push(edge([[1550, 705], [1585, 705]], { kind: "data" }));
  body.push(edge([[1675, 745], [1675, 800], [1368, 800], [1368, 835]], { kind: "data" }));
  body.push(edge([[1455, 872], [1490, 872]], { kind: "async" }));
  body.push(edge([[1640, 872], [1675, 872]], { kind: "async" }));

  return frame({
    title: "Legal data pipeline",
    subtitle: "VLegalAI · deterministic bootstrap plus freshness-driven incremental legal indexing",
    body: body.join("\n"),
  });
}

function renderDatabaseWriteFlow() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 355, h: 770, title: "Write Sources", color: C.blue }));
  body.push(groupBox({ x: 480, y: 195, w: 500, h: 770, title: "Application Transformations", color: C.magenta }));
  body.push(groupBox({ x: 1015, y: 195, w: 515, h: 770, title: "PostgreSQL Writes", color: C.teal }));
  body.push(groupBox({ x: 1565, y: 195, w: 265, h: 770, title: "Other Persistence", color: C.purple }));

  body.push(logoLabel("fastapi", 160, 225, 46, "FastAPI"));
  body.push(nodeBox({ x: 120, y: 335, w: 145, h: 75, title: "Google Callback", lines: ["identity"], iconKey: "google", stroke: C.blue }));
  body.push(nodeBox({ x: 285, y: 335, w: 130, h: 75, title: "Auth Chat", lines: ["/api/chat"], iconKey: "message", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 455, w: 145, h: 75, title: "Guest Chat", lines: ["temporary"], iconKey: "browser", stroke: C.blue }));
  body.push(nodeBox({ x: 285, y: 455, w: 130, h: 75, title: "Contracts", lines: ["draft / review"], iconKey: "files", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 575, w: 145, h: 75, title: "Articles", lines: ["research / save"], iconKey: "globe", stroke: C.blue }));
  body.push(nodeBox({ x: 285, y: 575, w: 130, h: 75, title: "Signature", lines: ["packet"], iconKey: "file", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 695, w: 145, h: 75, title: "Feedback", lines: ["page + message"], iconKey: "message", stroke: C.blue }));
  body.push(nodeBox({ x: 285, y: 695, w: 130, h: 75, title: "Indexer", lines: ["freshness / reindex"], iconKey: "refresh", stroke: C.blue }));
  body.push(nodeBox({ x: 160, y: 825, w: 215, h: 70, title: "Celery Beat + Worker", lines: ["scheduled legal refresh"], iconKey: "celery", stroke: C.blue }));

  body.push(stageLabel("1", 525, 245, "Validate, protect, transform", C.magenta));
  body.push(nodeBox({ x: 520, y: 320, w: 195, h: 80, title: "Identity Upsert", lines: ["resolve user + SSO"], iconKey: "key", stroke: C.magenta }));
  body.push(nodeBox({ x: 750, y: 320, w: 195, h: 80, title: "Chat Transaction", lines: ["USER commit → retrieval", "→ ASSISTANT commit"], iconKey: "workflow", stroke: C.magenta }));
  body.push(nodeBox({ x: 520, y: 445, w: 195, h: 85, title: "Encrypt + Hash", lines: ["AES-256-GCM", "SHA-256 integrity"], iconKey: "lock", stroke: C.green }));
  body.push(nodeBox({ x: 750, y: 445, w: 195, h: 85, title: "Rolling Summary", lines: ["Qwen summary", "BGE-M3 vector(1024)"], iconKey: "brain", stroke: C.magenta }));
  body.push(nodeBox({ x: 520, y: 575, w: 195, h: 80, title: "Atomic Rate Limit", lines: ["hash guest + IP", "window upsert"], iconKey: "clock", stroke: C.orange }));
  body.push(nodeBox({ x: 750, y: 575, w: 195, h: 80, title: "Product Write", lines: ["ownership + status", "editorial exception"], iconKey: "files", stroke: C.magenta }));
  body.push(nodeBox({ x: 520, y: 705, w: 195, h: 80, title: "Legal Versioning", lines: ["checksum · version", "split into chunks"], iconKey: "scale", stroke: C.teal }));
  body.push(nodeBox({ x: 750, y: 705, w: 195, h: 80, title: "Dual Projection", lines: ["BGE vector upsert", "graph MERGE"], iconKey: "merge", stroke: C.purple }));

  body.push(logoLabel("postgresql", 1080, 225, 46, "PostgreSQL 16"));
  body.push(nodeBox({ x: 1050, y: 330, w: 205, h: 75, title: "Identity", lines: ["app_user · sso_identity"], iconKey: "key", stroke: C.teal }));
  body.push(nodeBox({ x: 1285, y: 330, w: 205, h: 75, title: "Chat Transcript", lines: ["conversation · chat_message"], iconKey: "message", stroke: C.teal }));
  body.push(nodeBox({ x: 1050, y: 455, w: 205, h: 75, title: "Long-term Memory", lines: ["conversation_summary"], iconKey: "brain", stroke: C.teal }));
  body.push(nodeBox({ x: 1285, y: 455, w: 205, h: 75, title: "Answer Cache", lines: ["encrypted text · vector · TTL"], iconKey: "refresh", stroke: C.teal }));
  body.push(nodeBox({ x: 1050, y: 580, w: 205, h: 75, title: "Product Records", lines: ["artifact · article · signature", "feedback"], iconKey: "files", stroke: C.teal }));
  body.push(nodeBox({ x: 1285, y: 580, w: 205, h: 75, title: "Guest Counters", lines: ["guest_rate_limit"], iconKey: "clock", stroke: C.teal }));
  body.push(nodeBox({ x: 1050, y: 705, w: 205, h: 75, title: "Legal Registry", lines: ["legal_document · legal_chunk"], iconKey: "scale", stroke: C.teal }));
  body.push(nodeBox({ x: 1285, y: 705, w: 205, h: 75, title: "Retrieval Projection", lines: ["graphrag_chunk"], iconKey: "search", stroke: C.teal }));
  body.push(nodeBox({ x: 1165, y: 830, w: 215, h: 70, title: "Celery Coordination", lines: ["broker / result tables"], iconKey: "celery", stroke: C.teal }));

  body.push(databaseNode({ x: 1605, y: 290, w: 185, h: 155, title: "Neo4j", iconKey: "neo4j", lines: ["LegalNode · LegalChunk", "typed relationships"] }));
  body.push(nodeBox({ x: 1605, y: 520, w: 185, h: 95, title: "Browser sessionStorage", lines: ["guest transcript only", "no conversation rows"], iconKey: "browser", stroke: C.blue }));
  body.push(noteBox({
    x: 1605, y: 700, w: 185, h: 155, title: "Write guarantees",
    lines: ["Owned writes use transactions.", "Encrypted values carry integrity hashes.", "Graph uses idempotent MERGE."],
    color: C.green, iconKey: "shield",
  }));

  body.push(edge([[265, 372], [520, 360]], { kind: "data" }));
  body.push(edge([[415, 372], [750, 360]], { kind: "data" }));
  body.push(edge([[350, 410], [350, 487], [520, 487]], { kind: "data" }));
  body.push(edge([[265, 492], [520, 615]], { kind: "ink" }));
  body.push(edge([[415, 492], [750, 615]], { kind: "ink" }));
  body.push(edge([[265, 612], [750, 615]], { kind: "ink" }));
  body.push(edge([[415, 612], [750, 615]], { kind: "ink" }));
  body.push(edge([[265, 732], [520, 487]], { kind: "ink" }));
  body.push(edge([[415, 732], [520, 745]], { kind: "data" }));
  body.push(edge([[375, 860], [500, 860], [500, 745], [520, 745]], { kind: "async" }));
  body.push(edge([[715, 360], [1050, 367]], { kind: "data" }));
  body.push(edge([[945, 360], [1285, 367]], { kind: "data" }));
  body.push(edge([[847, 400], [847, 445]], { kind: "ink" }));
  body.push(edge([[945, 487], [1020, 487], [1020, 492], [1050, 492]], { kind: "data" }));
  body.push(edge([[715, 487], [1005, 487], [1005, 367], [1285, 367]], { kind: "data" }));
  body.push(edge([[715, 615], [1285, 615]], { kind: "data" }));
  body.push(edge([[945, 615], [1050, 617]], { kind: "data" }));
  body.push(edge([[715, 745], [1050, 742]], { kind: "data" }));
  body.push(edge([[945, 745], [1285, 742]], { kind: "data" }));
  body.push(edge([[945, 745], [1535, 745], [1535, 365], [1605, 365]], { kind: "async", label: "MERGE", labelX: 1545, labelY: 730 }));
  body.push(edge([[520, 615], [460, 615], [460, 567], [1605, 567]], { kind: "subtle", label: "guest history", labelX: 1500, labelY: 550 }));

  return frame({
    title: "Database write flow",
    subtitle: "VLegalAI · how identity, chat, product, legal-index and guest writes reach their persistence boundaries",
    body: body.join("\n"),
  });
}

function renderLegalQueryFlow() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 390, h: 770, title: "Request & Memory", color: C.blue }));
  body.push(groupBox({ x: 515, y: 195, w: 455, h: 770, title: "Cache & Retrieval", color: C.teal }));
  body.push(groupBox({ x: 1005, y: 195, w: 465, h: 770, title: "Verification & Generation", color: C.orange }));
  body.push(groupBox({ x: 1505, y: 195, w: 325, h: 770, title: "Persistence & Response", color: C.purple }));

  body.push(stageLabel("1", 130, 245, "Resolve context", C.blue));
  body.push(nodeBox({ x: 125, y: 310, w: 320, h: 75, title: "POST /api/chat", lines: ["question · optional conversation_id"], iconKey: "fastapi", stroke: C.blue }));
  body.push(diamond({ x: 190, y: 435, w: 190, h: 105, title: "Authenticated", lines: ["session?"], stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 600, w: 155, h: 90, title: "Guest Context", lines: ["rate limits", "browser history"], iconKey: "browser", stroke: C.blue }));
  body.push(nodeBox({ x: 300, y: 600, w: 155, h: 90, title: "Owned Context", lines: ["summary + last 12", "commit USER"], iconKey: "history", stroke: C.blue }));
  body.push(noteBox({
    x: 120, y: 775, w: 335, h: 115, title: "New-user example",
    lines: ['"How much is pay for working on a public holiday?"', "No personal conversation exists yet; retrieval starts from legal corpus."],
    color: C.blue, iconKey: "message",
  }));

  body.push(stageLabel("2", 555, 245, "Reuse safely or retrieve", C.teal));
  body.push(diamond({ x: 555, y: 315, w: 175, h: 105, title: "Public &", lines: ["context-free?"], stroke: C.teal }));
  body.push(nodeBox({ x: 765, y: 310, w: 175, h: 90, title: "Answer Cache", lines: ["exact query_hash", "semantic ≥ 0.96"], iconKey: "refresh", stroke: C.teal }));
  body.push(diamond({ x: 760, y: 455, w: 185, h: 105, title: "Current &", lines: ["fingerprint equal?"], stroke: C.teal }));
  body.push(nodeBox({ x: 550, y: 610, w: 175, h: 90, title: "Retrieval Service", lines: ["PostgreSQL dense + BM25", "RRF"], iconKey: "postgresql", stroke: C.teal }));
  body.push(nodeBox({ x: 765, y: 610, w: 175, h: 90, title: "Graph Expansion", lines: ["Neo4j ancestors", "typed relations"], iconKey: "neo4j", stroke: C.purple }));
  body.push(nodeBox({ x: 630, y: 800, w: 230, h: 75, title: "Ranked Legal Chunks", lines: ["merged by chunk_id · sources S1..Sn"], iconKey: "files", stroke: C.teal }));

  body.push(stageLabel("3", 1045, 245, "Verify before answering", C.orange));
  body.push(nodeBox({ x: 1040, y: 315, w: 190, h: 90, title: "Freshness Service", lines: ["verified_at TTL", "official-domain evidence"], iconKey: "shield", stroke: C.orange }));
  body.push(diamond({ x: 1260, y: 310, w: 180, h: 105, title: "Index", lines: ["updated?"], stroke: C.orange }));
  body.push(nodeBox({ x: 1040, y: 480, w: 190, h: 90, title: "Filter Status", lines: ["remove expired", "replaced · unknown"], iconKey: "filter", stroke: C.orange }));
  body.push(nodeBox({ x: 1260, y: 480, w: 180, h: 90, title: "Re-retrieve", lines: ["invalidate handle", "rank again"], iconKey: "refresh", stroke: C.orange }));
  body.push(nodeBox({ x: 1040, y: 645, w: 400, h: 95, title: "Grounded Prompt", lines: ["summary · recent history · verification · sources", "current question · optional cache draft"], iconKey: "file", stroke: C.orange }));
  body.push(nodeBox({ x: 1100, y: 815, w: 280, h: 75, title: "Local Qwen3-14B", lines: ["answer with citations [S1], [S2], ..."], iconKey: "qwen", stroke: C.orange }));

  body.push(stageLabel("4", 1545, 245, "Persist and return", C.purple));
  body.push(diamond({ x: 1575, y: 320, w: 185, h: 105, title: "Authenticated", lines: ["result?"], stroke: C.purple }));
  body.push(nodeBox({ x: 1540, y: 500, w: 255, h: 90, title: "Durable Chat Write", lines: ["encrypted ASSISTANT message", "sources + verification"], iconKey: "postgresql", stroke: C.purple }));
  body.push(nodeBox({ x: 1540, y: 640, w: 255, h: 90, title: "Rolling Memory", lines: ["encrypted summary", "BGE-M3 vector"], iconKey: "brain", stroke: C.purple }));
  body.push(nodeBox({ x: 1540, y: 780, w: 255, h: 90, title: "ChatResponse", lines: ["temporary for guest", "durable for authenticated"], iconKey: "check", stroke: C.purple }));
  body.push(noteBox({
    x: 1518, y: 905, w: 300, h: 45, title: "Eligible current answers may refresh the semantic cache.",
    lines: [], color: C.purple, iconKey: "refresh",
  }));

  body.push(edge([[285, 385], [285, 435]], { kind: "ink" }));
  body.push(edge([[240, 540], [198, 600]], { kind: "ink", label: "No", labelX: 205, labelY: 565 }));
  body.push(edge([[330, 540], [378, 600]], { kind: "data", label: "Yes", labelX: 360, labelY: 565 }));
  body.push(edge([[275, 645], [490, 645], [490, 367], [555, 367]], { kind: "data" }));
  body.push(edge([[455, 645], [490, 645], [490, 367], [555, 367]], { kind: "data" }));
  body.push(edge([[730, 367], [765, 355]], { kind: "data", label: "Yes", labelX: 748, labelY: 340 }));
  body.push(edge([[642, 420], [642, 610]], { kind: "ink", label: "No", labelX: 660, labelY: 515 }));
  body.push(edge([[852, 400], [852, 455]], { kind: "ink" }));
  body.push(edge([[760, 507], [735, 507], [735, 655], [725, 655]], { kind: "ink", label: "No / draft", labelX: 740, labelY: 590 }));
  body.push(edge([[945, 507], [985, 507], [985, 830], [1380, 830]], { kind: "data", label: "Exact current hit", labelX: 980, labelY: 490 }));
  body.push(edge([[725, 655], [765, 655]], { kind: "data" }));
  body.push(edge([[850, 700], [850, 800]], { kind: "data" }));
  body.push(edge([[860, 837], [980, 837], [980, 360], [1040, 360]], { kind: "data" }));
  body.push(edge([[1230, 360], [1260, 362]], { kind: "data" }));
  body.push(edge([[1350, 415], [1350, 480]], { kind: "ink", label: "Yes", labelX: 1370, labelY: 450 }));
  body.push(edge([[1260, 532], [1230, 532]], { kind: "data" }));
  body.push(edge([[1135, 405], [1135, 480]], { kind: "data", label: "No", labelX: 1155, labelY: 450 }));
  body.push(edge([[1135, 570], [1135, 645]], { kind: "data" }));
  body.push(edge([[1240, 740], [1240, 815]], { kind: "data" }));
  body.push(edge([[1380, 852], [1490, 852], [1490, 372], [1575, 372]], { kind: "data" }));
  body.push(edge([[1668, 425], [1668, 500]], { kind: "data", label: "Yes", labelX: 1690, labelY: 465 }));
  body.push(edge([[1575, 372], [1515, 372], [1515, 825], [1540, 825]], { kind: "ink", label: "No", labelX: 1525, labelY: 760 }));
  body.push(edge([[1668, 590], [1668, 640]], { kind: "data" }));
  body.push(edge([[1668, 730], [1668, 780]], { kind: "data" }));

  return frame({
    title: "Legal query flow",
    subtitle: "VLegalAI · request routing, semantic cache safety, HybridRAG, legal freshness and durable response handling",
    body: body.join("\n"),
  });
}

function renderChatHistoryFlow() {
  const body = [];

  body.push(icon("users", 95, 205, 68));
  body.push(lineText(129, 292, "User message", { size: 16, weight: 700, anchor: "middle" }));
  body.push(diamond({ x: 250, y: 200, w: 210, h: 110, title: "Google-authenticated", lines: ["session?"], stroke: C.orange }));
  body.push(noteBox({
    x: 540, y: 210, w: 505, h: 80, title: "Two different memory contracts",
    lines: ["Guest = browser-only temporary history. Authenticated = durable encrypted transcript + rolling semantic summary."],
    color: C.orange, iconKey: "history",
  }));

  body.push(groupBox({ x: 90, y: 380, w: 1740, h: 240, title: "Guest Memory — Browser Only", color: C.blue }));
  body.push(stageLabel("1", 130, 430, "Temporary turn", C.blue));
  body.push(nodeBox({ x: 120, y: 485, w: 185, h: 80, title: "Read History", lines: ["completed messages", "from sessionStorage"], iconKey: "browser", stroke: C.blue }));
  body.push(nodeBox({ x: 345, y: 485, w: 185, h: 80, title: "Compact", lines: ["remove pending / errors", "handle quota failure"], iconKey: "filter", stroke: C.blue }));
  body.push(nodeBox({ x: 570, y: 485, w: 185, h: 80, title: "Send Request", lines: ["message + history[]", "conversation_id = null"], iconKey: "message", stroke: C.blue }));
  body.push(nodeBox({ x: 795, y: 485, w: 185, h: 80, title: "Rate Counters", lines: ["PostgreSQL only", "hashed guest + IP"], iconKey: "postgresql", stroke: C.teal }));
  body.push(nodeBox({ x: 1020, y: 485, w: 185, h: 80, title: "Legal Answer", lines: ["retrieve · verify", "generate"], iconKey: "brain", stroke: C.blue }));
  body.push(nodeBox({ x: 1245, y: 485, w: 185, h: 80, title: "Temporary Response", lines: ["not server-persisted"], iconKey: "download", stroke: C.blue }));
  body.push(nodeBox({ x: 1470, y: 485, w: 320, h: 80, title: "Append to sessionStorage", lines: ["No conversation, message or summary rows are written."], iconKey: "browser", stroke: C.blue }));

  body.push(edge([[305, 525], [345, 525]], { kind: "data" }));
  body.push(edge([[530, 525], [570, 525]], { kind: "data" }));
  body.push(edge([[755, 525], [795, 525]], { kind: "data" }));
  body.push(edge([[980, 525], [1020, 525]], { kind: "data" }));
  body.push(edge([[1205, 525], [1245, 525]], { kind: "data" }));
  body.push(edge([[1430, 525], [1470, 525]], { kind: "data" }));

  body.push(groupBox({ x: 90, y: 690, w: 1740, h: 310, title: "Authenticated Memory — PostgreSQL", color: C.magenta }));
  body.push(stageLabel("2", 130, 740, "Durable turn + rolling long-term memory", C.magenta));
  body.push(nodeBox({ x: 120, y: 795, w: 175, h: 75, title: "Conversation", lines: ["resolve or create", "enforce ownership"], iconKey: "key", stroke: C.magenta }));
  body.push(nodeBox({ x: 330, y: 795, w: 190, h: 75, title: "Load Context", lines: ["decrypt summary", "+ last 12 messages"], iconKey: "history", stroke: C.magenta }));
  body.push(nodeBox({ x: 555, y: 795, w: 190, h: 75, title: "Commit USER", lines: ["encrypt content", "store integrity hash"], iconKey: "lock", stroke: C.magenta }));
  body.push(nodeBox({ x: 780, y: 795, w: 185, h: 75, title: "Answer", lines: ["HybridRAG + freshness", "Qwen generation"], iconKey: "brain", stroke: C.magenta }));
  body.push(nodeBox({ x: 1000, y: 795, w: 190, h: 75, title: "Commit ASSISTANT", lines: ["encrypt content", "sources + verification"], iconKey: "lock", stroke: C.magenta }));
  body.push(nodeBox({ x: 1225, y: 795, w: 175, h: 75, title: "Advisory Lock", lines: ["one summary refresh", "per conversation"], iconKey: "shield", stroke: C.magenta }));
  body.push(nodeBox({ x: 1435, y: 795, w: 175, h: 75, title: "Qwen Summary", lines: ["unsummarized turns", "batch of 12"], iconKey: "qwen", stroke: C.magenta }));
  body.push(nodeBox({ x: 1645, y: 795, w: 155, h: 75, title: "BGE-M3", lines: ["vector(1024)"], iconKey: "huggingface", stroke: C.magenta }));

  body.push(nodeBox({ x: 1215, y: 915, w: 585, h: 55, title: "Encrypt and UPSERT one conversation_summary row", lines: ["Full transcript remains durable even if summary refresh fails."], iconKey: "postgresql", stroke: C.teal }));

  body.push(edge([[295, 832], [330, 832]], { kind: "data" }));
  body.push(edge([[520, 832], [555, 832]], { kind: "data" }));
  body.push(edge([[745, 832], [780, 832]], { kind: "data" }));
  body.push(edge([[965, 832], [1000, 832]], { kind: "data" }));
  body.push(edge([[1190, 832], [1225, 832]], { kind: "data" }));
  body.push(edge([[1400, 832], [1435, 832]], { kind: "data" }));
  body.push(edge([[1610, 832], [1645, 832]], { kind: "data" }));
  body.push(edge([[1722, 870], [1722, 915]], { kind: "data" }));
  body.push(edge([[1215, 942], [540, 942], [540, 760], [425, 760], [425, 795]], { kind: "async", label: "next-turn long-term context", labelX: 820, labelY: 927 }));

  body.push(edge([[355, 310], [355, 355], [205, 355], [205, 485]], { kind: "ink", label: "No", labelX: 330, labelY: 345 }));
  body.push(edge([[460, 255], [1080, 255], [1080, 665], [205, 665], [205, 795]], { kind: "data", label: "Yes", labelX: 1055, labelY: 240 }));

  return frame({
    title: "Chat history flow",
    subtitle: "VLegalAI · explicit separation between temporary guest history and durable encrypted conversational memory",
    body: body.join("\n"),
  });
}

function renderGraphRagStorageFlow() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 415, h: 770, title: "Source & Parsing", color: C.blue }));
  body.push(groupBox({ x: 540, y: 195, w: 340, h: 770, title: "Bootstrap Staging", color: C.orange }));
  body.push(groupBox({ x: 915, y: 195, w: 430, h: 770, title: "PostgreSQL / pgvector", color: C.teal }));
  body.push(groupBox({ x: 1380, y: 195, w: 450, h: 770, title: "Neo4j Graph Projection", color: C.purple }));

  body.push(stageLabel("1", 130, 245, "Parse once", C.blue));
  body.push(nodeBox({ x: 120, y: 315, w: 355, h: 85, title: "Legal Source Text", lines: ["bootstrap DOCX or verified official PDF / DOCX / HTML"], iconKey: "file", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 455, w: 355, h: 85, title: "Structure + Semantic Parser", lines: ["legal hierarchy · entities · terminology · temporal · risk"], iconKey: "workflow", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 600, w: 160, h: 90, title: "Document", lines: ["doc_id · code", "title · version"], iconKey: "file", stroke: C.blue }));
  body.push(nodeBox({ x: 315, y: 600, w: 160, h: 90, title: "Legal Nodes", lines: ["node_id · type", "path · attributes"], iconKey: "network", stroke: C.purple }));
  body.push(nodeBox({ x: 120, y: 755, w: 160, h: 90, title: "Typed Edges", lines: ["CITES · GUIDES", "AMENDS · REPLACES"], iconKey: "merge", stroke: C.purple }));
  body.push(nodeBox({ x: 315, y: 755, w: 160, h: 90, title: "Retrieval Chunks", lines: ["chunk_id · node_id", "citation · text"], iconKey: "files", stroke: C.blue }));
  body.push(nodeBox({ x: 240, y: 885, w: 175, h: 55, title: "BGE-M3 vector(1024)", iconKey: "huggingface", stroke: C.purple }));

  body.push(stageLabel("2", 580, 245, "Materialize", C.orange));
  body.push(databaseNode({ x: 585, y: 320, w: 250, h: 185, title: "SQLite + FTS5", iconKey: "sqlite", lines: ["docs · nodes · edges · chunks", "local bootstrap artifact"] }));
  body.push(nodeBox({ x: 585, y: 575, w: 250, h: 105, title: "JSONL Exports", lines: ["documents.jsonl · nodes.jsonl", "edges.jsonl · chunks.jsonl"], iconKey: "file", stroke: C.orange }));
  body.push(noteBox({
    x: 585, y: 760, w: 250, h: 135, title: "Not production authority",
    lines: ["Used for reproducible builds,", "bulk sync and local fallback.", "Safe to regenerate from sources."],
    color: C.orange, iconKey: "refresh",
  }));

  body.push(stageLabel("3", 955, 245, "Store and index", C.teal));
  body.push(logoLabel("postgresql", 1010, 285, 44, "PostgreSQL"));
  body.push(nodeBox({ x: 950, y: 390, w: 360, h: 90, title: "LEGAL_DOCUMENT", lines: ["status · checksum · verified_at · version"], iconKey: "scale", stroke: C.teal }));
  body.push(nodeBox({ x: 950, y: 535, w: 360, h: 90, title: "LEGAL_CHUNK", lines: ["versioned application chunks · document_id FK"], iconKey: "files", stroke: C.teal }));
  body.push(nodeBox({ x: 950, y: 680, w: 360, h: 115, title: "GRAPHRAG_CHUNK", lines: ["retrieval payload · vector(1024)", "HNSW cosine + GIN lexical index"], iconKey: "search", stroke: C.teal }));
  body.push(noteBox({
    x: 950, y: 850, w: 360, h: 75, title: "Identity bridge",
    lines: ["external_chunk_id = chunk_id · plus node_id and doc_id"],
    color: C.teal, iconKey: "link",
  }));

  body.push(stageLabel("4", 1420, 245, "Project relationships", C.purple));
  body.push(logoLabel("neo4j", 1480, 285, 44, "Neo4j"));
  body.push(nodeBox({ x: 1420, y: 390, w: 170, h: 85, title: ":LegalNode", lines: ["unique node_id"], iconKey: "network", stroke: C.purple }));
  body.push(nodeBox({ x: 1620, y: 390, w: 170, h: 85, title: ":LegalChunk", lines: ["unique chunk_id"], iconKey: "file", stroke: C.purple }));
  body.push(nodeBox({ x: 1420, y: 540, w: 370, h: 115, title: "Structural Relationships", lines: ["(:LegalChunk)-[:CHUNK_OF]->(:LegalNode)", "BELONGS_TO depth hierarchy"], iconKey: "merge", stroke: C.purple }));
  body.push(nodeBox({ x: 1420, y: 710, w: 370, h: 125, title: "Dynamic Typed Relationships", lines: ["CITES · GUIDES · AMENDS · REPLACES", "semantic · process · risk · precedent", "edge_id + evidence"], iconKey: "network", stroke: C.purple }));
  body.push(noteBox({
    x: 1420, y: 875, w: 370, h: 50, title: "Idempotent MERGE keeps the graph projection rebuildable.",
    lines: [], color: C.purple, iconKey: "check",
  }));

  body.push(edge([[297, 400], [297, 455]], { kind: "data" }));
  body.push(edge([[297, 540], [200, 600]], { kind: "data" }));
  body.push(edge([[297, 540], [395, 600]], { kind: "data" }));
  body.push(edge([[297, 540], [200, 755]], { kind: "data" }));
  body.push(edge([[297, 540], [395, 755]], { kind: "data" }));
  body.push(edge([[395, 845], [395, 885]], { kind: "data" }));
  body.push(edge([[475, 645], [520, 645], [520, 410], [585, 410]], { kind: "subtle" }));
  body.push(edge([[475, 800], [520, 800], [520, 410], [585, 410]], { kind: "subtle" }));
  body.push(edge([[415, 912], [520, 912], [520, 450], [585, 450]], { kind: "subtle" }));
  body.push(edge([[710, 505], [710, 575]], { kind: "subtle" }));
  body.push(edge([[835, 410], [900, 410], [900, 435], [950, 435]], { kind: "data", label: "bulk sync", labelX: 900, labelY: 395 }));
  body.push(edge([[835, 450], [900, 450], [900, 737], [950, 737]], { kind: "data" }));
  body.push(edge([[1130, 480], [1130, 535]], { kind: "data" }));
  body.push(edge([[1310, 737], [1360, 737], [1360, 432], [1420, 432]], { kind: "async", label: "node_id", labelX: 1360, labelY: 720 }));
  body.push(edge([[1310, 737], [1360, 737], [1360, 432], [1620, 432]], { kind: "async", label: "chunk_id", labelX: 1500, labelY: 417 }));
  body.push(edge([[1590, 432], [1620, 432]], { kind: "async", label: "CHUNK_OF", labelX: 1605, labelY: 412 }));
  body.push(edge([[1505, 475], [1505, 540]], { kind: "async" }));
  body.push(edge([[200, 845], [900, 845], [900, 770], [1420, 770]], { kind: "async", label: "typed edges", labelX: 900, labelY: 830 }));

  return frame({
    title: "GraphRAG storage flow",
    subtitle: "VLegalAI · one parsed legal corpus, reproducible staging, PostgreSQL retrieval projection and Neo4j relationship projection",
    body: body.join("\n"),
  });
}

function renderHybridRagQueryFlow() {
  const body = [];

  body.push(groupBox({ x: 90, y: 195, w: 300, h: 770, title: "Query Preparation", color: C.blue }));
  body.push(groupBox({ x: 425, y: 195, w: 510, h: 770, title: "Stage 1 — PostgreSQL Retrieval", color: C.teal }));
  body.push(groupBox({ x: 970, y: 195, w: 410, h: 770, title: "Stage 2 — Neo4j Expansion", color: C.purple }));
  body.push(groupBox({ x: 1415, y: 195, w: 415, h: 770, title: "Fusion, Verification & Context", color: C.orange }));

  body.push(stageLabel("0", 130, 245, "Understand query", C.blue));
  body.push(icon("users", 185, 305, 74));
  body.push(nodeBox({ x: 120, y: 425, w: 240, h: 85, title: "Legal Question", lines: ['"Public-holiday work pay?"'], iconKey: "message", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 565, w: 240, h: 90, title: "Normalize + Terms", lines: ["whitespace normalization", "Vietnamese lexical terms"], iconKey: "filter", stroke: C.blue }));
  body.push(nodeBox({ x: 120, y: 715, w: 240, h: 90, title: "BGE-M3 Query Vector", lines: ["normalized vector(1024)"], iconKey: "huggingface", stroke: C.purple }));
  body.push(noteBox({
    x: 120, y: 855, w: 240, h: 70, title: "One query, two signals",
    lines: ["Lexical terms + dense semantics."],
    color: C.blue, iconKey: "merge",
  }));

  body.push(stageLabel("1", 465, 245, "Generate candidates", C.teal));
  body.push(logoLabel("postgresql", 520, 300, 46, "PostgreSQL + pgvector"));
  body.push(nodeBox({ x: 465, y: 410, w: 190, h: 105, title: "Dense Rank", lines: ["HNSW cosine distance", "limit max(64, top_k × 8)", "weight 0.55"], iconKey: "search", stroke: C.teal }));
  body.push(nodeBox({ x: 700, y: 410, w: 195, h: 105, title: "Lexical Rank", lines: ["GIN simple tsquery", "Okapi BM25 k1=1.5 · b=0.75", "weight 0.45"], iconKey: "file", stroke: C.teal }));
  body.push(nodeBox({ x: 560, y: 590, w: 245, h: 90, title: "Weighted RRF", lines: ["reciprocal rank fusion · k=60"], iconKey: "merge", stroke: C.teal }));
  body.push(nodeBox({ x: 500, y: 750, w: 360, h: 100, title: "score_chunk_payload", lines: ["rank decay · term coverage · negation / article boosts", "seed score keyed by node_id"], iconKey: "workflow", stroke: C.teal }));
  body.push(nodeBox({ x: 560, y: 890, w: 245, h: 50, title: "PostgreSQL seed chunks", iconKey: "postgresql", stroke: C.teal }));

  body.push(stageLabel("2", 1010, 245, "Expand legal context", C.purple));
  body.push(logoLabel("neo4j", 1060, 300, 46, "Neo4j"));
  body.push(nodeBox({ x: 1010, y: 410, w: 155, h: 100, title: "Ancestors", lines: ["BELONGS_TO", "depth 1..4", "decayed weights"], iconKey: "network", stroke: C.purple }));
  body.push(nodeBox({ x: 1190, y: 410, w: 155, h: 100, title: "Outgoing", lines: ["CITES · GUIDES", "AMENDS · REPLACES", "domain relations"], iconKey: "merge", stroke: C.purple }));
  body.push(nodeBox({ x: 1010, y: 570, w: 155, h: 100, title: "Incoming", lines: ["reverse GUIDES", "AMENDS · REPLACES"], iconKey: "refresh", stroke: C.purple }));
  body.push(nodeBox({ x: 1190, y: 570, w: 155, h: 100, title: "Fetch Chunks", lines: ["through CHUNK_OF", "prefer article / clause"], iconKey: "files", stroke: C.purple }));
  body.push(nodeBox({ x: 1050, y: 755, w: 255, h: 90, title: "Expanded Candidates", lines: ["scores preserve relation reasons"], iconKey: "network", stroke: C.purple }));
  body.push(noteBox({
    x: 1050, y: 890, w: 255, h: 50, title: "Graph augments; it does not replace ranked seeds.",
    lines: [], color: C.purple, iconKey: "check",
  }));

  body.push(stageLabel("3", 1455, 245, "Ground the answer", C.orange));
  body.push(nodeBox({ x: 1450, y: 330, w: 345, h: 85, title: "Merge by chunk_id", lines: ["keep max score · article boost 0.08 · preserve reasons"], iconKey: "merge", stroke: C.orange }));
  body.push(nodeBox({ x: 1450, y: 465, w: 345, h: 85, title: "Top-k + Source IDs", lines: ["sort descending · assign S1..Sn"], iconKey: "filter", stroke: C.orange }));
  body.push(nodeBox({ x: 1450, y: 600, w: 345, h: 85, title: "Serialize Evidence", lines: ["citation · text · doc_id · node_id · URL · score"], iconKey: "file", stroke: C.orange }));
  body.push(nodeBox({ x: 1450, y: 735, w: 345, h: 85, title: "Mandatory Freshness", lines: ["filter expired · replaced · unknown laws"], iconKey: "shield", stroke: C.orange }));
  body.push(nodeBox({ x: 1450, y: 870, w: 345, h: 60, title: "Grounded Qwen3 Context", iconKey: "qwen", stroke: C.orange }));

  body.push(edge([[240, 510], [240, 565]], { kind: "data" }));
  body.push(edge([[240, 655], [240, 715]], { kind: "data" }));
  body.push(edge([[360, 610], [410, 610], [410, 462], [700, 462]], { kind: "data", label: "terms", labelX: 410, labelY: 595 }));
  body.push(edge([[360, 760], [410, 760], [410, 462], [465, 462]], { kind: "data", label: "vector", labelX: 410, labelY: 745 }));
  body.push(edge([[560, 515], [560, 555], [640, 555], [640, 590]], { kind: "data" }));
  body.push(edge([[797, 515], [797, 555], [725, 555], [725, 590]], { kind: "data" }));
  body.push(edge([[682, 680], [682, 750]], { kind: "data" }));
  body.push(edge([[682, 850], [682, 890]], { kind: "data" }));
  body.push(edge([[805, 915], [950, 915], [950, 460], [1010, 460]], { kind: "async", label: "seed node_id", labelX: 950, labelY: 895 }));
  body.push(edge([[950, 915], [950, 620], [1010, 620]], { kind: "async" }));
  body.push(edge([[950, 915], [1170, 915], [1170, 460], [1190, 460]], { kind: "async" }));
  body.push(edge([[1165, 460], [1190, 620]], { kind: "async" }));
  body.push(edge([[1165, 620], [1190, 620]], { kind: "async" }));
  body.push(edge([[1268, 510], [1268, 570]], { kind: "async" }));
  body.push(edge([[1268, 670], [1268, 755]], { kind: "async" }));
  body.push(edge([[1305, 800], [1400, 800], [1400, 372], [1450, 372]], { kind: "data" }));
  body.push(edge([[805, 915], [1390, 915], [1390, 372], [1450, 372]], { kind: "subtle", label: "preserve seeds", labelX: 1390, labelY: 900 }));
  body.push(edge([[1622, 415], [1622, 465]], { kind: "data" }));
  body.push(edge([[1622, 550], [1622, 600]], { kind: "data" }));
  body.push(edge([[1622, 685], [1622, 735]], { kind: "data" }));
  body.push(edge([[1622, 820], [1622, 870]], { kind: "data" }));

  return frame({
    title: "HybridRAG query flow",
    subtitle: "VLegalAI · PostgreSQL dense + BM25 fusion, Neo4j graph expansion and mandatory legal freshness verification",
    body: body.join("\n"),
  });
}

const diagrams = [
  ["01_system_design", renderSystemDesign],
  ["02_postgresql_erd", renderPostgresqlErd],
  ["03_database_design", renderDatabaseDesign],
  ["04_application_workflow", renderApplicationWorkflow],
  ["05_legal_data_pipeline", renderLegalDataPipeline],
  ["06_database_write_flow", renderDatabaseWriteFlow],
  ["07_legal_query_flow", renderLegalQueryFlow],
  ["08_chat_history_flow", renderChatHistoryFlow],
  ["09_graphrag_storage_flow", renderGraphRagStorageFlow],
  ["10_hybrid_rag_query_flow", renderHybridRagQueryFlow],
];

fs.mkdirSync(svgDir, { recursive: true });
fs.mkdirSync(pngDir, { recursive: true });

const failures = [];
for (const [basename, renderer] of diagrams) {
  try {
    const svg = renderer();
    const svgPath = path.join(svgDir, `${basename}.svg`);
    const pngPath = path.join(pngDir, `${basename}.png`);
    fs.writeFileSync(svgPath, svg);
    const rasterizer = new Resvg(svg, {
      fitTo: { mode: "zoom", value: 2 },
      font: {
        loadSystemFonts: true,
        defaultFontFamily: "DejaVu Sans",
      },
    });
    fs.writeFileSync(pngPath, rasterizer.render().asPng());
    process.stdout.write(`Rendered ${basename}\n`);
  } catch (error) {
    failures.push(`${basename}: ${error instanceof Error ? error.stack : String(error)}`);
  }
}

if (failures.length) {
  process.stderr.write(`${failures.join("\n\n")}\n`);
  process.exit(1);
}
