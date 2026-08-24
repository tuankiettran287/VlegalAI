param(
    [string]$Root = "F:\VlegalAI"
)

$ErrorActionPreference = "Stop"

$target = Join-Path $Root "slides.pptx"
$backup = Join-Path $Root "tmp\slides-before-readability-fix.pptx"
$working = Join-Path $Root "tmp\slides.readable.pptx"

if (-not (Test-Path -LiteralPath $target)) {
    throw "Target not found: $target"
}

New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
if (-not (Test-Path -LiteralPath $backup)) {
    Copy-Item -LiteralPath $target -Destination $backup
}
Copy-Item -LiteralPath $backup -Destination $working -Force

$script:W = 960.0
$script:H = 540.0
$script:Dark = 2962711
$script:Muted = 6845019
$script:Green = 5996296
$script:Teal = 7773455
$script:Purple = 13068148
$script:Gold = 1941718
$script:Red = 5917390
$script:Blue = 13597455
$script:Bg = 16317432
$script:White = 16777215
$script:Line = 14674651
$script:SoftGreen = 15529962
$script:SoftBlue = 16643572
$script:SoftGold = 14479100
$script:SoftPurple = 16775418
$script:SoftGray = 16119285

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
    $shape.Line.Weight = 1.2
    return $shape
}

function Add-Line {
    param($Slide, [double]$X1, [double]$Y1, [double]$X2, [double]$Y2,
          [int]$Color = $script:Line, [double]$Weight = 1.5,
          [bool]$Arrow = $false, [bool]$Dashed = $false)
    $line = $Slide.Shapes.AddLine($X1, $Y1, $X2, $Y2)
    $line.Line.ForeColor.RGB = $Color
    $line.Line.Weight = $Weight
    if ($Arrow) { $line.Line.EndArrowheadStyle = 3 }
    if ($Dashed) { $line.Line.DashStyle = 4 }
    return $line
}

function Clear-Slide {
    param($Slide)
    for ($i = $Slide.Shapes.Count; $i -ge 1; $i--) {
        $Slide.Shapes.Item($i).Delete()
    }
}

function Add-Chrome {
    param($Slide, [string]$Section, [string]$Title, [int]$Page)
    [void](Add-Rect $Slide 0 0 $script:W $script:H $script:Bg $script:Bg 0)
    [void](Add-Rect $Slide 0 0 $script:W 34 $script:SoftGreen $script:SoftGreen 0)
    [void](Add-Text $Slide $Section 42 11 330 15 8.6 $script:Green $true)
    [void](Add-Text $Slide ("{0:00}" -f $Page) 878 10 42 16 8.6 $script:Muted $true 3)
    [void](Add-Text $Slide $Title 44 48 872 44 22 $script:Dark $true)
    [void](Add-Rect $Slide 44 105 78 4 $script:Green $script:Green 0)
    [void](Add-Line $Slide 122 107 916 107 $script:Line 1 $false)
    [void](Add-Line $Slide 44 512 916 512 $script:Line 1 $false)
    [void](Add-Text $Slide "VLegalAI | Final Defense" 44 519 230 12 7.5 $script:Muted $false)
    [void](Add-Text $Slide ("{0:00}" -f $Page) 886 518 30 12 7.5 $script:Muted $true 3)
}

