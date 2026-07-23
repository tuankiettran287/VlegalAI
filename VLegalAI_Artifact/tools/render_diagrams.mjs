import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { renderMermaidSVG } from "beautiful-mermaid";
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
const sourceDir = path.join(kitDir, "mermaid");
const svgDir = path.join(kitDir, "images", "svg");
const pngDir = path.join(kitDir, "images", "png");

const diagramMeta = {
  "01_system_design.mmd": [
    "System Design",
    "Production topology, local AI services, data stores, and scheduled jobs",
  ],
  "02_postgresql_erd.mmd": [
    "PostgreSQL ERD",
    "Application schema after Alembic migration 20260723_0006",
  ],
  "03_database_design.mmd": [
    "Physical Database Design",
    "System of record, retrieval projections, graph projection, and browser state",
  ],
  "04_application_workflow.mmd": [
    "Application Workflow",
    "Guest and authenticated journeys across legal and document features",
  ],
  "05_legal_data_pipeline.mmd": [
    "Legal Data Pipeline",
    "Bootstrap indexing and freshness-driven incremental updates",
  ],
  "06_database_write_flow.mmd": [
    "Database Write Flow",
    "Write ownership, encryption boundaries, and cross-store synchronization",
  ],
  "07_legal_query_flow.mmd": [
    "Legal Query Flow",
    "Cache, retrieval, mandatory freshness verification, generation, and persistence",
  ],
  "08_chat_history_flow.mmd": [
    "Chat History Flow",
    "Temporary guest memory and encrypted long-term authenticated memory",
  ],
  "09_graphrag_storage_flow.mmd": [
    "GraphRAG Storage Flow",
    "Shared identifiers across staging, PostgreSQL/pgvector, and Neo4j",
  ],
  "10_hybrid_rag_query_flow.mmd": [
    "HybridRAG Query Flow",
    "BGE-M3 dense retrieval, BM25, weighted RRF, and Neo4j expansion",
  ],
};

const colors = {
  bg: "#F8FAFC",
  fg: "#0F172A",
  line: "#64748B",
  accent: "#0F766E",
  muted: "#475569",
  surface: "#FFFFFF",
  border: "#CBD5E1",
  faint: "#94A3B8",
  groupHeader: "#E2E8F0",
};

const icons = {
  fastapi: { set: "logos", name: "fastapi-icon", color: "#009688" },
  postgresql: { set: "logos", name: "postgresql", color: "#4169E1" },
  neo4j: { set: "logos", name: "neo4j", color: "#018BFF" },
  react: { set: "logos", name: "react", color: "#149ECA" },
  typescript: { set: "logos", name: "typescript-icon", color: "#3178C6" },
  docker: { set: "logos", name: "docker-icon", color: "#2496ED" },
  google: { set: "logos", name: "google-icon", color: "#4285F4" },
  huggingface: {
    set: "simple",
    name: "huggingface",
    color: "#FF9D00",
  },
  sqlite: { set: "simple", name: "sqlite", color: "#0F80CC" },
  redis: { set: "logos", name: "redis", color: "#DC382D" },
  python: { set: "simple", name: "python", color: "#3776AB" },
  celery: { set: "simple", name: "celery", color: "#37814A" },
  caddy: { set: "simple", name: "caddy", color: "#1F88C0" },
  qwen: { set: "simple", name: "alibabacloud", color: "#FF6A00" },
  user: { set: "lucide", name: "user", color: "#475569" },
  scale: { set: "lucide", name: "scale", color: "#7C3AED" },
  bot: { set: "lucide", name: "bot", color: "#2563EB" },
  brain: { set: "lucide", name: "brain-circuit", color: "#2563EB" },
  search: { set: "lucide", name: "search", color: "#0F766E" },
  database: { set: "lucide", name: "database", color: "#475569" },
  document: { set: "lucide", name: "file-text", color: "#0891B2" },
  hierarchy: { set: "lucide", name: "folder-tree", color: "#7C3AED" },
  workflow: { set: "lucide", name: "workflow", color: "#EA580C" },
  clock: { set: "lucide", name: "clock", color: "#D97706" },
  refresh: { set: "lucide", name: "refresh-cw", color: "#0F766E" },
  shield: { set: "lucide", name: "shield-check", color: "#16A34A" },
  lock: { set: "lucide", name: "lock-keyhole", color: "#16A34A" },
  message: { set: "lucide", name: "message-square", color: "#2563EB" },
  history: { set: "lucide", name: "history", color: "#2563EB" },
  network: { set: "lucide", name: "network", color: "#7C3AED" },
  link: { set: "lucide", name: "link", color: "#7C3AED" },
  cloud: { set: "lucide", name: "cloud", color: "#0284C7" },
  download: { set: "lucide", name: "download", color: "#0284C7" },
  server: { set: "lucide", name: "server", color: "#475569" },
  layers: { set: "lucide", name: "layers", color: "#7C3AED" },
  key: { set: "lucide", name: "key-round", color: "#D97706" },
  filter: { set: "lucide", name: "filter", color: "#0F766E" },
  merge: { set: "lucide", name: "git-merge", color: "#7C3AED" },
  route: { set: "lucide", name: "route", color: "#475569" },
  sparkles: { set: "lucide", name: "sparkles", color: "#D97706" },
  json: { set: "lucide", name: "file-json", color: "#475569" },
  boxes: { set: "lucide", name: "boxes", color: "#475569" },
};

