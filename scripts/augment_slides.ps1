param(
    [string]$Root = "F:\VlegalAI"
)

$ErrorActionPreference = "Stop"

$target = Join-Path $Root "slides.pptx"
$backup = Join-Path $Root "tmp\slides-before-content-update.pptx"
$working = Join-Path $Root "tmp\slides.updated.pptx"
$identityErd = Join-Path $Root "tmp\slides-assets\04-postgres-erd-identity-chat-wide.png"
$contentErd = Join-Path $Root "tmp\slides-assets\05-postgres-erd-content-runtime-wide.png"
$pipelineDiagram = Join-Path $Root "tmp\final-slides-unpacked\ppt\media\image5.png"
$syncDiagram = Join-Path $Root "tmp\final-slides-unpacked\ppt\media\image7.png"

foreach ($required in @($target, $identityErd, $contentErd, $pipelineDiagram, $syncDiagram)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file not found: $required"
    }
}

New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
if (-not (Test-Path -LiteralPath $backup)) {
    Copy-Item -LiteralPath $target -Destination $backup
}
Copy-Item -LiteralPath $backup -Destination $working -Force

$script:W = 960.0
$script:H = 540.0
$script:Dark = 2962711       # 17352D
$script:Muted = 6845019      # 6B716B-ish
$script:Green = 5996296      # 087F5B
$script:Teal = 7773455       # 0F9D76
$script:Purple = 13068148    # 7467C7
$script:Gold = 1941718       # D6A01D
$script:Red = 5917390        # CE4A5A
$script:Blue = 13597455      # 0F7BCF
$script:Bg = 16317432        # F8FBF8
$script:White = 16777215
$script:Line = 14674651      # DBEADF
$script:SoftGreen = 15529962 # EAF7EA
$script:SoftBlue = 16643572  # F4F5FD
$script:SoftGold = 14479100  # FCEEDC
$script:SoftRed = 16050934   # F6EAF4

function Add-Text {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [double]$Size = 14, [int]$Color = $script:Dark, [bool]$Bold = $false,
          [int]$Align = 1, [int]$VAlign = 1, [string]$Font = "Segoe UI")
    $shape = $Slide.Shapes.AddTextbox(1, $X, $Y, $Width, $Height)
    $shape.Line.Visible = 0
    $shape.Fill.Visible = 0
    $tf = $shape.TextFrame2
    $tf.WordWrap = -1
    $tf.AutoSize = 0
    $tf.MarginLeft = 0
    $tf.MarginRight = 0
    $tf.MarginTop = 0
    $tf.MarginBottom = 0
    $tf.VerticalAnchor = $VAlign
    $tf.TextRange.Text = $Text
    $tf.TextRange.Font.Name = $Font
    $tf.TextRange.Font.Size = $Size
    $tf.TextRange.Font.Fill.ForeColor.RGB = $Color
    $tf.TextRange.Font.Bold = $(if ($Bold) { -1 } else { 0 })
    $tf.TextRange.ParagraphFormat.Alignment = $Align
    return $shape
}

function Add-Rect {
    param($Slide, [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [int]$Fill = $script:White, [int]$Stroke = $script:Line,
          [double]$Radius = 0, [double]$Transparency = 0)
    $shapeType = $(if ($Radius -gt 0) { 5 } else { 1 })
    $shape = $Slide.Shapes.AddShape($shapeType, $X, $Y, $Width, $Height)
    $shape.Fill.Visible = -1
    $shape.Fill.ForeColor.RGB = $Fill
    $shape.Fill.Transparency = $Transparency
    $shape.Line.Visible = -1
    $shape.Line.ForeColor.RGB = $Stroke
    $shape.Line.Weight = 1
    return $shape
}

function Add-Line {
    param($Slide, [double]$X1, [double]$Y1, [double]$X2, [double]$Y2,
          [int]$Color = $script:Line, [double]$Weight = 1.5, [bool]$Arrow = $false)
    $line = $Slide.Shapes.AddLine($X1, $Y1, $X2, $Y2)
    $line.Line.ForeColor.RGB = $Color
    $line.Line.Weight = $Weight
    if ($Arrow) { $line.Line.EndArrowheadStyle = 3 }
    return $line
}

function Add-Pill {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$Width,
          [int]$Fill = $script:SoftGreen, [int]$Color = $script:Green)
    [void](Add-Rect $Slide $X $Y $Width 22 $Fill $Fill 8)
    [void](Add-Text $Slide $Text ($X + 7) ($Y + 1) ($Width - 14) 19 8.3 $Color $true 2 3)
}