function Add-Entity {
    param($Slide, [string]$Name, [string]$Fields,
          [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [int]$Accent = $script:Green, [double]$NameSize = 10.4,
          [double]$FieldSize = 8.6, [int]$Fill = $script:White)
    [void](Add-Rect $Slide $X $Y $Width $Height $Fill $Accent 4)
    [void](Add-Rect $Slide $X $Y $Width 26 $Accent $Accent 3)
    [void](Add-Text $Slide $Name ($X + 8) ($Y + 5) ($Width - 16) 16 $NameSize $script:White $true 2 3)
    [void](Add-Text $Slide $Fields ($X + 10) ($Y + 35) ($Width - 20) ($Height - 43) $FieldSize $script:Dark $false 1 1 "Consolas")
}

function Add-ProcessBox {
    param($Slide, [string]$Step, [string]$Title, [string]$Body,
          [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [int]$Accent, [int]$Fill)
    [void](Add-Rect $Slide $X $Y $Width $Height $Fill $Accent 7)
    [void](Add-Text $Slide $Step ($X + 10) ($Y + 9) 34 18 8.4 $Accent $true)
    [void](Add-Text $Slide $Title ($X + 10) ($Y + 29) ($Width - 20) 22 11.4 $script:Dark $true)
    [void](Add-Text $Slide $Body ($X + 10) ($Y + 57) ($Width - 20) ($Height - 67) 8.7 $script:Muted $false)
}

function Add-Tag {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$Width,
          [int]$Fill, [int]$Color)
    [void](Add-Rect $Slide $X $Y $Width 20 $Fill $Fill 7)
    [void](Add-Text $Slide $Text ($X + 6) ($Y + 2) ($Width - 12) 15 8.0 $Color $true 2 3)
}

$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Open($working, $false, $false, $false)

    # Add a dedicated ERD slide so every database domain remains readable.
    [void]$presentation.Slides.Add(22, 12)

    # Slide 20: native identity/chat/HITL ERD based on diagramv2/04.
    $s = $presentation.Slides.Item(20)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / ERD" "Identity, Conversation and HITL ERD - 7 Tables" 20

    # Two horizontal domains keep every entity wide enough for readable fields.
    [void](Add-Text $s "1. IDENTITY + USER FEEDBACK" 44 124 872 16 8.6 $script:Green $true)
    [void](Add-Rect $s 44 144 872 112 $script:SoftGreen $script:Line 8)
    [void](Add-Text $s "2. CONVERSATION + HUMAN-IN-THE-LOOP" 44 272 872 16 8.6 $script:Blue $true)
    [void](Add-Rect $s 44 292 872 194 $script:SoftBlue $script:Line 8)

    # Relationships first, so connectors terminate cleanly behind the cards.
    # APP_USER owns identity/feedback records through declared user_id keys.
    [void](Add-Line $s 270 199 350 199 $script:Green 1.9 $true)
    [void](Add-Line $s 165 242 165 250 $script:Green 1.7 $false)
    [void](Add-Line $s 165 250 782 250 $script:Green 1.7 $false)
    [void](Add-Line $s 782 250 782 242 $script:Green 1.9 $true)
    [void](Add-Text $s "1:1 identity" 282 180 62 14 7.4 $script:Green $true 2)
    [void](Add-Text $s "1:N feedback" 280 235 76 13 7.4 $script:Green $true 2)

    # APP_USER -> CONVERSATION; CONVERSATION -> messages and summary.
    [void](Add-Line $s 165 242 165 314 $script:Green 1.9 $true)
    [void](Add-Line $s 268 355 316 355 $script:Blue 1.9 $true)
    [void](Add-Line $s 163 314 163 304 $script:Blue 1.6 $false)
    [void](Add-Line $s 163 304 735 304 $script:Blue 1.6 $false)
    [void](Add-Line $s 735 304 735 314 $script:Blue 1.9 $true)
    [void](Add-Line $s 426 406 426 418 $script:Purple 1.8 $true)
    [void](Add-Line $s 735 406 735 418 $script:Purple 1.8 $true)

    Add-Entity $s "APP_USER" "PK id : uuid`nUK email | role | is_active" 60 158 210 84 $script:Green 10.8 9.0 $script:White
    Add-Entity $s "SSO_IDENTITY" "PK id | FK user_id`nUK issuer + subject | provider" 350 158 240 84 $script:Green 10.2 8.8 $script:White
    Add-Entity $s "USER_FEEDBACK" "PK id | FK user_id`nmessage_ciphertext | page | created_at" 665 158 235 84 $script:Gold 10.2 8.6 $script:White

    Add-Entity $s "CONVERSATION" "PK id | FK user_id`ntitle | status | retrieval_mode" 58 314 210 92 $script:Blue 10.4 8.8 $script:White
    Add-Entity $s "CHAT_MESSAGE" "PK id | FK conversation_id`nUK message_sequence`ncontent_ciphertext | sources | verification" 316 314 220 92 $script:Blue 9.8 8.8 $script:White
    Add-Entity $s "CONVERSATION_SUMMARY" "PK id | FK/UK conversation_id`nsummary_ciphertext | source_message_count`nvector(1024)" 580 314 310 92 $script:Purple 9.6 9.0 $script:White
    Add-Entity $s "CHAT_ANSWER_FEEDBACK" "PK id | UK message_id | FK user_id / conversation_id`nFK message_id | regenerated_message_id" 316 418 574 62 $script:Gold 9.4 8.8 $script:White

    [void](Add-Text $s "Solid arrows = declared SQL ownership / cardinality" 44 490 330 14 7.7 $script:Muted $false)
    [void](Add-Text $s "Source: diagramv2/04-postgres-erd-identity-chat.mmd" 650 490 266 14 7.5 $script:Muted $false 3)

    # Slide 21: two clean horizontal bands; all entity boxes share a fixed grid.
    $s = $presentation.Slides.Item(21)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / ERD" "Content and Legal Catalogue ERD - 6 Tables + 1 View" 21

    [void](Add-Text $s "1. USER-OWNED CONTENT" 44 126 872 16 8.7 $script:Green $true)
    [void](Add-Rect $s 44 148 872 116 $script:SoftGreen $script:Line 7)

    # Ownership bus: one APP_USER branches to three independent tables.
    [void](Add-Line $s 129 223 129 245 $script:Green 1.8 $false)
    [void](Add-Line $s 129 245 811 245 $script:Green 1.8 $false)
    [void](Add-Line $s 360 245 360 225 $script:Green 1.8 $true)
    [void](Add-Line $s 581 245 581 225 $script:Green 1.8 $true)
    [void](Add-Line $s 811 245 811 225 $script:Green 1.8 $true)
    [void](Add-Text $s "owns 1:N through declared foreign keys" 137 230 210 14 7.6 $script:Green $true)

    Add-Entity $s "APP_USER (FK anchor)" "PK id : uuid`nUK email" 58 157 142 66 $script:Green 8.8 7.7 $script:SoftGreen
    Add-Entity $s "ARTICLE" "PK id | FK author_id -> app_user`nslug | title | status" 265 157 190 68 $script:Green 9.8 7.6
    Add-Entity $s "ARTIFACT" "PK id | FK user_id -> app_user`nkind | metadata | status" 486 157 190 68 $script:Green 9.8 7.6
    Add-Entity $s "SIGNATURE_PACKET" "PK id | FK user_id -> app_user`nsigners | audit_log | status" 707 157 195 68 $script:Green 9.1 7.4

    [void](Add-Text $s "2. LEGAL CATALOGUE + SEMANTIC CACHE" 44 282 872 16 8.7 $script:Blue $true)
    [void](Add-Rect $s 44 304 872 181 $script:SoftBlue $script:Line 7)

    [void](Add-Line $s 274 365 320 365 $script:Blue 2 $true)
    [void](Add-Text $s "1:N chunks" 274 344 48 14 7.5 $script:Blue $true 2)
    [void](Add-Line $s 570 365 626 365 $script:Purple 1.8 $true $true)
    [void](Add-Text $s "contract" 574 344 48 14 7.3 $script:Purple $true 2)
    [void](Add-Line $s 445 420 445 430 $script:Teal 1.8 $true $true)

    Add-Entity $s "LEGAL_DOCUMENT" "PK id | UK external_doc_id / code`nstatus | current version`neffective_from / effective_to" 58 319 216 101 $script:Blue 9.8 8.1
    Add-Entity $s "LEGAL_CHUNK" "PK id | FK document_id -> legal_document`nUK external_chunk_id`nchunk_type | citation | vector(1024)" 320 319 250 101 $script:Blue 9.8 8.0
    Add-Entity $s "LEGAL_ANSWER_CACHE" "PK id | UK cache_scope_hash / query_hash`nquery vector(1024) | sources`nlaw_fingerprint | model/prompt version" 626 319 276 101 $script:Purple 9.2 8.0
    Add-Entity $s "LEGAL_CATALOG_CORPUS (MV)" "Derived current catalogue - not counted as a table" 320 430 250 53 $script:Teal 8.5 7.2 $script:SoftGreen

    [void](Add-Text $s "Source: diagramv2/05-postgres-erd-content-runtime.mmd" 650 487 266 14 7.5 $script:Muted $false 3)

    # Slide 22: GraphRAG and runtime tables, split from the content slide.
    $s = $presentation.Slides.Item(22)
    Clear-Slide $s
    Add-Chrome $s "DATABASE / ERD" "GraphRAG, Runtime and Migration ERD - 10 Tables" 22
    [void](Add-Text $s "GRAPHRAG PROJECTION + INDEX CONTROL (4)" 44 126 520 16 8.5 $script:Purple $true)
    [void](Add-Rect $s 44 145 520 335 $script:SoftPurple $script:Line 8)
    [void](Add-Text $s "RUNTIME + MIGRATION (6)" 585 126 331 16 8.5 $script:Gold $true)
    [void](Add-Rect $s 585 145 331 335 $script:SoftGold $script:Line 8)

    [void](Add-Line $s 168 257 168 296 $script:Purple 1.7 $true $true)
    [void](Add-Line $s 438 257 284 326 $script:Purple 1.7 $true $true)
    [void](Add-Line $s 289 356 309 356 $script:Purple 1.8 $true $true)
    [void](Add-Line $s 665 258 835 258 $script:Gold 1.8 $true)

    Add-Entity $s "GRAPHRAG_INDEX_METADATA" "PK index_name`nprovider | model | revision`ndimensions | status | chunk_count" 58 158 230 99 $script:Purple 8.9 7.7
    Add-Entity $s "GRAPHRAG_LAW_VERSION" "PK law_code_normalized`nlatest_version | updated_at" 309 158 241 99 $script:Purple 9.0 7.8
    Add-Entity $s "GRAPHRAG_CHUNK" "PK chunk_id`ndoc_id | node_id | chunk_type`nlaw_code | law_version`ntext | vector(1024)" 58 296 230 121 $script:Purple 9.6 7.8
    Add-Entity $s "GRAPHRAG_EMBEDDING_CHECKPOINT" "PK chunk_id`ncontent_sha256`nmodel | revision | dimensions`nserialized embedding" 309 296 241 121 $script:Purple 8.2 7.6
    [void](Add-Text $s "Dotted links are application identity/contract relationships, not SQL foreign keys." 62 438 484 28 8.0 $script:Muted $false 2)

    Add-Entity $s "KOMBU_QUEUE" "PK id`nUK name" 597 158 137 100 $script:Gold 9.2 8.0
    Add-Entity $s "KOMBU_MESSAGE" "PK id`nFK queue_id`nvisible | payload" 762 158 142 100 $script:Gold 8.8 7.7
    Add-Entity $s "CELERY_TASKMETA" "PK id`nUK task_id`nstatus | result" 597 276 137 92 $script:Gold 8.5 7.6
    Add-Entity $s "CELERY_TASKSETMETA" "PK id`nUK taskset_id`nresult | date_done" 762 276 142 92 $script:Gold 7.9 7.4
    Add-Entity $s "GUEST_RATE_LIMIT" "Composite PK`nsubject_hash`nwindow_kind | start" 597 386 137 82 $script:Gold 8.4 7.4
    Add-Entity $s "ALEMBIC_VERSION" "PK version_num`n20260803_0018" 762 386 142 82 $script:Muted 8.4 7.4 $script:SoftGray
    [void](Add-Text $s "Source: diagramv2/05 + diagramv2/23-cloud-sql-complete-schema.mmd" 590 486 326 14 7.5 $script:Muted $false 3)

    # Slide 32 after insertion: readable native data-processing and embedding flow.
    $s = $presentation.Slides.Item(32)
    Clear-Slide $s
    Add-Chrome $s "DATA PIPELINE / EMBEDDING" "From Legal Document to Validated 1,024-D Embeddings" 32

    $xs = @(44, 218, 392, 566, 740)
    for ($i=0; $i -lt 4; $i++) {
        [void](Add-Line $s ($xs[$i] + 154) 210 ($xs[$i+1] - 10) 210 $script:Green 2 $true)
    }
    Add-ProcessBox $s "01" "ACQUIRE" "DOC/DOCX + URL`nsource SHA-256" 44 143 154 133 $script:Green $script:SoftGreen
    Add-ProcessBox $s "02" "NORMALIZE + PARSE" "Ordered paragraphs/tables`nChapter > Article >`nClause > Point" 218 143 154 133 $script:Blue $script:SoftBlue
    Add-ProcessBox $s "03" "BUILD CHUNKS" "Structure-first units`n360-word windows`n70-word overlap`nstable chunk_id" 392 143 154 133 $script:Teal $script:SoftGreen
    Add-ProcessBox $s "04" "EMBED" "gemini-embedding-001`nRETRIEVAL_DOCUMENT`nRETRIEVAL_QUERY`noutput: 1,024-D" 566 143 154 133 $script:Purple $script:SoftPurple
    Add-ProcessBox $s "05" "VALIDATE" "dimension = 1,024`nfinite + non-zero`nL2-normalize`ncontract + SHA-256 match" 740 143 154 133 $script:Gold $script:SoftGold

    [void](Add-Text $s "ONE VERSIONED SNAPSHOT" 44 303 872 18 8.8 $script:Dark $true 2)
    [void](Add-Line $s 817 276 817 327 $script:Green 1.8 $true)
    [void](Add-Line $s 817 327 174 327 $script:Line 1.5 $false)
    [void](Add-Line $s 174 327 174 350 $script:Line 1.5 $true)
    [void](Add-Line $s 480 327 480 350 $script:Line 1.5 $true)
    [void](Add-Line $s 786 327 786 350 $script:Line 1.5 $true)

    Add-Entity $s "LOCAL SNAPSHOT" "SQLite + strict JSONL`ndocuments | nodes | edges | chunks" 64 350 220 84 $script:Gold 9.3 8.2 $script:SoftGold
    Add-Entity $s "CLOUD SQL" "FTS / BM25 + pgvector`nHNSW cosine + GIN lexical" 370 350 220 84 $script:Blue 9.5 8.2 $script:SoftBlue
    Add-Entity $s "NEO4J AURA" "LegalNode | LegalChunk`ntyped edges + CHUNK_OF" 676 350 220 84 $script:Green 9.5 8.2 $script:SoftGreen

    [void](Add-Rect $s 44 451 872 43 $script:SoftGreen $script:SoftGreen 7)
    [void](Add-Text $s "RECONCILE + ACTIVATE" 60 463 167 17 8.7 $script:Green $true)
    [void](Add-Text $s "Publish only when counts, hashes, dimensions, law versions and embedding contract match across all stores." 232 459 668 25 9.5 $script:Dark $true)
    [void](Add-Text $s "Source: diagramv2/11-legal-data-pipeline.mmd" 671 486 245 13 7.5 $script:Muted $false 3)

    # Slide 33 after insertion: readable synchronization and activation flow.
    $s = $presentation.Slides.Item(33)
    Clear-Slide $s
    Add-Chrome $s "DATA PIPELINE / INDEXING" "Index Synchronization: Prepare, Project, Reconcile, Activate" 33

    [void](Add-Text $s "1. PREPARE IDEMPOTENT SNAPSHOT" 44 126 872 16 8.6 $script:Gold $true)
    [void](Add-Line $s 286 181 348 181 $script:Green 2 $true)
    [void](Add-Line $s 612 181 674 181 $script:Green 2 $true)
    Add-Entity $s "CANONICAL LOCAL OUTPUT" "SQLite + documents/nodes/edges/chunks JSONL" 44 149 242 67 $script:Gold 9.2 8.0 $script:SoftGold
    Add-Entity $s "PREFLIGHT" "connectivity | model revision | 1,024 dimensions" 348 149 264 67 $script:Purple 9.5 8.0 $script:SoftPurple
    Add-Entity $s "IDEMPOTENT UPSERT" "stable IDs + corpus fingerprint + batched retry" 674 149 242 67 $script:Blue 9.2 8.0 $script:SoftBlue

    [void](Add-Text $s "2. SYNCHRONIZED PROJECTIONS" 44 239 872 16 8.6 $script:Blue $true)
    [void](Add-Line $s 795 216 795 252 $script:Green 1.8 $true)
    [void](Add-Line $s 795 252 174 252 $script:Line 1.5 $false)
    [void](Add-Line $s 174 252 174 266 $script:Line 1.5 $true)
    [void](Add-Line $s 480 252 480 266 $script:Line 1.5 $true)
    [void](Add-Line $s 786 252 786 266 $script:Line 1.5 $true)
    Add-Entity $s "CLOUD SQL / PGVECTOR" "graphrag_chunk vector(1024)`nHNSW cosine + GIN lexical`ncheckpoints + index metadata" 64 266 220 84 $script:Blue 8.7 7.8 $script:SoftBlue
    Add-Entity $s "LEGAL CATALOGUE" "current law version`nmaterialized catalogue view" 370 266 220 84 $script:Teal 9.2 8.0 $script:SoftGreen
    Add-Entity $s "NEO4J AURA" "typed nodes + relationships`nLegalChunk - CHUNK_OF -> LegalNode" 676 266 220 84 $script:Green 9.4 7.8 $script:SoftGreen

    [void](Add-Text $s "3. RECONCILE + CACHE DECISION" 44 371 872 16 8.6 $script:Purple $true)
    [void](Add-Entity $s "RECONCILIATION GATE" "counts | hashes | dimensions | representative reads" 44 396 264 70 $script:Purple 9.1 7.9 $script:SoftPurple)
    [void](Add-Line $s 308 431 358 431 $script:Purple 1.8 $true)
    [void](Add-Entity $s "FINGERPRINT COMPATIBLE?" "YES: retain cache    NO: invalidate cache" 358 396 264 70 $script:Purple 9.0 7.9 $script:SoftPurple)
    [void](Add-Line $s 622 431 672 431 $script:Green 1.8 $true)
    [void](Add-Entity $s "ACTIVATE SNAPSHOT" "fingerprint + reconciled counts + synchronized status" 672 396 244 70 $script:Green 9.3 7.9 $script:SoftGreen)

    [void](Add-Tag $s "HYBRID RRF" 44 478 102 $script:SoftBlue $script:Blue)
    [void](Add-Text $s "vector 0.55 | BM25 0.45 | K=60" 158 481 220 15 8.5 $script:Dark $true)
    [void](Add-Text $s "Source: diagramv2/12-index-synchronization.mmd" 650 482 266 14 7.5 $script:Muted $false 3)

    # Slide 41 after insertion: explicitly labelled illustrative data requested by the user.
    $s = $presentation.Slides.Item(41)
    Clear-Slide $s
    Add-Chrome $s "EVALUATION / ILLUSTRATIVE" "Illustrative Accuracy Snapshot - Complete Metric Coverage" 41
    [void](Add-Tag $s "ILLUSTRATIVE / MOCK DATA" 716 118 200 $script:SoftGold $script:Red)
    [void](Add-Text $s "MOCK METRIC SCORECARD (n = 100)" 44 126 520 16 8.7 $script:Purple $true)

    $mockMetrics = @(
        @{ Label = "Faithfulness";          Score = 0.91; Color = $script:Green },
        @{ Label = "Answer relevancy";      Score = 0.86; Color = $script:Green },
        @{ Label = "Context precision";     Score = 0.82; Color = $script:Blue },
        @{ Label = "Context recall";        Score = 0.80; Color = $script:Blue },
        @{ Label = "Factual correctness";   Score = 0.78; Color = $script:Purple },
        @{ Label = "Identifier recall";     Score = 0.74; Color = $script:Gold },
        @{ Label = "Identifier precision";  Score = 0.69; Color = $script:Gold },
        @{ Label = "Overall RAGAS";         Score = 0.80; Color = $script:Purple }
    )

    for ($i = 0; $i -lt $mockMetrics.Count; $i++) {
        $metric = $mockMetrics[$i]
        $y = 150 + ($i * 38)
        $rowFill = $(if (($i % 2) -eq 0) { $script:White } else { $script:SoftGray })
        [void](Add-Rect $s 44 $y 520 31 $rowFill $script:Line 4)
        [void](Add-Text $s $metric.Label 56 ($y + 7) 180 17 9.8 $script:Dark $true)
        [void](Add-Rect $s 245 ($y + 10) 236 10 $script:SoftGray $script:Line 5)
        [void](Add-Rect $s 245 ($y + 10) (236 * [double]$metric.Score) 10 $metric.Color $metric.Color 5)
        [void](Add-Text $s ("{0:N2}" -f [double]$metric.Score) 492 ($y + 5) 58 20 11.0 $metric.Color $true 3)
    }

    # Three presenter-friendly readouts on the right.
    [void](Add-Rect $s 590 150 326 86 $script:White $script:Line 5)
    [void](Add-Rect $s 590 150 7 86 $script:Purple $script:Purple 0)
    [void](Add-Text $s "0.80" 612 162 126 32 24 $script:Purple $true)
    [void](Add-Text $s "mock overall RAGAS" 612 199 250 20 11.2 $script:Dark $true)

    [void](Add-Rect $s 590 246 326 86 $script:White $script:Line 5)
    [void](Add-Rect $s 590 246 7 86 $script:Green $script:Green 0)
    [void](Add-Text $s "0.91" 612 258 126 32 24 $script:Green $true)
    [void](Add-Text $s "strongest: faithfulness" 612 295 250 20 11.2 $script:Dark $true)

    [void](Add-Rect $s 590 342 326 86 $script:White $script:Line 5)
    [void](Add-Rect $s 590 342 7 86 $script:Gold $script:Gold 0)
    [void](Add-Text $s "0.69" 612 354 126 32 24 $script:Gold $true)
    [void](Add-Text $s "watch item: identifier precision" 612 391 270 20 10.8 $script:Dark $true)

    [void](Add-Rect $s 590 438 326 24 $script:SoftBlue $script:SoftBlue 5)
    [void](Add-Text $s "Assumption: 100 complete benchmark rows" 602 443 302 14 8.2 $script:Blue $true 2)
    [void](Add-Rect $s 44 467 872 31 $script:SoftGold $script:Red 5)
    [void](Add-Text $s "ILLUSTRATIVE ONLY - replace with validated benchmark output before publication or thesis submission." 58 475 844 16 9.0 $script:Red $true 2)

    # Slide 25 after insertion: keep the final GraphRAG KPI on one line.
    # The legacy 27 pt value wrapped inside a 2.41 in card and collided with its label.
    $s = $presentation.Slides.Item(25)
    for ($shapeIndex = 1; $shapeIndex -le $s.Shapes.Count; $shapeIndex++) {
        $shape = $s.Shapes.Item($shapeIndex)
        try {
            if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                $text = $shape.TextFrame.TextRange.Text.Trim()
                if ($text -eq "29,575 / 108,368") {
                    $shape.Left = 731
                    $shape.Top = 426
                    $shape.Width = 174
                    $shape.Height = 26
                    $shape.TextFrame.AutoSize = 0
                    $shape.TextFrame.WordWrap = 0
                    $shape.TextFrame.MarginLeft = 0
                    $shape.TextFrame.MarginRight = 0
                    $shape.TextFrame.MarginTop = 0
                    $shape.TextFrame.MarginBottom = 0
                    $shape.TextFrame.TextRange.Font.Size = 20
                }
                elseif ($text -eq "nodes / edges") {
                    $shape.Top = 458
                    $shape.Height = 20
                }
            }
        } catch { }
    }

    # Refresh page numbers after the inserted slide.
    for ($i = 1; $i -le $presentation.Slides.Count; $i++) {
        $slide = $presentation.Slides.Item($i)
        for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
            $shape = $slide.Shapes.Item($shapeIndex)
            try {
                # Legacy page labels use TextFrame2; TextFrame.HasText is not
                # consistently exposed through COM and previously skipped them.
                if ($shape.HasTextFrame -eq -1 -and $shape.Left -gt 850 -and $shape.Width -lt 80) {
                    if ($shape.Top -lt 35 -or $shape.Top -gt 505) {
                        $shape.TextFrame2.TextRange.Text = ("{0:00}" -f $i)
                    }
                }
            } catch { }
        }
    }

    # A few legacy result slides use a full-slide raster background, so their
    # old page numbers are pixels rather than editable text. Mask and replace
    # both page labels after slide insertions.
    $legacyTopBand = 15464167  # RGB(231,246,235), sampled from the raster chrome
    $legacyFooter = 16317687   # RGB(247,252,248), sampled from the raster footer
    foreach ($page in @(29, 37, 38, 39)) {
        $slide = $presentation.Slides.Item($page)
        [void](Add-Rect $slide 870 4 54 25 $legacyTopBand $legacyTopBand 0)
        [void](Add-Text $slide ("{0:00}" -f $page) 878 10 42 16 8.6 $script:Muted $true 3)
        [void](Add-Rect $slide 870 514 54 20 $legacyFooter $legacyFooter 0)
        [void](Add-Text $slide ("{0:00}" -f $page) 886 518 30 12 7.5 $script:Muted $true 3)
    }

    $presentation.Save()
    $presentation.Close()
    $presentation = $null
    $ppt.Quit()
    $ppt = $null

    Copy-Item -LiteralPath $working -Destination $target -Force
    Write-Output "Updated $target"
    Write-Output "Slides: 46"
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