const neo4jNodeIds = new Set([
  "NEO",
  "GNODE",
  "GCHUNK",
  "GRELS",
  "LEGALNODE",
  "LEGALCHUNK",
  "RELS",
  "GRAPHWRITE",
  "GRAPHMERGE",
  "ANCESTOR",
  "OUTGOING",
  "INCOMING",
  "FETCH",
]);

const celeryNodeIds = new Set(["WORKER", "BEAT", "SCHED", "CELERYDB"]);
const postgresqlNodeIds = new Set([
  "PG",
  "PGV",
  "APPDB",
  "AUTHDB",
  "CHATDB",
  "MEMORYDB",
  "CACHEDB",
  "PRODUCTDB",
  "LEGALDB",
  "VECTORDB",
  "LIMITDB",
  "REGISTRY",
  "VERSIONED",
  "PROJECTION",
  "DENSE",
  "LEX",
  "RRF",
  "SEEDS",
  "IDENTITY",
  "CHAT",
  "LEGAL",
  "RETRIEVAL",
  "PRODUCTS",
  "RUNTIME",
  "CACHE",
]);

function iconData(spec) {
  const collection = iconSets[spec.set];
  const icon = collection.icons[spec.name];
  if (!icon) {
    throw new Error(`Missing icon ${spec.set}:${spec.name}`);
  }
  return {
    body: icon.body.replaceAll("currentColor", spec.color),
    width: icon.width ?? collection.width ?? 24,
    height: icon.height ?? collection.height ?? 24,
  };
}