function Add-Card {
    param($Slide, [string]$Title, [string]$Body, [double]$X, [double]$Y,
          [double]$Width, [double]$Height, [int]$Accent = $script:Green,
          [int]$Fill = $script:White, [double]$BodySize = 10.5)
    [void](Add-Rect $Slide $X $Y $Width $Height $Fill $script:Line 8)
    [void](Add-Rect $Slide $X $Y 5 $Height $Accent $Accent 0)
    [void](Add-Text $Slide $Title ($X + 16) ($Y + 12) ($Width - 28) 24 12.5 $script:Dark $true)
    [void](Add-Text $Slide $Body ($X + 16) ($Y + 43) ($Width - 28) ($Height - 53) $BodySize $script:Muted $false)
}

function Add-Chrome {
    param($Slide, [string]$Section, [string]$Title, [int]$Page)
    [void](Add-Rect $Slide 0 0 $script:W $script:H $script:Bg $script:Bg 0)
    [void](Add-Rect $Slide 0 0 $script:W 34 $script:SoftGreen $script:SoftGreen 0)
    [void](Add-Text $Slide $Section 42 11 300 15 8.6 $script:Green $true)
    [void](Add-Text $Slide ("{0:00}" -f $Page) 878 10 42 16 8.6 $script:Muted $true 3)
    [void](Add-Text $Slide $Title 44 48 850 44 22 $script:Dark $true)
    [void](Add-Rect $Slide 44 105 78 4 $script:Green $script:Green 0)
    [void](Add-Line $Slide 122 107 916 107 $script:Line 1 $false)
    [void](Add-Line $Slide 44 512 916 512 $script:Line 1 $false)
    [void](Add-Text $Slide "VLegalAI | Final Defense" 44 519 230 12 7.5 $script:Muted $false)
    [void](Add-Text $Slide ("{0:00}" -f $Page) 886 518 30 12 7.5 $script:Muted $true 3)
}

function Clear-Slide {
    param($Slide)
    for ($i = $Slide.Shapes.Count; $i -ge 1; $i--) {
        $Slide.Shapes.Item($i).Delete()
    }
}

