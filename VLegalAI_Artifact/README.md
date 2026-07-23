# VLegalAI Architecture Kit — Schematic Edition

Source-accurate English diagrams for `tuankiettran287/VlegalAI` at commit `18c0c25ed7a66f6f9088320522bba102ea6427d6`.

## Included

- 10 editable Mermaid files in `mermaid/`.
- 10 high-resolution, hand-composed schematic PNG images in `images/png/`.
- 10 scalable, hand-composed schematic SVG images in `images/svg/`.
- `images/png/00_architecture_gallery.png`, a one-page overview of the complete set.
- `ARCHITECTURE_REPORT.md` with architecture decisions and source traceability.
- `DATABASE_DESIGN.md` with the physical data model, indexes, constraints, protection boundaries, and cross-store contracts.
- `ICON_ATTRIBUTION.md` with icon-library and trademark attribution.

The visual language follows a professional architecture-schematic format:
landscape canvas, warm engineering-paper background, graph grid, dashed system
boundaries, thin orthogonal connectors, compact component boxes, and embedded
technology marks. It intentionally avoids presentation-card framing and
auto-layout artifacts.

Recognizable technology marks are used for FastAPI, PostgreSQL, Neo4j, React,
Docker, Celery, Caddy, Google, Hugging Face/BGE-M3, SQLite, Python, and
Alibaba Cloud/Qwen. Generic workflow nodes use a consistent Lucide icon set.
All marks are embedded in the generated SVG and PNG files; the images make no
request to an external icon CDN.

## Diagram set

1. System Design
2. PostgreSQL ERD
3. Physical Database Design
4. Application Workflow
5. Legal Data Pipeline
6. Database Write Flow
7. Legal Query Flow
8. Chat History Flow
9. GraphRAG Storage Flow
10. HybridRAG Query Flow

## Open on Windows

The ZIP is flat: after extraction, `README.md`, `mermaid/`, `images/`, and
`tools/` appear immediately. Open PNG files with Photos, SVG files with a
browser, and `.mmd` files with Mermaid Live or a Mermaid-enabled editor.

## Re-render the schematic images

The `.mmd` files use standard Mermaid syntax and include lightweight Unicode
fallback symbols, so they can be opened directly in Mermaid Live, VS Code
Mermaid extensions, GitHub Markdown, or Mermaid CLI.

To reproduce the hand-composed branded SVG/PNG renders included in this kit:

```bash
npm install
npm run render
```

Node.js 20 or newer is recommended.

The premium SVG layouts live in `tools/render_schematic_diagrams.mjs`. The
Mermaid files remain the portable, editable logical counterparts. To render the
Mermaid auto-layout edition instead, run `npm run render:mermaid`.

## Recommended reading order

Start with:

1. `ARCHITECTURE_REPORT.md`
2. `images/png/01_system_design.png`
3. `images/png/02_postgresql_erd.png`
4. `images/png/10_hybrid_rag_query_flow.png`