function chooseNodeIcon(filename, nodeId, rawLabel) {
  const label = rawLabel
    .replaceAll("&amp;", "&")
    .replaceAll("&gt;", ">")
    .replaceAll("&lt;", "<")
    .toLowerCase();
  const id = nodeId.toUpperCase();

  if (filename === "02_postgresql_erd.mmd") return icons.postgresql;
  if (neo4jNodeIds.has(id)) return icons.neo4j;
  if (celeryNodeIds.has(id)) return icons.celery;
  if (postgresqlNodeIds.has(id)) return icons.postgresql;
  if (id === "VOLUMES") return icons.docker;
  if (id === "BROWSER" || id === "FRONTEND") return icons.react;
  if (id === "CADDY") return icons.caddy;
  if (id === "GOOGLE" || id === "OIDC") return icons.google;
  if (id === "HF") return icons.huggingface;
  if (id === "QWEN" || id === "VERDICT" || id === "ROLLING") {
    return icons.qwen;
  }
  if (id === "STAGING" || id === "STAGE" || id === "SQLITE") {
    return icons.sqlite;
  }
  if (id === "MIGRATE") return icons.python;
  if (id === "JSONL") return icons.json;
  if (/\bneo4j\b/.test(label)) return icons.neo4j;
  if (/\bcelery\b/.test(label)) return icons.celery;
  if (/\bfastapi\b|\/api\/|api endpoint|endpoints/.test(label)) {
    return icons.fastapi;
  }
  if (/\breact\b|\btypescript\b|\bspa\b|frontend container/.test(label)) {
    return icons.react;
  }
  if (/\bcaddy\b/.test(label)) return icons.caddy;
  if (/\bdocker\b/.test(label)) return icons.docker;
  if (/\bgoogle\b|\boidc\b/.test(label)) return icons.google;
  if (/\bhugging face\b/.test(label)) return icons.huggingface;
  if (/\bqwen\b/.test(label)) return icons.qwen;
  if (/\bbge-m3\b|embedding|vector\(1024\)/.test(label)) {
    return icons.huggingface;
  }
  if (/\bsqlite\b|\bfts5\b/.test(label)) return icons.sqlite;
  if (/\bredis\b/.test(label)) return icons.redis;
  if (/\balembic\b/.test(label)) return icons.python;
  if (
    /\bpostgresql\b|\bpgvector\b|\bhnsw\b|\bbm25\b|\bgin\b/.test(label) ||
    /(_DB|DB)$/.test(id) ||
    /(app_user|sso_identity|conversation|chat_message|conversation_summary|legal_document|legal_chunk|graphrag_chunk|legal_answer_cache|guest_rate_limit|signature_packet|user_feedback)/.test(
      label,
    )
  ) {
    return icons.postgresql;
  }
  if (/\btavily\b|search|retrieve|retrieval|lookup|query/.test(label)) {
    return icons.search;
  }
  if (/encrypt|cipher|integrity|authenticated|verification/.test(label)) {
    return icons.lock;
  }
  if (/rate.limit|ttl|schedule|nightly|24-hour|window/.test(label)) {
    return icons.clock;
  }
  if (/refresh|reindex|rerun|invalidate|upsert|update/.test(label)) {
    return icons.refresh;
  }
  if (/graph|relationship|ancestor|outgoing|incoming|edge/.test(label)) {
    return icons.network;
  }
  if (/message|chat|response|answer/.test(label)) return icons.message;
  if (/summary|memory|history/.test(label)) return icons.history;
  if (/user|citizen|identity|account|guest/.test(label)) return icons.user;
  if (/legal|law|article|clause|contract|signature/.test(label)) {
    return icons.scale;
  }
  if (/document|docx|pdf|html|source|citation/.test(label)) {
    return icons.document;
  }
  if (/download|ingest|send|receive/.test(label)) return icons.download;
  if (/parse|split|chunk|hierarchy|structure/.test(label)) {
    return icons.hierarchy;
  }
  if (/classif|normalize|filter|score/.test(label)) return icons.filter;
  if (/merge|fusion|combine/.test(label)) return icons.merge;
  if (/model|generate|verdict|assistant|grounded prompt/.test(label)) {
    return icons.brain;
  }
  if (/cache/.test(label)) return icons.database;
  if (/jsonl|json/.test(label)) return icons.json;
  if (/volume|storage|artifact/.test(label)) return icons.boxes;
  if (/worker|job|process|transaction|workflow/.test(label)) {
    return icons.workflow;
  }
  if (/service|runtime|server/.test(label)) return icons.server;
  if (/cloud|external/.test(label)) return icons.cloud;
  if (/key|token|session|cookie/.test(label)) return icons.key;
  if (/relation|link|belongs_to|chunk_of/.test(label)) return icons.link;
  if (/current|valid|check|status|effective/.test(label)) return icons.shield;
  if (/choose|available|eligible|updated|authenticated\?/.test(label)) {
    return icons.route;
  }
  return icons.layers;
}

