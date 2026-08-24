# VLegalAI Architecture Diagrams v2

This directory contains a code- and runtime-aligned architecture pack for VLegalAI. Mermaid sources in `src/` are the canonical editable definitions. `render-pdf.ps1` compiles those sources into tightly fitted vector PDFs under `pdf/`; the LaTeX report consumes those vector artifacts and does not consume PNG previews. SVG and PNG files remain optional browser/preview artifacts only.

## Code-first report build

```powershell
.\diagramv2\render-pdf.ps1
& .\.tmp\tectonic-0.17.0\tectonic.exe -X compile .\VlegalAI_Report.tex --outdir .\output\pdf
```

The `--pdfFit` Mermaid CLI option makes each generated page match the chart bounding box. Text, nodes, and connectors remain vector objects in the report PDF, so the diagrams can be enlarged without raster blur. Every architecture figure in `VlegalAI_Report.tex` names the corresponding Mermaid diagram ID; edits therefore begin in `diagramv2/src/*.mmd`, not in an image editor.

## Quick entry points

- Production system design: [SVG](svg/02-production-deployment.svg) · [PNG](png/02-production-deployment.png)
- Cloud SQL ERD — identity, chat, and HITL: [SVG](svg/04-postgres-erd-identity-chat.svg) · [PNG](png/04-postgres-erd-identity-chat.png)
- Cloud SQL ERD — content and runtime: [SVG](svg/05-postgres-erd-content-runtime.svg) · [PNG](png/05-postgres-erd-content-runtime.png)
- Cloud SQL table inventory — all 23 tables: [SVG](svg/23-cloud-sql-complete-schema.svg) · [PNG](png/23-cloud-sql-complete-schema.png)
- Neo4j legal ontology: [SVG](svg/07-neo4j-knowledge-graph.svg) · [PNG](png/07-neo4j-knowledge-graph.png)
- End-to-end chat sequence: [SVG](svg/09-chat-request-sequence.svg) · [PNG](png/09-chat-request-sequence.png)
- Legal-data pipeline: [SVG](svg/11-legal-data-pipeline.svg) · [PNG](png/11-legal-data-pipeline.png)
- CI/CD release workflow: [SVG](svg/18-cicd-release-workflow.svg) · [PNG](png/18-cicd-release-workflow.png)

## Diagram catalogue

| No. | View | Mermaid source | SVG |
|---:|---|---|---|
| 01 | System context | [src/01-system-context.mmd](src/01-system-context.mmd) | [svg/01-system-context.svg](svg/01-system-context.svg) |
| 02 | Production deployment | [src/02-production-deployment.mmd](src/02-production-deployment.mmd) | [svg/02-production-deployment.svg](svg/02-production-deployment.svg) |
| 03 | Application components | [src/03-application-components.mmd](src/03-application-components.mmd) | [svg/03-application-components.svg](svg/03-application-components.svg) |
| 04 | PostgreSQL ERD: identity, chat, HITL | [src/04-postgres-erd-identity-chat.mmd](src/04-postgres-erd-identity-chat.mmd) | [svg/04-postgres-erd-identity-chat.svg](svg/04-postgres-erd-identity-chat.svg) |
| 05 | PostgreSQL ERD: content and runtime | [src/05-postgres-erd-content-runtime.mmd](src/05-postgres-erd-content-runtime.mmd) | [svg/05-postgres-erd-content-runtime.svg](svg/05-postgres-erd-content-runtime.svg) |
| 06 | GraphRAG storage model | [src/06-graphrag-storage-model.mmd](src/06-graphrag-storage-model.mmd) | [svg/06-graphrag-storage-model.svg](svg/06-graphrag-storage-model.svg) |
| 07 | Neo4j legal knowledge graph | [src/07-neo4j-knowledge-graph.mmd](src/07-neo4j-knowledge-graph.mmd) | [svg/07-neo4j-knowledge-graph.svg](svg/07-neo4j-knowledge-graph.svg) |
| 08 | End-to-end user journey | [src/08-end-to-end-user-journey.mmd](src/08-end-to-end-user-journey.mmd) | [svg/08-end-to-end-user-journey.svg](svg/08-end-to-end-user-journey.svg) |
| 09 | Chat request sequence | [src/09-chat-request-sequence.mmd](src/09-chat-request-sequence.mmd) | [svg/09-chat-request-sequence.svg](svg/09-chat-request-sequence.svg) |
| 10 | Adaptive retrieval routing | [src/10-adaptive-retrieval-routing.mmd](src/10-adaptive-retrieval-routing.mmd) | [svg/10-adaptive-retrieval-routing.svg](svg/10-adaptive-retrieval-routing.svg) |
| 11 | Legal-data ingestion pipeline | [src/11-legal-data-pipeline.mmd](src/11-legal-data-pipeline.mmd) | [svg/11-legal-data-pipeline.svg](svg/11-legal-data-pipeline.svg) |
| 12 | Local-to-cloud index synchronization | [src/12-index-synchronization.mmd](src/12-index-synchronization.mmd) | [svg/12-index-synchronization.svg](svg/12-index-synchronization.svg) |
| 13 | Freshness and replacement workflow | [src/13-freshness-reindex-workflow.mmd](src/13-freshness-reindex-workflow.mmd) | [svg/13-freshness-reindex-workflow.svg](svg/13-freshness-reindex-workflow.svg) |
| 14 | Google OIDC sign-in | [src/14-google-oidc-sequence.mmd](src/14-google-oidc-sequence.mmd) | [svg/14-google-oidc-sequence.svg](svg/14-google-oidc-sequence.svg) |
| 15 | Attachment question workflow | [src/15-attachment-question-workflow.mmd](src/15-attachment-question-workflow.mmd) | [svg/15-attachment-question-workflow.svg](svg/15-attachment-question-workflow.svg) |
| 16 | Contract feature workflows | [src/16-contract-workflows.mmd](src/16-contract-workflows.mmd) | [svg/16-contract-workflows.svg](svg/16-contract-workflows.svg) |
| 17 | Article research and publishing | [src/17-article-publishing-workflow.mmd](src/17-article-publishing-workflow.mmd) | [svg/17-article-publishing-workflow.svg](svg/17-article-publishing-workflow.svg) |
| 18 | CI/CD and release flow | [src/18-cicd-release-workflow.mmd](src/18-cicd-release-workflow.mmd) | [svg/18-cicd-release-workflow.svg](svg/18-cicd-release-workflow.svg) |
| 19 | Conversation and feedback states | [src/19-conversation-feedback-state.mmd](src/19-conversation-feedback-state.mmd) | [svg/19-conversation-feedback-state.svg](svg/19-conversation-feedback-state.svg) |
| 20 | Observability and failure recovery | [src/20-observability-recovery.mmd](src/20-observability-recovery.mmd) | [svg/20-observability-recovery.svg](svg/20-observability-recovery.svg) |
| 21 | Measured data landscape | [src/21-measured-data-landscape.mmd](src/21-measured-data-landscape.mmd) | [svg/21-measured-data-landscape.svg](svg/21-measured-data-landscape.svg) |
| 22 | Frontend sitemap and API surface | [src/22-frontend-api-map.mmd](src/22-frontend-api-map.mmd) | [svg/22-frontend-api-map.svg](svg/22-frontend-api-map.svg) |
| 23 | Cloud SQL table inventory: all physical tables | [src/23-cloud-sql-complete-schema.mmd](src/23-cloud-sql-complete-schema.mmd) | [svg/23-cloud-sql-complete-schema.svg](svg/23-cloud-sql-complete-schema.svg) |