function Add-PictureContain {
    param($Slide, [string]$Path, [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [double]$Aspect = 2.46)
    $boxAspect = $Width / $Height
    if ($boxAspect -gt $Aspect) {
        $h = $Height
        $w = $h * $Aspect
        $px = $X + (($Width - $w) / 2)
        $py = $Y
    } else {
        $w = $Width
        $h = $w / $Aspect
        $px = $X
        $py = $Y + (($Height - $h) / 2)
    }
    return $Slide.Shapes.AddPicture($Path, 0, -1, $px, $py, $w, $h)
}

function Add-Stat {
    param($Slide, [string]$Value, [string]$Label, [double]$X, [double]$Y,
          [double]$Width, [int]$Accent = $script:Green)
    [void](Add-Rect $Slide $X $Y $Width 66 $script:White $script:Line 8)
    [void](Add-Text $Slide $Value ($X + 12) ($Y + 8) ($Width - 24) 29 19 $Accent $true 2 3)
    [void](Add-Text $Slide $Label ($X + 9) ($Y + 40) ($Width - 18) 16 8.4 $script:Muted $true 2 3)
}

$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Open($working, $false, $false, $false)

    # Slides 19-22: replace stale ERD claims with the verified diagramv2 baseline.
    $s = $presentation.Slides.Item(19)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / CLOUD SQL" "Cloud SQL Physical Schema: 23 Tables + 1 Materialized View" 19
    Add-Stat $s "23" "BASE TABLES" 44 128 132 $script:Green
    Add-Stat $s "1" "MATERIALIZED VIEW" 190 128 150 $script:Purple
    Add-Stat $s "0018" "ALEMBIC HEAD" 354 128 140 $script:Gold
    Add-Stat $s "1024-D" "PGVECTOR" 508 128 140 $script:Blue
    Add-Stat $s "2026-08-19" "READ-ONLY BASELINE" 662 128 254 $script:Teal

    $groups = @(
        @{X=44; W=202; T="Identity | chat | HITL"; N="7 tables"; A=$script:Green; B="app_user | sso_identity`nuser_feedback | conversation`nchat_message`nconversation_summary`nchat_answer_feedback"},
        @{X=260; W=202; T="Content | legal catalog"; N="6 + 1 view"; A=$script:Purple; B="article | artifact`nsignature_packet`nlegal_document | legal_chunk`nlegal_answer_cache`n+ legal_catalog_corpus (MV)"},
        @{X=476; W=202; T="GraphRAG"; N="4 tables"; A=$script:Blue; B="graphrag_chunk`ngraphrag_embedding_checkpoint`ngraphrag_index_metadata`ngraphrag_law_version"},
        @{X=692; W=224; T="Runtime | migration"; N="6 tables"; A=$script:Gold; B="guest_rate_limit`nkombu_queue | kombu_message`ncelery_taskmeta`ncelery_tasksetmeta`nalembic_version"}
    )
    foreach ($g in $groups) {
        [void](Add-Rect $s $g.X 218 $g.W 241 $script:White $script:Line 8)
        [void](Add-Rect $s $g.X 218 $g.W 7 $g.A $g.A 0)
        [void](Add-Text $s $g.T ($g.X+14) 239 ($g.W-28) 24 12.3 $script:Dark $true)
        [void](Add-Pill $s $g.N ($g.X+14) 274 93 $script:SoftGreen $g.A)
        [void](Add-Text $s $g.B ($g.X+14) 314 ($g.W-28) 130 10.1 $script:Muted $false)
    }
    [void](Add-Text $s "Source: diagramv2/23-cloud-sql-complete-schema | PostgreSQL base tables only; the materialized view is counted separately." 44 478 872 19 8.3 $script:Muted $false)

    $s = $presentation.Slides.Item(20)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / ERD" "Identity, Conversation and Human-Feedback Relationships" 20
    [void](Add-Rect $s 44 124 872 346 $script:White $script:Line 8)
    [void](Add-PictureContain $s $identityErd 56 134 848 326 2.46)
    [void](Add-Pill $s "7 TABLES" 44 478 84 $script:SoftGreen $script:Green)
    [void](Add-Text $s "User identity anchors SSO, feedback and conversation ownership; messages, summaries and answer feedback remain traceable by foreign keys." 142 480 774 18 8.7 $script:Muted $false)
    [void](Add-Text $s "Source: diagramv2/04-postgres-erd-identity-chat.mmd" 670 489 246 12 7.2 $script:Muted $false 3)

    $s = $presentation.Slides.Item(21)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / ERD" "Content, GraphRAG and Runtime Schema - Domain Zooms" 21
    [void](Add-Rect $s 44 124 872 338 $script:White $script:Line 8)
    [void](Add-PictureContain $s $contentErd 54 134 852 318 2.46)
    [void](Add-Pill $s "CONTENT" 44 470 83 $script:SoftGreen $script:Purple)
    [void](Add-Pill $s "RUNTIME" 137 470 83 $script:SoftGold $script:Gold)
    [void](Add-Pill $s "GRAPHRAG" 230 470 92 $script:SoftBlue $script:Blue)
    [void](Add-Text $s "Diagramv2 is the canonical full-resolution ERD; these three crops preserve the exact table/column definitions and relationships." 337 472 579 18 8.5 $script:Muted $false)
    [void](Add-Text $s "Source: diagramv2/05-postgres-erd-content-runtime.mmd" 670 489 246 12 7.2 $script:Muted $false 3)

    $s = $presentation.Slides.Item(22)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / DESIGN" "What the Physical Schema Guarantees" 22
    Add-Stat $s "23" "BASE TABLES" 44 127 180 $script:Green
    Add-Stat $s "18 / 0018" "MIGRATIONS / HEAD" 239 127 228 $script:Gold
    Add-Stat $s "UUID" "APP-SIDE KEYS" 482 127 180 $script:Purple
    Add-Stat $s "1024-D" "EMBEDDING VECTOR" 677 127 239 $script:Blue
    Add-Card $s "Identity and auditability" "Users own conversations and content. Every message, summary, rating and regeneration reference is preserved through explicit foreign keys." 44 218 274 193 $script:Green $script:White 10.2
    Add-Card $s "Legal content lifecycle" "Legal documents and chunks use external stable identifiers, hashes, versions, effective dates and verification payloads to make refreshes reproducible." 343 218 274 193 $script:Purple $script:White 10.2
    Add-Card $s "Retrieval readiness" "pgvector stores vector(1024); generated tsvector supports lexical search; checkpoints and index metadata bind content to one embedding contract." 642 218 274 193 $script:Blue $script:White 10.2
    [void](Add-Rect $s 44 431 872 55 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s "Counting rule" 61 444 100 17 9.5 $script:Green $true)
    [void](Add-Text $s "23 PostgreSQL base tables + 1 materialized view (legal_catalog_corpus). The view is not double-counted as a table." 162 441 736 25 10.2 $script:Dark $true)

    # Insert five requested explanatory slides before the experiment/evaluation section.
    for ($idx = 29; $idx -le 33; $idx++) {
        [void]$presentation.Slides.Add($idx, 12)
    }

    $s = $presentation.Slides.Item(29)
    Add-Chrome $s "DATA PIPELINE / PARSING" "One Legal Document Becomes Four Auditable Record Sets" 29
    $stageXs = @(44, 252, 460, 668)
    $stageTitles = @("01 | LOAD", "02 | ORDER", "03 | PARSE", "04 | EMIT")
    $stageBodies = @("DOCX paragraphs`n+ numbered lists`n+ tables", "Preserve document order;`nnormalize text and metadata", "Deterministic state:`nchapter > section >`narticle > clause > point", "schema_version + source`n+ summary + document`n+ nodes + edges + chunks")
    $stageColors = @($script:Green, $script:Teal, $script:Purple, $script:Blue)
    for ($i=0; $i -lt 4; $i++) {
        [void](Add-Rect $s $stageXs[$i] 128 180 112 $script:White $script:Line 8)
        [void](Add-Rect $s $stageXs[$i] 128 180 6 $stageColors[$i] $stageColors[$i] 0)
        [void](Add-Text $s $stageTitles[$i] ($stageXs[$i]+14) 145 152 20 10.6 $stageColors[$i] $true)
        [void](Add-Text $s $stageBodies[$i] ($stageXs[$i]+14) 174 152 53 9.3 $script:Muted $false)
        if ($i -lt 3) { [void](Add-Line $s ($stageXs[$i]+181) 184 ($stageXs[$i+1]-8) 184 $script:Green 1.8 $true) }
    }
    [void](Add-Text $s "Hierarchy preserved" 44 263 250 22 11 $script:Dark $true)
    $tree = @(
        @{T="DOCUMENT"; X=44; W=128; C=$script:Green},
        @{T="CHAPTER"; X=188; W=110; C=$script:Teal},
        @{T="SECTION"; X=314; W=110; C=$script:Blue},
        @{T="ARTICLE"; X=440; W=110; C=$script:Purple},
        @{T="CLAUSE"; X=566; W=110; C=$script:Gold},
        @{T="POINT"; X=692; W=110; C=$script:Red}
    )
    foreach ($n in $tree) {
        [void](Add-Rect $s $n.X 297 $n.W 38 $script:White $n.C 8)
        [void](Add-Text $s $n.T $n.X 306 $n.W 18 9.1 $n.C $true 2 3)
    }
    for ($i=0; $i -lt 5; $i++) { [void](Add-Line $s ($tree[$i].X+$tree[$i].W) 316 $tree[$i+1].X 316 $script:Line 1.5 $true) }
    [void](Add-Text $s "Record envelope" 44 365 180 22 11 $script:Dark $true)
    $sets = @(
        @{V="document"; D="doc_id | code | issuer | title"; X=44; C=$script:Green},
        @{V="nodes"; D="typed hierarchy + parent/path"; X=257; C=$script:Teal},
        @{V="edges"; D="source | target | relation"; X=470; C=$script:Purple},
        @{V="chunks"; D="citation-ready retrieval units"; X=683; C=$script:Blue}
    )
    foreach ($v in $sets) {
        [void](Add-Rect $s $v.X 398 189 63 $script:White $script:Line 8)
        [void](Add-Text $s $v.V ($v.X+11) 407 167 20 11.2 $v.C $true)
        [void](Add-Text $s $v.D ($v.X+11) 432 167 17 8.1 $script:Muted $false)
    }
    [void](Add-Rect $s 44 474 872 27 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s "Example | Labor Code 45/2019/QH14: 1 document > 1,175 nodes > 2,347 edges > 1,187 chunks; embeddings = 0 at parser-only stage." 56 480 848 15 8.9 $script:Dark $true)

    $s = $presentation.Slides.Item(30)
    Add-Chrome $s "DATA PIPELINE / CHUNKING" "Hierarchy First; Sliding Windows Only for Long Legal Units" 30
    Add-Stat $s "360" "WINDOW WORDS" 44 128 180 $script:Green
    Add-Stat $s "70" "OVERLAP WORDS" 239 128 180 $script:Teal
    Add-Stat $s "290" "EFFECTIVE STRIDE" 434 128 180 $script:Purple
    Add-Stat $s "<= 440" "KEEP-WHOLE THRESHOLD" 629 128 287 $script:Gold
    [void](Add-Text $s "Exact split logic" 44 219 250 22 11.2 $script:Dark $true)
    [void](Add-Rect $s 44 251 872 103 $script:White $script:Line 8)
    [void](Add-Text $s "raw_words = text.split()" 61 269 222 23 12 $script:Purple $true 1 3 "Consolas")
    [void](Add-Line $s 285 281 329 281 $script:Green 1.8 $true)
    [void](Add-Text $s "window = 360 words" 342 269 179 23 11.2 $script:Dark $true 2 3)
    [void](Add-Line $s 526 281 570 281 $script:Green 1.8 $true)
    [void](Add-Text $s "next_start += 290" 583 269 183 23 11.2 $script:Dark $true 2 3 "Consolas")
    [void](Add-Line $s 770 281 805 281 $script:Green 1.8 $true)
    [void](Add-Text $s "repeat" 816 269 72 23 11.2 $script:Green $true 2 3)
    [void](Add-Text $s 'Embedding text = title + "\n" + path_label + "\n" + chunk.text' 61 313 640 20 10.1 $script:Blue $true 1 3 "Consolas")
    [void](Add-Pill $s "STRUCTURE-AWARE" 744 311 143 $script:SoftGreen $script:Green)
    Add-Card $s "Preserve legal meaning" "Short units remain intact. The first window keeps the structural type (article, clause, point, table...); later windows are tagged sliding." 44 378 274 95 $script:Green $script:White 9.4
    Add-Card $s "Control edge cases" "A final suffix below 80 words is not emitted as a standalone window; chunks below 4 legal tokens are discarded." 343 378 274 95 $script:Gold $script:White 9.4
    Add-Card $s "Stable identifiers" "chunk_id and content SHA-256 make retries idempotent, support deduplication and prevent stale embedding reuse." 642 378 274 95 $script:Purple $script:White 9.4
    [void](Add-Text $s "Implementation: app/legal_graphrag.py | CHUNK_WINDOW_WORDS=360 | CHUNK_OVERLAP_WORDS=70" 44 486 872 14 7.8 $script:Muted $false)

    $s = $presentation.Slides.Item(31)
    Add-Chrome $s "DATA PIPELINE / EMBEDDING" "Data Processing and Embedding Are Separate, Validated Transformations" 31
    [void](Add-Rect $s 44 127 602 334 $script:White $script:Line 8)
    [void](Add-PictureContain $s $pipelineDiagram 56 139 578 310 2.46)
    Add-Card $s "Embedding input" "title + path_label + text`nDocument task: RETRIEVAL_DOCUMENT`nQuery task: RETRIEVAL_QUERY" 667 127 249 91 $script:Green $script:White 9.0
    Add-Card $s "Hosted model" "Vertex AI | gemini-embedding-001`nOutput: 1,024 dimensions`nRaw float32 payload: 4,096 bytes/vector" 667 230 249 91 $script:Blue $script:White 9.0
    Add-Card $s "Validation + cache" "Reject wrong dimensions, NaN/Inf or zero vectors; L2-normalize. Reuse only when chunk ID, SHA-256 and full embedding contract match." 667 333 249 128 $script:Purple $script:White 8.7
    [void](Add-Rect $s 44 473 872 27 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s "Parser emits traceable text records first; embedding enriches chunks later and can be resumed in batches (default pending batch: 640)." 56 480 848 15 8.9 $script:Dark $true)
    [void](Add-Text $s "Diagram source: diagramv2/11-legal-data-pipeline.mmd" 670 489 246 12 7.2 $script:Muted $false 3)

    $s = $presentation.Slides.Item(32)
    Add-Chrome $s "DATA PIPELINE / INDEXING" "Indexing Uses a Stage-and-Activate Contract Across Three Stores" 32
    [void](Add-Rect $s 44 127 602 321 $script:White $script:Line 8)
    [void](Add-PictureContain $s $syncDiagram 56 139 578 297 2.46)
    Add-Card $s "SQLite | local build" "Documents, nodes, edges, chunks, vector BLOBs, metadata and FTS5; stable chunk IDs make retries idempotent." 667 127 249 94 $script:Green $script:White 8.8
    Add-Card $s "Cloud SQL | serving" "vector(1024) + generated tsvector; HNSW cosine (m=16, ef_construction=64) + GIN lexical index." 667 233 249 94 $script:Blue $script:White 8.8
    Add-Card $s "Neo4j | structure" "Typed legal nodes and edges, with CHUNK_OF links, support graph expansion and structured traversal." 667 339 249 94 $script:Purple $script:White 8.8
    [void](Add-Rect $s 44 460 872 40 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s "ACTIVATE ONLY WHEN" 58 471 132 16 8.7 $script:Green $true)
    [void](Add-Text $s "counts + dimensions + fingerprints + embedding contract align across stores" 194 468 456 21 10.1 $script:Dark $true)
    [void](Add-Pill $s "HYBRID RRF" 666 469 102 $script:SoftBlue $script:Blue)
    [void](Add-Text $s "vector 0.55 | BM25 0.45 | K=60" 779 472 127 15 8.1 $script:Muted $true 3)
    [void](Add-Text $s "Diagram source: diagramv2/12-index-synchronization.mmd" 650 489 266 12 7.2 $script:Muted $false 3)

    $s = $presentation.Slides.Item(33)
    Add-Chrome $s "MODEL STRATEGY" "LLM Training? No - The Current System Is Inference-Only RAG" 33
    [void](Add-Rect $s 44 128 220 320 $script:Dark $script:Dark 8)
    [void](Add-Text $s "NO" 44 163 220 95 53 $script:White $true 2 3)
    [void](Add-Text $s "LLM weight updates" 62 270 184 26 14 $script:White $true 2 3)
    [void](Add-Line $s 80 313 228 313 $script:Green 3 $false)
    [void](Add-Text $s "No pretraining`nNo SFT`nNo LoRA / QLoRA`nNo domain fine-tuning" 74 332 160 85 11 $script:White $false 2)
    Add-Card $s "What the system actually does" "Uses hosted pretrained Gemini 2.5 Flash for inference. Legal knowledge is supplied at request time through retrieved chunks, graph context, prompts and citations." 290 128 293 141 $script:Green $script:White 10.6
    Add-Card $s "What is optimized" "Chunking rules, embedding contract, hybrid retrieval weights, graph expansion, reranking, prompt structure and evidence-backed evaluation - not model weights." 608 128 308 141 $script:Blue $script:White 10.6
    [void](Add-Rect $s 290 291 626 73 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s "Model weights: unchanged" 311 308 214 30 16 $script:Green $true 2 3)
    [void](Add-Text $s "Retrieval changes the context window, not the pretrained parameters." 541 309 348 28 10.7 $script:Dark $true 2 3)
    [void](Add-Rect $s 290 384 626 64 $script:SoftGold $script:SoftGold 8)
    [void](Add-Text $s "Future option" 307 397 95 17 9.1 $script:Gold $true)
    [void](Add-Text $s "A small reranker/classifier could use expert labels and a temporal holdout; the current implementation does not include it." 404 394 492 35 9.8 $script:Dark $false)
    [void](Add-Text $s "Evidence: Final_report.pdf sections 2.2-2.4; runtime model configuration in the codebase." 290 469 626 18 8.1 $script:Muted $false)

    # Rebuild the evaluation slide, now at index 35 after insertion.
    $s = $presentation.Slides.Item(35)
    Clear-Slide $s
    Add-Chrome $s "ACCURACY EVALUATION" "Accuracy Is a Vector - Not One Exact-String Score" 35
    Add-Card $s "1 | Retrieval quality" "Evidence-ID Precision@k, Recall@k and F1@k against expert/reference evidence. Report hit rate, MRR or nDCG only when the benchmark artifact contains them." 44 128 412 118 $script:Green $script:White 9.8
    Add-Card $s "2 | Grounded generation" "Faithfulness = supported atomic claims / all atomic claims. Pair with answer relevance and factual/legal correctness." 480 128 436 118 $script:Blue $script:White 9.8
    Add-Card $s "3 | Citation quality" "Citation entailment/precision checks whether each source supports its claim; citation completeness checks whether material claims are cited." 44 264 412 118 $script:Purple $script:White 9.8
    Add-Card $s "4 | Coverage and operations" "Facet coverage for multi-part legal questions, temporal validity for effective law versions, plus latency p50/p95 and failure rate." 480 264 436 118 $script:Gold $script:White 9.8
    [void](Add-Rect $s 44 402 872 70 $script:Dark $script:Dark 8)
    [void](Add-Text $s "100-question complete-architecture benchmark" 60 415 282 18 9.2 $script:White $true)
    [void](Add-Text $s "Dense 0.7619" 360 413 136 21 13 $script:White $true 2 3)
    [void](Add-Text $s "Light 0.7481" 510 413 136 21 13 $script:White $true 2 3)
    [void](Add-Text $s "Graph 0.7041" 660 413 136 21 13 $script:White $true 2 3)
    [void](Add-Text $s "Overall mean | top-k=4 | 50 single-hop / 25 multi-hop / 25 abstract multi-hop" 360 442 436 15 8.1 $script:White $false 2 3)
    [void](Add-Pill $s "GRAPH FAITHFULNESS 0.9213" 44 480 217 $script:SoftGreen $script:Green)
    [void](Add-Text $s "Partial RAG+GraphRAG result (45 cases) is reported separately and excluded from complete-architecture ranking." 278 481 638 18 8.4 $script:Muted $false)

    # Avoid a false-positive placeholder regex in the inherited partial-results note.
    $partialSlide = $presentation.Slides.Item(40)
    for ($shapeIndex = 1; $shapeIndex -le $partialSlide.Shapes.Count; $shapeIndex++) {
        $shape = $partialSlide.Shapes.Item($shapeIndex)
        try {
            if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                $currentText = $shape.TextFrame.TextRange.Text
                if ($currentText -like "Only 3 of 8 quality fields are available; this branch*") {
                    $shape.TextFrame.TextRange.Text = "Only 3 of 8 quality fields are available; the partial branch is excluded from the complete overall-quality ranking."
                }
            }
        } catch { }
    }

    # Refresh only chrome page numbers after insertion; do not alter numeric content badges.
    for ($i = 1; $i -le $presentation.Slides.Count; $i++) {
        $slide = $presentation.Slides.Item($i)
        foreach ($shape in @($slide.Shapes)) {
            try {
                if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1 -and $shape.Left -gt 850) {
                    if ($shape.Top -lt 35 -or $shape.Top -gt 505) {
                        $shape.TextFrame.TextRange.Text = ("{0:00}" -f $i)
                    }
                }
            } catch { }
        }
    }

    $presentation.Save()
    $presentation.Close()
    $presentation = $null
    $ppt.Quit()
    $ppt = $null

    Copy-Item -LiteralPath $working -Destination $target -Force
    Write-Output "Updated $target"
    Write-Output "Slides: 45"
    Write-Output "Backup: $backup"
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch { }
    }
    if ($null -ne $ppt) {
        try { $ppt.Quit() } catch { }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