function escapeXml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function numericAttribute(markup, name) {
  const match = markup.match(new RegExp(`\\b${name}="([0-9.-]+)"`));
  return match ? Number(match[1]) : null;
}

function shapeBounds(nodeGroup) {
  const rect = nodeGroup.match(/<rect\b[^>]*>/);
  if (rect) {
    const x = numericAttribute(rect[0], "x");
    const y = numericAttribute(rect[0], "y");
    const width = numericAttribute(rect[0], "width");
    const height = numericAttribute(rect[0], "height");
    if ([x, y, width, height].every(Number.isFinite)) {
      return { x, y, width, height };
    }
  }

  const polygon = nodeGroup.match(/<polygon\b[^>]*\bpoints="([^"]+)"/);
  if (polygon) {
    const values = polygon[1]
      .trim()
      .split(/[ ,]+/)
      .map(Number)
      .filter(Number.isFinite);
    const xs = values.filter((_, index) => index % 2 === 0);
    const ys = values.filter((_, index) => index % 2 === 1);
    if (xs.length && ys.length) {
      const x = Math.min(...xs);
      const y = Math.min(...ys);
      return {
        x,
        y,
        width: Math.max(...xs) - x,
        height: Math.max(...ys) - y,
      };
    }
  }

  const ellipse = nodeGroup.match(/<ellipse\b[^>]*>/);
  if (ellipse) {
    const cx = numericAttribute(ellipse[0], "cx");
    const cy = numericAttribute(ellipse[0], "cy");
    const rx = numericAttribute(ellipse[0], "rx");
    const ry = numericAttribute(ellipse[0], "ry");
    if ([cx, cy, rx, ry].every(Number.isFinite)) {
      return {
        x: cx - rx,
        y: cy - ry,
        width: rx * 2,
        height: ry * 2,
      };
    }
  }

  return null;
}