## Evidence baseline

Validated on **2026-08-19** using read-only inspection of the current branch, Cloud Run resources, Cloud SQL PostgreSQL schema, and the local GraphRAG snapshot.

- Cloud Run service: `vlegalai`, Gen2, 8 vCPU, 16 GiB RAM, concurrency 16, timeout 3600 seconds, autoscale 0–2 instances.
- Worker pools: `vlegal-worker` (2 vCPU, 4 GiB) and `vlegal-beat` (1 vCPU, 512 MiB), both active with one instance.
- Jobs: `vlegal-migrate`, `vlegal-reindex` (4 vCPU, 8 GiB, 24-hour timeout), and `vlegal-publish-article` (2 vCPU, 2 GiB).
- Cloud SQL: PostgreSQL with `vector`; 23 application/runtime tables. Current measured rows include 13 users, 284 conversations, 749 messages, 32,334 GraphRAG chunks, 74 law versions, and 9 articles.
- Diagrams 04 and 05 document all 23 base tables in detail. Diagram 23 provides a single-page inventory and distinguishes the `legal_catalog_corpus` materialized view from those tables.
- Local GraphRAG snapshot: 74 documents, 29,575 nodes, 108,368 edges, and 32,334 chunks. The local chunk count equals the Cloud SQL `graphrag_chunk` count.
- Live Neo4j schema probing was unavailable from the workstation because the configured Aura hostname did not resolve. The graph view is therefore derived from `app/legal_ontology.py`, `app/legal_graphrag.py`, `app/external_graphrag.py`, and the local synchronized snapshot.

## Important implementation note

`app/worker.py` declares the legal freshness task every 10 days, while the deployed beat entry point uses `app/scheduler.py`, which currently schedules it every 24 hours. Diagram 13 shows both the intended policy and the actual deployed scheduler path so this discrepancy is visible rather than hidden.

## Visual conventions

- Arrow direction always follows the initiator or producer toward the invoked component, destination, or persisted result.
- Solid blue/green arrows: runtime request, data movement, or state transition.
- Dashed purple arrows: deployment, scheduling, configuration, or operator control.
- Dashed gray links: measured parity or another logical correlation, never runtime data movement.
- Sequence diagrams use chronological top-to-bottom messages; ERDs use crow's-foot relationships rather than process arrows.
- Red nodes: validation failure, fallback, or operator attention.
- Connectors are routed by phase or layer so unrelated flows do not share a line or cross through nodes.
- Each diagram focuses on one architectural question; detail is delegated to the next numbered view instead of duplicating arrow networks.

## Design and rendering method

The diagram taxonomy, semantic color system, connector discipline, and focus-per-view rule follow the visual guidance in [axton-obsidian-visual-skills](https://github.com/axtonliu/axton-obsidian-visual-skills). Mermaid sources were batch-tested using the workflow described by [Pretty Mermaid Skills](https://github.com/imxv/Pretty-mermaid-skills), then rendered with the official Mermaid CLI and `mermaid-config.json` to preserve multiline labels and ERD notation. `preview.html` provides a local fit-to-viewport viewer for any generated SVG.

Validation result: **24 Mermaid sources and 24 vector PDF outputs**. The report embeds these code-defined vector diagrams directly.