function inlineIcon(spec, x, y, size, label = "") {
  const data = iconData(spec);
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 ${data.width} ${data.height}" preserveAspectRatio="xMidYMid meet" overflow="visible"${label ? ` aria-label="${escapeXml(label)}"` : ' aria-hidden="true"'}>
${label ? `<title>${escapeXml(label)}</title>` : ""}
${data.body}
</svg>`;
}

function iconBadge(spec, x, y, nodeLabel) {
  const size = 30;
  return `<g class="technology-icon" transform="translate(${x}, ${y})">
  <title>${escapeXml(nodeLabel)} icon</title>
  <rect x="0" y="0" width="${size}" height="${size}" rx="9" fill="#FFFFFF" stroke="${spec.color}" stroke-width="1.25" stroke-opacity="0.55" filter="url(#icon-shadow)"/>
  ${inlineIcon(spec, 6, 6, 18)}
</g>`;
}

function polishNodeGroup(nodeGroup, filename) {
  const idMatch = nodeGroup.match(/\bdata-id="([^"]+)"/);
  const labelMatch = nodeGroup.match(/\bdata-label="([\s\S]*?)"\s+data-shape=/);
  const shapeMatch = nodeGroup.match(/\bdata-shape="([^"]+)"/);
  if (!idMatch || !labelMatch) return nodeGroup;

  const nodeId = idMatch[1];
  const label = labelMatch[1].replaceAll("\n", " ");
  const spec = chooseNodeIcon(filename, nodeId, label);
  const bounds = shapeBounds(nodeGroup);
  if (!bounds) return nodeGroup;

  let polished = nodeGroup;
  if (shapeMatch?.[1] === "rectangle") {
    polished = polished.replace(
      /<rect\b([^>]*?)\brx="0"\s+ry="0"([^>]*)>/,
      '<rect$1rx="12" ry="12"$2>',
    );
  }

  if (shapeMatch?.[1] !== "cylinder") {
    polished = polished.replace(
      /(<(?:rect|polygon|ellipse)\b[^>]*?)\sstroke="#CBD5E1"([^>]*>)/,
      `$1 stroke="${spec.color}" stroke-opacity="0.42"$2`,
    );
    polished = polished.replace(
      /(<(?:rect|polygon|ellipse)\b[^>]*?)(\s*\/?>)/,
      '$1 filter="url(#node-shadow)"$2',
    );
  }

  const badgeX = bounds.x - 32;
  const badgeY = bounds.y + Math.min(9, Math.max(3, (bounds.height - 30) / 2));
  return polished.replace(
    /<\/g>\s*$/,
    `${iconBadge(spec, badgeX, badgeY, label)}</g>`,
  );
}

function polishEntityGroup(entityGroup, filename) {
  const idMatch = entityGroup.match(/\bdata-id="([^"]+)"/);
  const labelMatch = entityGroup.match(/\bdata-label="([^"]+)"/);
  if (!idMatch || !labelMatch) return entityGroup;

  const bounds = shapeBounds(entityGroup);
  if (!bounds) return entityGroup;
  const spec = chooseNodeIcon(filename, idMatch[1], labelMatch[1]);

  let rectIndex = 0;
  let polished = entityGroup.replace(/<rect\b[^>]*>/g, (rect) => {
    rectIndex += 1;
    if (rectIndex > 2) return rect;
    let updated = rect.replace('rx="0" ry="0"', 'rx="12" ry="12"');
    if (rectIndex === 1) {
      updated = updated
        .replace(
          'stroke="#CBD5E1"',
          `stroke="${spec.color}" stroke-opacity="0.42"`,
        )
        .replace(/\s*\/?>$/, ' filter="url(#node-shadow)" />');
    }
    return updated;
  });

  const badgeX = bounds.x - 13;
  const badgeY = bounds.y + 3;
  return polished.replace(
    /<\/g>\s*$/,
    `${iconBadge(spec, badgeX, badgeY, labelMatch[1])}</g>`,
  );
}

function decorateDiagramSvg(svg, filename) {
  let decorated = svg.replace(
    /<g class="subgraph"[\s\S]*?<\/g>/g,
    (group) =>
      group
        .replaceAll('rx="0" ry="0"', 'rx="16" ry="16"')
        .replace(
          /(<rect\b[^>]*?)\sstroke-width="1"([^>]*>)/,
          '$1 stroke-width="1.15"$2',
        ),
  );

  decorated = decorated.replace(
    /<g class="node"[\s\S]*?<\/g>/g,
    (group) => polishNodeGroup(group, filename),
  );
  decorated = decorated.replace(
    /<g class="entity"[\s\S]*?<\/g>/g,
    (group) => polishEntityGroup(group, filename),
  );

  decorated = decorated
    .replace(
      /(<polyline class="edge"[^>]*?)\sstroke-width="1"([^>]*>)/g,
      '$1 stroke-width="1.35"$2',
    )
    .replace(
      /(<polyline class="er-relationship"[^>]*?)\sstroke-width="1"([^>]*>)/g,
      '$1 stroke-width="1.35"$2',
    )
    .replace(
      /(<text\b[^>]*?)\sfont-weight="500"([^>]*>)/g,
      '$1 font-weight="600"$2',
    );

  return decorated;
}

function prepareSourceForIconRender(source) {
  return source
    .replace(
      /[▶▦☁⚖⚙◷↻◆◉⌁⇩▣⊕≡⌕◫⇄✓✦⏱⇧⇢⇠]\s+/gu,
      "",
    )
    .replaceAll("G Google", "Google");
}

function flattenSvg(svg) {
  const replacements = new Map([
    ["var(--_text)", colors.fg],
    ["var(--_text-sec)", colors.muted],
    ["var(--_text-muted)", colors.muted],
    ["var(--_text-faint)", colors.faint],
    ["var(--_line)", colors.line],
    ["var(--_arrow)", colors.accent],
    ["var(--_node-fill)", colors.surface],
    ["var(--_node-stroke)", colors.border],
    ["var(--_group-fill)", colors.bg],
    ["var(--_group-hdr)", colors.groupHeader],
    ["var(--_inner-stroke)", colors.groupHeader],
    ["var(--_key-badge)", colors.groupHeader],
  ]);
  let flattened = svg.replace(/<style>[\s\S]*?<\/style>/, "");
  for (const [from, to] of replacements) {
    flattened = flattened.replaceAll(from, to);
  }
  return flattened.replace(
    /style="[^"]*background:[^"]*"/,
    `style="background:${colors.bg}"`,
  );
}

function addTechnicalCanvas(svg, title, subtitle) {
  const viewBox = svg.match(/viewBox="0 0 ([0-9.]+) ([0-9.]+)"/);
  if (!viewBox) throw new Error("Rendered SVG is missing a numeric viewBox");
  const originalWidth = Number(viewBox[1]);
  const originalHeight = Number(viewBox[2]);
  const horizontalPadding = 42;
  const headerHeight = 76;
  const bottomPadding = 24;
  const finalWidth = originalWidth + horizontalPadding * 2;
  const finalHeight = originalHeight + headerHeight + bottomPadding;
  const inner = svg
    .replace(/^<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "");

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${finalWidth} ${finalHeight}" width="${finalWidth}" height="${finalHeight}">
<defs>
  <filter id="node-shadow" x="-12%" y="-18%" width="124%" height="140%">
    <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#0F172A" flood-opacity="0.07"/>
  </filter>
  <filter id="icon-shadow" x="-35%" y="-35%" width="170%" height="180%">
    <feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-color="#0F172A" flood-opacity="0.12"/>
  </filter>
</defs>
<rect x="0" y="0" width="${finalWidth}" height="${finalHeight}" fill="#FFFFFF"/>
<text x="${horizontalPadding}" y="28" font-family="DejaVu Sans, sans-serif" font-size="22" font-weight="700" fill="#0F172A">${escapeXml(title)}</text>
<text x="${horizontalPadding}" y="50" font-family="DejaVu Sans, sans-serif" font-size="12" font-weight="400" fill="#475569">${escapeXml(subtitle)}</text>
<line x1="${horizontalPadding}" y1="64" x2="${finalWidth - horizontalPadding}" y2="64" stroke="#CBD5E1" stroke-width="1"/>
<g transform="translate(${horizontalPadding}, ${headerHeight})">
${inner}
</g>
</svg>`;
}

fs.mkdirSync(svgDir, { recursive: true });
fs.mkdirSync(pngDir, { recursive: true });

const failures = [];
for (const filename of Object.keys(diagramMeta)) {
  try {
    const rawSource = fs.readFileSync(path.join(sourceDir, filename), "utf8");
    const source = prepareSourceForIconRender(rawSource);
    const [title, subtitle] = diagramMeta[filename];
    const rendered = renderMermaidSVG(source, {
      ...colors,
      font: "DejaVu Sans",
      padding: 42,
      nodeSpacing: 34,
      layerSpacing: 58,
      componentSpacing: 34,
      thoroughness: 7,
    });
    const decorated = decorateDiagramSvg(flattenSvg(rendered), filename);
    const framed = addTechnicalCanvas(decorated, title, subtitle);
    const basename = filename.replace(/\.mmd$/, "");
    const svgPath = path.join(svgDir, `${basename}.svg`);
    const pngPath = path.join(pngDir, `${basename}.png`);
    fs.writeFileSync(svgPath, framed);

    const rasterizer = new Resvg(framed, {
      fitTo: { mode: "zoom", value: 2 },
      font: {
        loadSystemFonts: true,
        defaultFontFamily: "DejaVu Sans",
      },
    });
    fs.writeFileSync(pngPath, rasterizer.render().asPng());
    process.stdout.write(`Rendered ${filename}\n`);
  } catch (error) {
    failures.push(`${filename}: ${error instanceof Error ? error.stack : String(error)}`);
  }
}

if (failures.length) {
  process.stderr.write(`${failures.join("\n\n")}\n`);
  process.exit(1);
}
