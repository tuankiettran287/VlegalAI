param(
    [string]$OutputFile = "f:\VlegalAI\VlegalAI_Graduation_Defense.pptx"
)

$ErrorActionPreference = "Stop"

$script:W = 960.0
$script:H = 540.0

$script:Dark = 2962711       # #17352D
$script:Navy = 3813662       # #1E293B
$script:Muted = 6845019      # #6B716B
$script:Green = 5996296      # #087F5B
$script:Teal = 7773455       # #0F9D76
$script:Purple = 13068148    # #7467C7
$script:Gold = 1941718       # #D6A01D
$script:Red = 5917390        # #CE4A5A
$script:Blue = 13597455      # #0F7BCF
$script:Bg = 16317432        # #F8FBF8
$script:White = 16777215     # #FFFFFF
$script:Line = 14674651      # #DBEADF
$script:SoftGreen = 15529962 # #EAF7EA
$script:SoftBlue = 16643572  # #F4F5FD
$script:SoftGold = 14479100  # #FCEEDC
$script:SoftRed = 16050934   # #F6EAF4
$script:CardDark = 2302755   # #232323

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
    if ($Stroke -eq 0) {
        $shape.Line.Visible = 0
    } else {
        $shape.Line.Visible = -1
        $shape.Line.ForeColor.RGB = $Stroke
        $shape.Line.Weight = 1
    }
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
          [int]$Fill = $script:SoftGreen, [int]$Color = $script:Green, [double]$Height = 22, [double]$FontSize = 8.5)
    [void](Add-Rect $Slide $X $Y $Width $Height $Fill 0 8)
    [void](Add-Text $Slide $Text ($X + 4) ($Y + 1) ($Width - 8) ($Height - 2) $FontSize $Color $true 2 3)
}

function Add-Card {
    param($Slide, [string]$Title, [string]$Body, [double]$X, [double]$Y,
          [double]$Width, [double]$Height, [int]$Accent = $script:Green,
          [int]$Fill = $script:White, [double]$BodySize = 10, [double]$TitleSize = 12)
    [void](Add-Rect $Slide $X $Y $Width $Height $Fill $script:Line 8)
    [void](Add-Rect $Slide $X $Y 5 $Height $Accent $Accent 0)
    [void](Add-Text $Slide $Title ($X + 14) ($Y + 10) ($Width - 24) 22 $TitleSize $script:Dark $true)
    [void](Add-Text $Slide $Body ($X + 14) ($Y + 34) ($Width - 24) ($Height - 42) $BodySize $script:Muted $false)
}

function Add-Stat {
    param($Slide, [string]$Value, [string]$Label, [double]$X, [double]$Y,
          [double]$Width, [int]$Accent = $script:Green, [double]$Height = 66)
    [void](Add-Rect $Slide $X $Y $Width $Height $script:White $script:Line 8)
    [void](Add-Text $Slide $Value ($X + 8) ($Y + 6) ($Width - 16) 28 18 $Accent $true 2 3)
    [void](Add-Text $Slide $Label ($X + 6) ($Y + 36) ($Width - 12) 22 8.3 $script:Muted $true 2 3)
}

function Add-Chrome {
    param($Slide, [string]$Section, [string]$Title, [int]$Page, [int]$TotalPages = 20)
    [void](Add-Rect $Slide 0 0 $script:W $script:H $script:Bg $script:Bg 0)
    [void](Add-Rect $Slide 0 0 $script:W 32 $script:SoftGreen $script:SoftGreen 0)
    [void](Add-Text $Slide ("VLEGALAI | " + $Section.ToUpper()) 44 8 400 16 8.5 $script:Green $true)
    [void](Add-Text $Slide ("{0:00} / {1:00}" -f $Page, $TotalPages) 850 8 66 16 8.5 $script:Muted $true 3)
    [void](Add-Text $Slide $Title 44 44 872 40 20 $script:Dark $true)
    [void](Add-Rect $Slide 44 94 72 3.5 $script:Green $script:Green 0)
    [void](Add-Line $Slide 116 96 916 96 $script:Line 1 $false)
    [void](Add-Line $Slide 44 510 916 510 $script:Line 1 $false)
    [void](Add-Text $Slide "VlegalAI: Vietnamese Labor Law GraphRAG and AI Assistant | Capstone Defense" 44 516 450 14 7.5 $script:Muted $false)
    [void](Add-Text $Slide ("Trang {0:00}" -f $Page) 860 516 56 14 7.5 $script:Muted $true 3)
}

$ppt = $null
$presentation = $null

try {
    Write-Host "Creating PowerPoint Application..."
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Add([Microsoft.Office.Core.MsoTriState]::msoTrue)
    $presentation.PageSetup.SlideWidth = $script:W
    $presentation.PageSetup.SlideHeight = $script:H

    $blankLayout = 12

    # Slide 1: Cover
    $s1 = $presentation.Slides.Add(1, $blankLayout)
    [void](Add-Rect $s1 0 0 $script:W $script:H $script:Dark $script:Dark 0)
    [void](Add-Rect $s1 0 0 12 $script:H $script:Green $script:Green 0)
    [void](Add-Pill $s1 "HOI DONG BAO VE DO AN TOT NGHIEP - KHOA 2026" 56 50 360 $script:Green $script:White 26 9.5)
    [void](Add-Text $s1 "VLEGALAI" 56 95 800 50 36 $script:White $true 1 1 "Segoe UI")
    [void](Add-Text $s1 "He thong Tro ly Phap ly Lao dong Viet Nam Ung dung GraphRAG va Large Language Models" 56 150 820 54 18 $script:SoftGreen $true 1 1 "Segoe UI")
    [void](Add-Line $s1 56 215 880 215 $script:Green 2 $false)

    [void](Add-Rect $s1 56 240 400 160 $script:CardDark 0 8)
    [void](Add-Text $s1 "SINH VIEN THUC HIEN:" 76 255 360 20 10 $script:Teal $true)
    $svText = "- Tran Tuan Kiet (Leader) - QE180152" + [Environment]::NewLine + "- Le Thanh Dat - QE170186" + [Environment]::NewLine + "- Phan Bao Khanh - DE170648"
    [void](Add-Text $s1 $svText 76 280 360 100 11.5 $script:White $false)

    [void](Add-Rect $s1 480 240 400 160 $script:CardDark 0 8)
    [void](Add-Text $s1 "GIANG VIEN HUONG DAN:" 500 255 360 20 10 $script:Gold $true)
    $gvText = "- GVHD: ThS. Le Trung Hieu" + [Environment]::NewLine + "- Dong GVHD: ThS. Truong Ngoc Hung" + [Environment]::NewLine + "- Ma de tai: AIP491 - FPT University"
    [void](Add-Text $s1 $gvText 500 280 360 100 11.5 $script:White $false)
    [void](Add-Text $s1 "Thang 08 / 2026 | Chuyen nganh Tri tue Nhan tao (AI)" 56 460 820 20 10 $script:Muted $false 2)

    # Slide 2: Overview & Problem
    $s2 = $presentation.Slides.Add(2, $blankLayout)
    Add-Chrome $s2 "TONG QUAN" "Boi canh Thuc tien va Thach thuc trong Tra cuu Phap luat Lao dong" 2
    $p1 = "- Cau truc phan cap nghiem ngat: Van ban > Chuong > Muc > Dieu > Khoan > Diem." + [Environment]::NewLine + "- Ton tai nhieu dieu kien loai tru, dan chieu cheo phuc tap giua cac van ban." + [Environment]::NewLine + "- Thuong xuyen thay doi/sua doi hieu luc (Nghi dinh moi thay the Nghi dinh cu)."
    Add-Card $s2 "Thach thuc Phap luat Viet Nam" $p1 44 115 420 160 $script:Red $script:White 10

    $p2 = "- Ao giac (Hallucination): Bia dat so dieu luat, muc phat khong co thuc." + [Environment]::NewLine + "- Thieu can cu dan chung: Khong the chung minh nguon goc chinh xac." + [Environment]::NewLine + "- Khong cap nhat kip thoi: Tri thuc dong bang trong trong so mo hinh."
    Add-Card $s2 "Han che cua LLM Truyen thong" $p2 484 115 432 160 $script:Gold $script:White 10

    $p3 = "Xay dung he thong Tro ly Phap ly chuyen sau cho Luat Lao dong Viet Nam ket hop Do thi Tri thuc (Legal Knowledge Graph) va Hybrid RAG (pgvector + BM25 + Neo4j):" + [Environment]::NewLine + "[*] Dam bao 100% cau tra loi co trich dan dieu khoan chinh xac, co the kiem chung (Grounding & Provenance)." + [Environment]::NewLine + "[*] Phan luong cau hoi thich ung (Adaptive Routing) giup toi uu ca do chinh xac lan toc do phan hoi."
    Add-Card $s2 "Muc tieu & Giai phap cua VlegalAI" $p3 44 290 872 135 $script:Green $script:SoftGreen 10.5
    [void](Add-Pill $s2 "PHAM VI: 74 VAN BAN QUY PHAM PHAP LUAT LAO DONG" 44 445 360 $script:SoftBlue $script:Blue)
    [void](Add-Pill $s2 "100% CO CAN CU TRICH DAN DIEU KHOAN" 420 445 320 $script:SoftGreen $script:Green)

    # Slide 3: Architecture
    $s3 = $presentation.Slides.Add(3, $blankLayout)
    Add-Chrome $s3 "KIEN TRUC HE THONG" "Kien truc 4 Tang Toan dien cua VlegalAI" 3
    $archs = @(
        @{T="1. TANG TRAI NGHIEM (UI/UX)"; B="- React 18 + Vite SPA" + [Environment]::NewLine + "- Markdown rendering + S1-Sn Citations" + [Environment]::NewLine + "- Chat da phien, upload hop dong/OCR" + [Environment]::NewLine + "- Human-in-the-Loop (HITL) rating"; C=$script:Green; X=44},
        @{T="2. TANG DICH VU (API/GATEWAY)"; B="- FastAPI + Gunicorn async serving" + [Environment]::NewLine + "- OAuth Google OIDC + PKCE" + [Environment]::NewLine + "- Routing Policy & Facet Planning" + [Environment]::NewLine + "- Evidence Gating & Citation Validator"; C=$script:Teal; X=268},
        @{T="3. TANG LUU TRU (STORAGE)"; B="- Cloud SQL PostgreSQL 18 (23 tables)" + [Environment]::NewLine + "- pgvector HNSW (vector 1,024D)" + [Environment]::NewLine + "- Neo4j Knowledge Graph (30k nodes)" + [Environment]::NewLine + "- Local SQLite + FTS5 fulltext"; C=$script:Blue; X=492},
        @{T="4. TANG AI & KNOWLEDGE"; B="- Vertex AI Gemini 2.5 Flash (LLM)" + [Environment]::NewLine + "- gemini-embedding-001 (Embeddings)" + [Environment]::NewLine + "- 10-Layer Legal Knowledge Graph" + [Environment]::NewLine + "- Hybrid RRF (Vector 0.55 + BM25 0.45)"; C=$script:Purple; X=716}
    )
    foreach ($a in $archs) {
        [void](Add-Rect $s3 $a.X 118 208 300 $script:White $script:Line 8)
        [void](Add-Rect $s3 $a.X 118 208 6 $a.C $a.C 0)
        [void](Add-Text $s3 $a.T ($a.X + 10) 130 188 36 10.5 $a.C $true)
        [void](Add-Text $s3 $a.B ($a.X + 10) 175 188 230 9.5 $script:Dark $false)
    }
    [void](Add-Rect $s3 44 435 880 55 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s3 "Diem cot loi" 60 445 100 18 10 $script:Green $true)
    [void](Add-Text $s3 "Kien truc phan tach ro rang giua Tang suy luan (LLM co dinh trong so) va Tang tri thuc phap ly (Vector + Do thi co the cap nhat dong theo thoi gian thuc)." 160 443 740 38 10 $script:Dark $false)

    # Slide 4: Parsing Method & Document Structure
    $s4 = $presentation.Slides.Add(4, $blankLayout)
    Add-Chrome $s4 "XU LY DU LIEU" "Cau truc Document khi Parsing va Phuong phap Tat dinh (Deterministic Parsing)" 4
    $p4_1 = "- Dung LLM de parse de bi mat dong, ao giac so dieu khoan va khong dong nhat." + [Environment]::NewLine + "- VlegalAI dung State Machine + Regular Expressions phap ly Viet Nam." + [Environment]::NewLine + "- Trang thai Parser: sigma_i = (d, c_i, s_i, a_i, q_i, p_i) tuong ung Document > Chapter > Section > Article > Clause > Point."
    Add-Card $s4 "1. Tai sao Parsing Tat dinh (Khong dung LLM)?" $p4_1 44 115 420 180 $script:Green $script:White 9.5

    $p4_2 = "- Chuong: ^Chuong\s+([IVXLCDM]+|\d+)" + [Environment]::NewLine + "- Muc: ^Muc\s+([IVXLCDM]+|\d+)" + [Environment]::NewLine + "- Dieu: ^Dieu\s+(\d+[a-zA-Z]?)\s*[\.:]\s*(.+)" + [Environment]::NewLine + "- Khoan: ^(\d{1,3})\.\s+(.+)" + [Environment]::NewLine + "- Diem: ^([a-zdd](?:\d+)?)\)\s+(.+)" + [Environment]::NewLine + "- Bang bieu (Table): Giu nguyen vi tri duoi dieu khoan chua no."
    Add-Card $s4 "2. Quy chuan Header Regex Phap ly" $p4_2 484 115 432 180 $script:Blue $script:White 9.2

    [void](Add-Rect $s4 44 310 872 170 $script:White $script:Line 8)
    [void](Add-Text $s4 "Cau truc Document Envelope Output khi Parsing (JSON Schema 1.0):" 60 322 840 20 11 $script:Dark $true)
    $envs = @(
        @{T="source"; D="path, filename, size_bytes, sha256 (Khoa dinh danh bat bien)"; X=60; W=195; C=$script:Teal},
        @{T="document"; D="doc_id, title, code (45/2019/QH14), doc_type, issuer, text"; X=270; W=200; C=$script:Green},
        @{T="nodes[]"; D="node_id, label, parent_id, path_label, text, ordinal, child_count"; X=485; W=205; C=$script:Purple},
        @{T="edges[] & chunks[]"; D="edge_id, relation, evidence | chunk_id, citation, token_count"; X=705; W=195; C=$script:Gold}
    )
    foreach ($e in $envs) {
        [void](Add-Rect $s4 $e.X 350 $e.W 115 $script:Bg $script:Line 6)
        [void](Add-Text $s4 $e.T ($e.X + 8) 358 ($e.W - 16) 18 10.5 $e.C $true)
        [void](Add-Text $s4 $e.D ($e.X + 8) 382 ($e.W - 16) 75 9 $script:Muted $false)
    }

    # Slide 5: Parsing Example
    $s5 = $presentation.Slides.Add(5, $blankLayout)
    Add-Chrome $s5 "XU LY DU LIEU" "Minh chung Ket qua Parsing: Bo Luat Lao Dong 45/2019/QH14" 5
    Add-Stat $s5 "1" "VAN BAN GOC" 44 115 130 $script:Green
    Add-Stat $s5 "1,175" "NODES DO THI" 186 115 140 $script:Teal
    Add-Stat $s5 "2,347" "EDGES QUAN HE" 338 115 140 $script:Purple
    Add-Stat $s5 "1,187" "CHUNKS TRUY HOI" 490 115 150 $script:Blue
    Add-Stat $s5 "3.85 MiB" "JSON SERIALIZED" 652 115 130 $script:Gold
    Add-Stat $s5 "0" "EMBEDDINGS (Parser-Only)" 794 115 122 $script:Red

    $p5_1 = "- 1 Document, 1 Co quan ban hanh (Quoc hoi)." + [Environment]::NewLine + "- 17 Chuong, 24 Muc, 220 Dieu, 640 Khoan, 272 Diem." + [Environment]::NewLine + "- 2,347 Edges quan he cap bac va dan chieu co huong (CO_DIEU, CO_KHOAN, CO_DIEM, THUOC_VE...)."
    Add-Card $s5 "Chi tiet Phan ra Node & Edge" $p5_1 44 195 420 180 $script:Teal $script:White 10

    $p5_2 = "- Document: slug(filename_stem)" + [Environment]::NewLine + "- Dieu: dieu:bo-luat-45-2019-qh14:91" + [Environment]::NewLine + "- Khoan: khoan:bo-luat-45-2019-qh14:91:1" + [Environment]::NewLine + "- Diem: diem:bo-luat-45-2019-qh14:91:1:a" + [Environment]::NewLine + "-> Cho phep join tat dinh giua SQLite, PostgreSQL, Neo4j va Citation UI."
    Add-Card $s5 "Quy tac Sinh Dinh danh Bat bien (Stable IDs)" $p5_2 484 195 432 180 $script:Purple $script:White 10

    [void](Add-Rect $s5 44 390 872 85 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s5 "Vi du Cu the voi Dieu 91 (Muc luong toi thieu):" 60 398 400 18 10.5 $script:Green $true)
    $p5_3 = "- Node Dieu: dieu:bo-luat-45-2019-qh14:91 (Chuong VI, 4 khoan truc thuoc)." + [Environment]::NewLine + "- Node Khoan 1: khoan:bo-luat-45-2019-qh14:91:1 (Parent: Dieu 91, Path: Bo Luat Lao Dong > Chuong VI > Dieu 91 > Khoan 1)." + [Environment]::NewLine + "- Citation hoan chinh: 'Bo Luat Lao Dong 2019, Dieu 91, Khoan 1'."
    [void](Add-Text $s5 $p5_3 60 420 840 50 9.5 $script:Dark $false)

    # Slide 6: Chunking Strategy
    $s6 = $presentation.Slides.Add(6, $blankLayout)
    Add-Chrome $s6 "CHUNKING & INDEXING" "Chien luoc Chunking Phan cap (Hierarchy-Aware Chunking) va 9 Loai Chunks" 6
    $p6_1 = "- VlegalAI KHONG cat van ban theo so ky tu co dinh hay token thong thuong (tranh viec 1 cau bi cat doi, mat chu the hoac mat dieu kien ngoai le)." + [Environment]::NewLine + "- Ranh gioi phan doan dau tien la Don vi Cau truc Phap ly (Legal Unit): Moi Khoan, Diem hoac Dieu luat tu nhien tao thanh mot Retrieval Chunk doc lap." + [Environment]::NewLine + "- Moi chunk luon gan lien voi ma dinh danh node (node_id) va duong dan phan cap (path_label) de phuc vu trich dan chinh xac."
    Add-Card $s6 "Nguyen ly Phan doan theo Cau truc Phap ly" $p6_1 44 115 420 185 $script:Green $script:White 9.5

    [void](Add-Rect $s6 484 115 432 365 $script:White $script:Line 8)
    [void](Add-Text $s6 "Bang phan loai 9 loai Chunk trong He thong:" 500 125 400 20 10.5 $script:Dark $true)
    $ctypes = @(
        @{T="article"; D="Toan van Dieu luat (dung cho tra cuu muc dieu & trich dan)"; C=$script:Green},
        @{T="clause"; D="Noi dung Khoan (don vi chua quyen, nghia vu, dieu kien)"; C=$script:Teal},
        @{T="point"; D="Noi dung Diem (quy dinh chi tiet, danh sach hanh vi vi pham)"; C=$script:Blue},
        @{T="table"; D="Bang luong toi thieu vung, phu cap, he so, ty le dong"; C=$script:Purple},
        @{T="structure"; D="Tieu de & pham vi Chuong/Muc (phuc vu cau hoi bao quat)"; C=$script:Gold},
        @{T="document_intro"; D="Loi mo dau, can cu phap ly, pham vi dieu chinh van ban"; C=$script:Muted},
        @{T="semantic"; D="Node Ontology (thuat ngu, chu the, quy trinh, muc phat)"; C=$script:Red},
        @{T="sliding"; D="Cua so truot bo tro cho cac dieu khoan dai vuot nguong"; C=$script:Dark},
        @{T="document_structure"; D="Thong ke so luong chuong/dieu/khoan cua van ban"; C=$script:Green}
    )
    $cy = 150
    foreach ($ct in $ctypes) {
        [void](Add-Pill $s6 $ct.T 500 $cy 110 $script:Bg $ct.C 19 8)
        [void](Add-Text $s6 $ct.D 618 ($cy + 1) 285 18 8.2 $script:Muted $false)
        $cy += 23
    }
    $p6_2 = "- Giu tron ven ngu canh phap ly va chu the thuc hien." + [Environment]::NewLine + "- Khac phuc triet de loi phan doan lam dut gay quan he phap luat." + [Environment]::NewLine + "- San sang trich dan truc tiep S1-Sn den tung Dieu/Khoan/Diem."
    Add-Card $s6 "Loi ich cot loi" $p6_2 44 315 420 165 $script:Blue $script:SoftGreen 9.8

    # Slide 7: String Splitting & Sliding Window
    $s7 = $presentation.Slides.Add(7, $blankLayout)
    Add-Chrome $s7 "CHUNKING & CAT CHUOI" "Co che Cat Chuoi (String Splitting) va Cua so Truot (Sliding Window Fallback)" 7
    Add-Stat $s7 "W = 360" "DO DAI CUA SO (TU)" 44 115 190 $script:Green
    Add-Stat $s7 "O = 70" "DO GOI DAU OVERLAP" 250 115 190 $script:Teal
    Add-Stat $s7 "Delta = 290" "BUOC NHAY STRIDE" 456 115 190 $script:Purple
    Add-Stat $s7 "N <= 440" "NGUONG GIU NGUYEN 1 CHUNK" 662 115 254 $script:Gold

    $p7_1 = "- Su dung bieu thuc chinh quy tieng Viet: T = [0-9A-Za-zA-yDd]+" + [Environment]::NewLine + "- Dem so tu: N(x) = len(VN_WORD_RE.findall(text))" + [Environment]::NewLine + "- Khong bi anh huong boi loi cat roi ky tu co dau (UTF-8 multi-byte)."
    Add-Card $s7 "1. Bo dem Token Tieng Viet Chuan" $p7_1 44 195 420 135 $script:Green $script:White 9.5

    $p7_2 = "- Neu N(x) <= 440 tu: Giu nguyen 1 chunk duy nhat." + [Environment]::NewLine + "- Neu N(x) > 440 tu: Tao cac cua so truot: C_j = x[j*Delta : j*Delta + W] voi buoc nhay Delta = max(80, W - O) = 290 tu." + [Environment]::NewLine + "- Ty le overlap danh dinh: rho = 70 / 360 = 19.44%."
    Add-Card $s7 "2. Thuat toan Cua so Truot (legal_graphrag.py)" $p7_2 484 195 432 135 $script:Blue $script:White 9.5

    [void](Add-Rect $s7 44 345 872 135 $script:White $script:Line 8)
    [void](Add-Text $s7 "3. Quy tac Kiem soat Bien va Loai bo Nhieu (Edge Cases Control):" 60 355 840 20 11 $script:Dark $true)
    $p7_3 = "- Cua so dau tien giu loai cau truc goc (article, clause, point, table...); cac cua so tiep theo duoc gan nhan 'sliding'." + [Environment]::NewLine + "- Phan duoi cuoi cung neu co so tu < 80 tu se bi huy bo (khong tao chunk vun)." + [Environment]::NewLine + "- Loai bo toan bo cac doan van ban co do dai < 4 token phap ly (loai bo tieu de rac, duong phan cach)."
    [void](Add-Text $s7 $p7_3 60 380 840 50 9.5 $script:Dark $false)
    [void](Add-Pill $s7 "CONG THUC: X_c = title(c) + '\n' + path(c) + '\n' + text(c)" 60 440 450 $script:SoftGreen $script:Green)
    [void](Add-Pill $s7 "CHUNK NGAN VAN MANG DAY DU NGU CANH DIEU LUAT" 520 440 380 $script:SoftBlue $script:Blue)

    # Slide 8: Data Processing & Vector Embedding
    $s8 = $presentation.Slides.Add(8, $blankLayout)
    Add-Chrome $s8 "VECTOR EMBEDDING" "Quy trinh Xu ly Du lieu, Vector Embedding va Co che Caching" 8
    $p8_1 = "Moi Chunk duoc dong goi theo hop dong van ban nghiem ngat:" + [Environment]::NewLine + "  X_c = title(c) || '\n' || path(c) || '\n' || text(c)" + [Environment]::NewLine + "Vi du:" + [Environment]::NewLine + "  'Muc luong toi thieu'" + [Environment]::NewLine + "  'Bo Luat Lao Dong (45/2019/QH14) > Chuong VI > Dieu 91 > Khoan 1'" + [Environment]::NewLine + "  '1. Muc luong toi thieu la muc luong thap nhat duoc tra...'"
    Add-Card $s8 "1. Chuan hoa Chuoi dau vao Embedding" $p8_1 44 115 420 180 $script:Green $script:White 9.2

    $p8_2 = "- Model: Vertex AI gemini-embedding-001" + [Environment]::NewLine + "- Chieu khong gian: m = 1,024 chieu (float32)." + [Environment]::NewLine + "- Task Type chuyen biet:" + [Environment]::NewLine + "  + Du lieu van ban (Chunks): RETRIEVAL_DOCUMENT" + [Environment]::NewLine + "  + Cau hoi nguoi dung (Queries): RETRIEVAL_QUERY" + [Environment]::NewLine + "- Chuan hoa L2: e(x) = z(x) / ||z(x)||_2." + [Environment]::NewLine + "- Khoang cach Cosine tren pgvector: d_cos = 1 - e(q)^T * e(c)."
    Add-Card $s8 "2. Embedding Model & Task Type" $p8_2 484 115 432 180 $script:Blue $script:White 9.2

    $p8_3 = "- Moi vector float32 1024D = 4,096 bytes/chunk." + [Environment]::NewLine + "- Tong 32,334 chunks xap xi 126.3 MiB raw vector." + [Environment]::NewLine + "- Checkpoint theo batch (640 chunks/batch) vao PostgreSQL: Quota timeout co the resume lai ngay lap tuc ma khong tinh toan lai tu dau."
    Add-Card $s8 "3. Quan ly Dung luong & Checkpoint Batch" $p8_3 44 310 420 165 $script:Purple $script:White 9.5

    $p8_4 = "- Hash noi dung: h_c = SHA256(X_c)." + [Environment]::NewLine + "- Vector chi duoc tai su dung khi khop toan bo 7 yeu to: chunk_id + h_c + provider + model + revision + task_type + dimension (1024)." + [Environment]::NewLine + "- Bat ky sua doi nao trong van ban luat se kich hoat tinh lai vector tu dong."
    Add-Card $s8 "4. Caching theo Content Hash (SHA-256)" $p8_4 484 115 432 165 $script:Gold $script:White 9.5

    # Slide 9: Multi-Store Indexing
    $s9 = $presentation.Slides.Add(9, $blankLayout)
    Add-Chrome $s9 "INDEXING DA TANG" "He thong Indexing Da Tang Dong bo (PostgreSQL, pgvector, Neo4j, SQLite)" 9
    $stores = @(
        @{T="1. PGVECTOR (HNSW)"; D="- Cot vector(1024) trong bang graphrag_chunk." + [Environment]::NewLine + "- Thuat toan HNSW do thi tiem can phan tang:" + [Environment]::NewLine + "  + vector_cosine_ops" + [Environment]::NewLine + "  + M = 16, ef_construction = 64" + [Environment]::NewLine + "- Truy hoi tuong dong ngu nghia cuc nhanh."; C=$script:Blue; X=44; W=274},
        @{T="2. POSTGRESQL (GIN FTS)"; D="- Cot generated tsvector tren [title, citation, text]." + [Environment]::NewLine + "- GIN Index phuc vu tim kiem tu khoa chinh xac." + [Environment]::NewLine + "- Khop so hieu van ban (45/2019/QH14), so dieu luat, thuat ngu, muc tien te."; C=$script:Green; X=343; W=274},
        @{T="3. NEO4J GRAPH INDEX"; D="- 29,575 nodes & 108,368 edges." + [Environment]::NewLine + "- Unique Constraint tren LegalChunk(chunk_id)." + [Environment]::NewLine + "- Fulltext Index tren [title, citation, text]." + [Environment]::NewLine + "- Mo rong 2-hop theo cac quan he phap ly."; C=$script:Purple; X=642; W=274}
    )
    foreach ($st in $stores) {
        [void](Add-Rect $s9 $st.X 115 $st.W 200 $script:White $script:Line 8)
        [void](Add-Rect $s9 $st.X 115 $st.W 6 $st.C $st.C 0)
        [void](Add-Text $s9 $st.T ($st.X + 12) 128 ($st.W - 24) 22 11 $st.C $true)
        [void](Add-Text $s9 $st.D ($st.X + 12) 155 ($st.W - 24) 150 9.5 $script:Dark $false)
    }

    [void](Add-Rect $s9 44 330 872 145 $script:SoftGreen $script:SoftGreen 8)
    [void](Add-Text $s9 "Hop nhat Thu hang RRF (Reciprocal Rank Fusion) tai Query Time:" 60 342 840 20 11.5 $script:Green $true)
    $p9_r = "- Ket hop diem so Vector va BM25 bang cong thuc Weighted RRF (K = 60):" + [Environment]::NewLine + "  S_RRF(c) = w_v * (K + 1) / (K + r_v(c)) + w_b * (K + 1) / (K + r_b(c)) voi trong so w_v = 0.55 (Vector) va w_b = 0.45 (BM25)." + [Environment]::NewLine + "- Dieu chinh diem so co so theo muc do bao phu tu khoa: S_0(c) = S_RRF(c) / (r_f(c)^0.35) + 0.9 * m_c / min(|T_q|, 10) + B(c, q)."
    [void](Add-Text $s9 $p9_r 60 368 840 60 9.5 $script:Dark $false)
    [void](Add-Pill $s9 "ATOMIC ACTIVATION: CHI KICH HOAT KHI TONG SO LUONG CHUNKS VA HASH DONG BO 100% GIUA CAC DB" 60 435 780 $script:White $script:Green)

    # Slide 10: LLM Training vs RAG
    $s10 = $presentation.Slides.Add(10, $blankLayout)
    Add-Chrome $s10 "CHIEN LUOC MO HINH" "Co Train / Fine-Tune LLM hay khong? Quyet dinh Ky thuat Cot loi (ADR-04)" 10
    [void](Add-Rect $s10 44 115 220 360 $script:Dark $script:Dark 8)
    [void](Add-Text $s10 "KHONG" 44 140 220 50 36 $script:Red $true 2 3)
    [void](Add-Text $s10 "Fine-tune hay Train lai Trong so LLM" 54 195 200 30 12 $script:White $true 2 3)
    [void](Add-Line $s10 64 235 244 235 $script:Green 2 $false)
    $p10_no = "- Khong Pretraining" + [Environment]::NewLine + "- Khong SFT" + [Environment]::NewLine + "- Khong LoRA / QLoRA" + [Environment]::NewLine + "- Trong so mo hinh giu co dinh: theta' = theta"
    [void](Add-Text $s10 $p10_no 64 250 180 180 10.5 $script:White $false 1)

    $reasons = @(
        @{T="1. Kha nang Dan chung & Nguon goc (Provenance)"; D="LLM fine-tuned luu kien thuc vao 'hop den' trong so, khong the bao dam trich dan chinh xac tuyet doi tung Dieu/Khoan. RAG giu nguyen ven chuoi bang chung: Answer > Evidence > Chunk > Provision > Instrument."; C=$script:Green; X=280; Y=115; W=305; H=170},
        @{T="2. Tinh Cap nhat & Luat Het hieu luc (Freshness)"; D="Phap luat thay doi lien tuc (Nghi dinh moi thay the cu). Neu fine-tune, moi lan doi luat phai thu thap du lieu & train lai rat ton kem va de lan lon. Voi GraphRAG, chi can re-index lai DB trong vai phut."; C=$script:Blue; X=605; Y=115; W=311; H=170},
        @{T="3. Kiem soat Ao giac (Hallucination Control)"; D="Linh vuc phap ly doi hoi su chinh xac tuyet doi. Viec ep mo hinh chi sinh cau tra loi dua tren tap bang chung duoc truy hoi (Evidence-first prompt contract) giup triet tieu hoan toan nguy co bia dat so dieu luat."; C=$script:Purple; X=280; Y=300; W=305; H=175},
        @{T="4. Mo hinh Su dung Thuc te (Hosted LLM)"; D="Su dung Google Gemini 2.5 Flash qua Vertex AI. Toi uu hoa tap trung vao: Cau truc do thi tri thuc, Chien luoc Chunking, Hybrid RRF, Prompt Engineering va Bo loc Kiem chung Trich dan (Evidence Gate)."; C=$script:Gold; X=605; Y=300; W=311; H=175}
    )
    foreach ($r in $reasons) {
        [void](Add-Rect $s10 $r.X $r.Y $r.W $r.H $script:White $script:Line 8)
        [void](Add-Rect $s10 $r.X $r.Y 5 $r.H $r.C $r.C 0)
        [void](Add-Text $s10 $r.T ($r.X + 12) ($r.Y + 8) ($r.W - 20) 36 10 $r.C $true)
        [void](Add-Text $s10 $r.D ($r.X + 12) ($r.Y + 44) ($r.W - 20) ($r.H - 50) 8.8 $script:Dark $false)
    }

    # Slide 11: 10-Layer Legal KG
    $s11 = $presentation.Slides.Add(11, $blankLayout)
    Add-Chrome $s11 "KNOWLEDGE GRAPH" "Kien truc Do thi Tri thuc Phap ly 10 Tang (10-Layer Legal Ontology)" 11
    $layers = @(
        @{L="L0"; N="Nguon & Hieu luc"; D="Van ban goc, co quan ban hanh, ngay hieu luc, quan he sua doi/thay the"; C=$script:Green},
        @{L="L1"; N="Cau truc Van ban"; D="Chuong > Muc > Dieu > Khoan > Diem, quan he HAS_PART, dan chieu cheo"; C=$script:Teal},
        @{L="L2"; N="Thuat ngu & Chu de"; D="Dinh nghia phap ly tu dong, ban do chu de dinh huong toan bo corpus"; C=$script:Blue},
        @{L="L3"; N="Tien luong & Thuong"; D="Khoan thu nhap, ky han tra luong, luong toi thieu vung, cong thuc tinh, ty le %"; C=$script:Purple},
        @{L="L4"; N="Chu the & Quan he"; D="Nguoi lao dong, nguoi su dung LD, to chuc dai dien, quyen loi & nghia vu"; C=$script:Gold},
        @{L="L5"; N="Quy trinh & Thu tuc"; D="Thu tuc hanh chinh, ho so yeu cau, co quan giai quyet, thoi han xu ly"; C=$script:Red},
        @{L="L6"; N="Thoi gian & Thoi hieu"; D="Moc thoi gian luat dinh, thoi han bao truoc, thoi hieu khieu nai"; C=$script:Green},
        @{L="L7"; N="Che tai & Rui ro"; D="Hanh vi vi pham, khung phat tien, bien phap khac phuc hau qua, muc do rui ro"; C=$script:Teal},
        @{L="L8"; N="Vong doi Quan he LD"; D="Giao ket > Thuc hien > Sua doi > Tam hoan > Cham dut hop dong lao dong"; C=$script:Blue},
        @{L="L9"; N="An le & Thuc tien"; D="Phan quyet toa an, tinh tiet cot loi (san sang mo rong khi nap an le)"; C=$script:Purple}
    )
    $ly1 = 115
    for ($i = 0; $i -lt 5; $i++) {
        $l = $layers[$i]
        [void](Add-Rect $s11 44 $ly1 420 62 $script:White $script:Line 6)
        [void](Add-Pill $s11 $l.L 54 ($ly1 + 12) 42 $script:Bg $l.C 20 9)
        [void](Add-Text $s11 $l.N 106 ($ly1 + 10) 345 18 10.5 $script:Dark $true)
        [void](Add-Text $s11 $l.D 106 ($ly1 + 30) 345 28 8.4 $script:Muted $false)
        $ly1 += 70
    }
    $ly2 = 115
    for ($i = 5; $i -lt 10; $i++) {
        $l = $layers[$i]
        [void](Add-Rect $s11 484 $ly2 432 62 $script:White $script:Line 6)
        [void](Add-Pill $s11 $l.L 494 ($ly2 + 12) 42 $script:Bg $l.C 20 9)
        [void](Add-Text $s11 $l.N 546 ($ly2 + 10) 355 18 10.5 $script:Dark $true)
        [void](Add-Text $s11 $l.D 546 ($ly2 + 30) 355 28 8.4 $script:Muted $false)
        $ly2 += 70
    }
    [void](Add-Text $s11 "Quy tac duyet do thi: Moi duong di tren do thi bat buoc phai ket thuc tai LegalChunk co trich dan van ban quy pham phap luat dang co hieu luc." 44 480 872 16 8.8 $script:Green $true)

    # Slide 12: Adaptive Routing & Evidence Gating
    $s12 = $presentation.Slides.Add(12, $blankLayout)
    Add-Chrome $s12 "TRUY HOI & TAO SINH" "Phan Luong Cau Hoi Thich Ung (Adaptive Routing) va Evidence Gating" 12
    $p12_1 = "- Single-hop (Don tang): Tra cuu truc tiep 1 dieu khoan -> Chay nhanh qua nhanh Hybrid RAG (pgvector + BM25) trong ~15ms." + [Environment]::NewLine + "- Multi-hop (Da tang / Quan he): Cau hoi so sanh, lien ket van ban -> Kich hoat duyet do thi Neo4j 2-hop de gom day du can cu cheo."
    Add-Card $s12 "1. Phan luong Do phuc tap (Routing)" $p12_1 44 115 420 160 $script:Green $script:White 9.5

    $p12_2 = "- Chuan hoa Teencode / Viet tat: Chi chuan hoa khi phat hien tin hieu nhieu, bao toan nguyen ven so tien, ngay thang." + [Environment]::NewLine + "- Phan tach Khia canh (Facet Decomposition): Tach cau hoi kep thanh cac van de doc lap de truy hoi rieng biet, tranh bo sot y."
    Add-Card $s12 "2. Xu ly Cau hoi Phuc & Nhieu" $p12_2 484 115 432 160 $script:Teal $script:White 9.5

    $p12_3 = "- Kiem tra tinh lien quan cua Chunk truoc khi dua vao context prompt." + [Environment]::NewLine + "- Neu khong tim thay can cu phap ly phu hop: He thong chu dong tra ve thong bao chua du co so thay vi de LLM tu suy dien sai lech."
    Add-Card $s12 "3. Cong Bang chung (Evidence Gate)" $p12_3 44 290 420 175 $script:Purple $script:White 9.5

    $p12_4 = "- He thong gan nhan trich dan [S1], [S2]... cho tung khang dinh." + [Environment]::NewLine + "- Hau kiem tra (Post-validation): Kiem tra tung [S_i] co thuc su chua noi dung chung minh cho cau tra loi hay khong." + [Environment]::NewLine + "- Loai bo trich dan mo coi hoac khong lien quan."
    Add-Card $s12 "4. Xac thuc Trich dan (Citation Validation)" $p12_4 484 290 432 175 $script:Gold $script:White 9.5

    # Slide 13: Evaluation Methodology
    $s13 = $presentation.Slides.Add(13, $blankLayout)
    Add-Chrome $s13 "DANH GIA DO CHINH XAC" "Phuong Phap Danh Gia Do Chinh Xac: Vector Chat Luong 8 Chieu" 13
    [void](Add-Rect $s13 44 115 872 45 $script:Dark $script:Dark 8)
    [void](Add-Text $s13 "Do chinh xac trong Phap ly la mot Vector da chieu: Q = (Q_ret, Q_faith, Q_rel, Q_fact, Q_cite, Q_facet, Q_temp, Q_lat)" 60 126 840 22 11 $script:White $true 2 3)

    $evalCards = @(
        @{T="1. FAITHFULNESS (Tinh trung thuc)"; D="Ty le cac phat bieu trong cau tra loi duoc chung minh truc tiep boi ngu canh trich dan (|S_q| / |A_q|). Triet tieu ao giac."; C=$script:Green; X=44; Y=175; W=208},
        @{T="2. ANSWER RELEVANCY"; D="Muc do cau tra loi giai quyet dung va trung cau hoi cua nguoi dung, khong tra loi lan man hoac lac de."; C=$script:Teal; X=265; Y=175; W=208},
        @{T="3. CONTEXT PRECISION & RECALL"; D="Do chinh xac va do bao phu cua tap chunk trich xuat so voi tap bang chung chuan (Ground Truth)."; C=$script:Blue; X=486; Y=175; W=208},
        @{T="4. FACTUAL CORRECTNESS"; D="Do chinh xac ve mat su that va ket luan phap ly so voi cau tra loi mau cua chuyen gia luat."; C=$script:Purple; X=708; Y=175; W=208}
    )
    foreach ($ec in $evalCards) {
        [void](Add-Rect $s13 $ec.X $ec.Y $ec.W 130 $script:White $script:Line 8)
        [void](Add-Rect $s13 $ec.X $ec.Y 5 130 $ec.C $ec.C 0)
        [void](Add-Text $s13 $ec.T ($ec.X + 10) ($ec.Y + 8) ($ec.W - 16) 30 9.5 $ec.C $true)
        [void](Add-Text $s13 $ec.D ($ec.X + 10) ($ec.Y + 40) ($ec.W - 16) 80 8.8 $script:Muted $false)
    }
    $p13_id = "- Danh gia muc do trung khop chinh xac ma dinh danh dieu khoan phap ly: R_ID = |R_k giao G| / |G| va P_ID = |R_k giao G| / |R_k|."
    Add-Card $s13 "Context ID Precision & Recall" $p13_id 44 320 430 145 $script:Gold $script:White 9.5
    $p13_bench = "- 100 cau hoi luat lao dong thuc te chia lam 3 nhom: 50 Single-hop, 25 Multi-hop Specific, 25 Multi-hop Abstract." + [Environment]::NewLine + "- So sanh truc dien 4 kien truc: Dense RAG, LightRAG, GraphRAG, RAG+GraphRAG."
    Add-Card $s13 "Bo Benchmark RAGAS 100 Cau hoi Thuc te" $p13_bench 484 320 432 145 $script:Green $script:SoftGreen 9.5

    # Slide 14: RAGAS Benchmark Results
    $s14 = $presentation.Slides.Add(14, $blankLayout)
    Add-Chrome $s14 "KET QUA THUC NGHIEM" "Bang Ket Qua So Sanh Thuc Nghiem 4 Kien Truc (RAGAS Benchmark 100)" 14
    $cols = @(
        @{N="Kien truc"; X=44; W=120},
        @{N="Faithfulness"; X=168; W=95},
        @{N="Ans Relevancy"; X=267; W=95},
        @{N="Ctx Precision"; X=366; W=95},
        @{N="Ctx Recall"; X=465; W=95},
        @{N="Factual Corr."; X=564; W=95},
        @{N="ID Recall"; X=663; W=80},
        @{N="Latency (Ret)"; X=747; W=85},
        @{N="Overall RAGAS"; X=836; W=80}
    )
    [void](Add-Rect $s14 44 115 872 28 $script:Dark $script:Dark 0)
    foreach ($col in $cols) {
        [void](Add-Text $s14 $col.N $col.X 120 $col.W 18 8.5 $script:White $true 2 3)
    }
    $rows = @(
        @{Arch="Dense RAG"; Faith="0.9111"; Rel="0.9126"; Prec="0.7783"; Rec="0.8154"; Fact="0.3985"; IDR="0.6800"; Lat="15.8 ms"; Overall="0.7619"; Best=$true; C=$script:Green},
        @{Arch="LightRAG"; Faith="0.9160"; Rel="0.8951"; Prec="0.6950"; Rec="0.8124"; Fact="0.4271"; IDR="0.6650"; Lat="148.8 ms"; Overall="0.7481"; Best=$false; C=$script:Blue},
        @{Arch="GraphRAG"; Faith="0.9213*"; Rel="0.8641"; Prec="0.5558"; Rec="0.7820"; Fact="0.4003"; IDR="0.5750"; Lat="146.7 ms"; Overall="0.7041"; Best=$false; C=$script:Purple},
        @{Arch="RAG+GraphRAG"; Faith="0.9403#"; Rel="--"; Prec="--"; Rec="--"; Fact="--"; IDR="0.6850*"; Lat="162.6 ms"; Overall="Checkpoint"; Best=$false; C=$script:Gold}
    )
    $ry = 145
    foreach ($r in $rows) {
        $bg = $(if ($r.Best) { $script:SoftGreen } else { $script:White })
        [void](Add-Rect $s14 44 $ry 872 32 $bg $script:Line 0)
        [void](Add-Text $s14 $r.Arch 48 ($ry + 6) 112 20 9 $r.C $true 1 3)
        [void](Add-Text $s14 $r.Faith 168 ($ry + 6) 95 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Rel 267 ($ry + 6) 95 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Prec 366 ($ry + 6) 95 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Rec 465 ($ry + 6) 95 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Fact 564 ($ry + 6) 95 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.IDR 663 ($ry + 6) 80 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Lat 747 ($ry + 6) 85 20 9 $script:Dark $false 2 3)
        [void](Add-Text $s14 $r.Overall 836 ($ry + 6) 80 20 9 $r.C $true 2 3)
        $ry += 34
    }
    $p14_eval = "- GraphRAG dat do trung thuc Faithfulness cao nhat (0.9213) nho kha nang bao quat ngu canh cau truc quan he, han che toi da ao giac." + [Environment]::NewLine + "- Dense RAG dat Context Precision va Toc do truy hoi tot nhat (15.8ms vs ~147ms cua Graph) cho cac cau hoi tra cuu don tang (Single-hop)." + [Environment]::NewLine + "- Minh chung cho quyet dinh thiet ke Adaptive Routing: Dung Hybrid Dense RAG lam mac dinh cho cau hoi don gian va chi kich hoat GraphRAG cho cau hoi phuc tap."
    Add-Card $s14 "Nhan xet & Danh gia Khoa hoc tu Du lieu Thuc nghiem" $p14_eval 44 290 872 175 $script:Green $script:SoftGreen 9.8

    # Slide 15: Complexity Analysis
    $s15 = $presentation.Slides.Add(15, $blankLayout)
    Add-Chrome $s15 "PHAN TICH CHUYEN SAU" "Hieu nang theo Phan loai Do phuc tap Cau hoi (Single-hop vs Multi-hop)" 15
    $cTypes = @(
        @{T="Single-Hop Specific (50 cau)"; Dense="0.8114"; Light="0.8039"; Graph="0.7458"; D="Tra cuu truc tiep 1 dieu luat, 1 muc luong toi thieu, 1 thoi han cu the." + [Environment]::NewLine + "-> Dense RAG chiem uu the tuyet doi ve toc do va do chinh xac ngu canh."; C=$script:Green; X=44},
        @{T="Multi-Hop Specific (25 cau)"; Dense="0.7625"; Light="0.7283"; Graph="0.6914"; D="Cau hoi ket hop 2-3 dieu luat (VD: Dieu kien huong luong + Trach nhiem NSDLDT)." + [Environment]::NewLine + "-> Do thi ho tro tim duong dan chieu cheo."; C=$script:Blue; X=343},
        @{T="Multi-Hop Abstract (25 cau)"; Dense="0.6624"; Light="0.6563"; Graph="0.6334"; D="Cau hoi tinh huong tong hop, so sanh quyen loi giua cac nhom lao dong." + [Environment]::NewLine + "-> GraphRAG co muc do suy giam diem so it nhat (-0.112 vs -0.149 cua Dense)."; C=$script:Purple; X=642}
    )
    foreach ($ct in $cTypes) {
        [void](Add-Rect $s15 $ct.X 115 274 235 $script:White $script:Line 8)
        [void](Add-Rect $s15 $ct.X 115 274 6 $ct.C $ct.C 0)
        [void](Add-Text $s15 $ct.T ($ct.X + 10) 128 254 22 10.5 $ct.C $true)
        [void](Add-Rect $s15 ($ct.X + 10) 155 254 50 $script:Bg 0 6)
        [void](Add-Text $s15 ("Dense: " + $ct.Dense + " | Light: " + $ct.Light + " | Graph: " + $ct.Graph) ($ct.X + 12) 168 250 20 9.2 $script:Dark $true 2 3)
        [void](Add-Text $s15 $ct.D ($ct.X + 10) 215 254 125 9.2 $script:Muted $false)
    }
    $p15_trade = "- Do thi tri thuc (Neo4j) giup mo rong quan he phap ly rat tot nhung lam tang do tre truy hoi tu 15.8ms len ~147ms." + [Environment]::NewLine + "- Thoi gian sinh cau tra loi cua LLM chiem da so (5.7s - 8.3s)." + [Environment]::NewLine + "- Thiet ke VlegalAI ket hop: Seed Hybrid Retrieval + Bounded Graph Expansion (2-hop) la toi uu nhat cho moi truong san pham thuc te."
    Add-Card $s15 "Ket luan ve Bai toan Danh doi (Trade-Off): Do chinh xac vs Thoi gian phan hoi" $p15_trade 44 365 872 105 $script:Gold $script:White 9.5

    # Slide 16: Cloud Deployment & Database
    $s16 = $presentation.Slides.Add(16, $blankLayout)
    Add-Chrome $s16 "TRIEN KHAI & HA TANG" "Mo hinh Co So Du Lieu Vat Ly va Ha Tang Google Cloud Platform (GCP)" 16
    Add-Stat $s16 "23" "POSTGRES BASE TABLES" 44 115 160 $script:Green
    Add-Stat $s16 "1" "MATERIALIZED VIEW" 218 115 155 $script:Teal
    Add-Stat $s16 "18" "ALEMBIC MIGRATIONS" 387 115 160 $script:Purple
    Add-Stat $s16 "Cloud Run" "SERVERLESS INGRESS" 561 115 165 $script:Blue
    Add-Stat $s16 "CI / CD" "WIF + GITHUB ACTIONS" 740 115 176 $script:Gold

    $dbGroups = @(
        @{T="Identity & Chat (7 tables)"; D="app_user, sso_identity, user_feedback, conversation, chat_message, conversation_summary, chat_answer_feedback"; C=$script:Green; X=44},
        @{T="Content & Catalog (6 + 1 view)"; D="article, artifact, signature_packet, legal_document, legal_chunk, legal_answer_cache + legal_catalog_corpus (MV)"; C=$script:Teal; X=268},
        @{T="GraphRAG (4 tables)"; D="graphrag_chunk (vector 1024D), graphrag_embedding_checkpoint, graphrag_index_metadata, graphrag_law_version"; C=$script:Blue; X=492},
        @{T="Runtime & Queue (6 tables)"; D="guest_rate_limit, kombu_queue, kombu_message, celery_taskmeta, celery_tasksetmeta, alembic_version"; C=$script:Purple; X=716}
    )
    foreach ($dbg in $dbGroups) {
        [void](Add-Rect $s16 $dbg.X 195 208 175 $script:White $script:Line 8)
        [void](Add-Rect $s16 $dbg.X 195 208 5 $dbg.C $dbg.C 0)
        [void](Add-Text $s16 $dbg.T ($dbg.X + 10) 205 188 32 10 $dbg.C $true)
        [void](Add-Text $s16 $dbg.D ($dbg.X + 10) 242 188 120 8.6 $script:Muted $false)
    }
    $p16_cicd = "- Trien khai qua GitHub Actions voi Workload Identity Federation (WIF) - Khong luu tru Service Account key lau dai." + [Environment]::NewLine + "- 1 Container Image duy nhat cho ca Web API, Celery Worker, Scheduler va Reindex Job." + [Environment]::NewLine + "- Tu dong chay Unit Test (492 backend tests, 16 frontend tests) va Database Migration truoc khi release."
    Add-Card $s16 "Quy trinh CI/CD & Trien khai Bat bien (Immutable Container Image)" $p16_cicd 44 380 872 90 $script:Blue $script:SoftBlue 9.2

    # Slide 17: Features & Product Demo
    $s17 = $presentation.Slides.Add(17, $blankLayout)
    Add-Chrome $s17 "TINH NANG SAN PHAM" "Bo Tinh Nang Toan Dien Ho Tro Doanh Nghiep va Nguoi Lao Dong" 17
    $features = @(
        @{T="1. Tra cuu & Hoi dap Phap ly"; D="- Hoi dap tu nhien bang tieng Viet." + [Environment]::NewLine + "- Cung cap trich dan nguon luat chinh xac [S1-Sn]." + [Environment]::NewLine + "- Hien thi toan van dieu khoan khi click vao citation."; C=$script:Green; X=44; Y=115},
        @{T="2. Soan thao Hop dong Lao dong"; D="- Ho tro tao hop dong theo bieu mau chuan phap luat." + [Environment]::NewLine + "- Tu dong dien muc luong toi thieu vung theo quy dinh moi nhat." + [Environment]::NewLine + "- Xuat file DOCX quy chuan."; C=$script:Teal; X=484; Y=115},
        @{T="3. Ra soat & Danh gia Rui ro HD"; D="- Upload hop dong (DOCX/PDF) de quet dieu khoan bat loi." + [Environment]::NewLine + "- Canh bao vi pham luat lao dong, thieu quyen loi bat buoc." + [Environment]::NewLine + "- Goi y dieu khoan sua doi an toan."; C=$script:Blue; X=44; Y=290},
        @{T="4. So sanh Hai Ban Hop dong"; D="- Tu dong can chinh cac dieu khoan tuong ung giua 2 phien ban." + [Environment]::NewLine + "- Phat hien noi dung them, bot, sua doi." + [Environment]::NewLine + "- Danh gia thay doi muc do rui ro phap ly."; C=$script:Purple; X=484; Y=290}
    )
    foreach ($f in $features) {
        [void](Add-Rect $s17 $f.X $f.Y 420 160 $script:White $script:Line 8)
        [void](Add-Rect $s17 $f.X $f.Y 5 160 $f.C $f.C 0)
        [void](Add-Text $s17 $f.T ($f.X + 14) ($f.Y + 10) 390 22 11 $f.C $true)
        [void](Add-Text $s17 $f.D ($f.X + 14) ($f.Y + 38) 390 110 9.5 $script:Dark $false)
    }

    # Slide 18: Security & Governance
    $s18 = $presentation.Slides.Add(18, $blankLayout)
    Add-Chrome $s18 "BAO MAT & QUAN TRI" "Bao Mat Quyen Rieng Tu va Co Che Quan Tri Du Lieu (Data Governance)" 18
    $p18_1 = "- Hop dong va tep dinh kem duoc ma hoa cap ung dung (Application-level Encryption) bang khoa bao mat." + [Environment]::NewLine + "- Cach ly hoan toan theo User Ownership: Khong bao gio dua tai lieu rieng tu vao Vector Database hay Graph dung chung." + [Environment]::NewLine + "- Token truy cap dinh kem co thoi han (expiring attachment token)."
    Add-Card $s18 "1. Bao ve Tai lieu Tai len Rieng tu" $p18_1 44 115 420 170 $script:Red $script:White 9.5

    $p18_2 = "- Dang nhap qua Google OIDC voi giao thuc Authorization Code Flow ket hop PKCE (Proof Key for Code Exchange)." + [Environment]::NewLine + "- Cookie phien lam viec HttpOnly, Secure, SameSite bao ve chong tan cong XSS/CSRF." + [Environment]::NewLine + "- Tuyet doi khong de lo API Key cua Gemini/GCP tren trinh duyet client."
    Add-Card $s18 "2. Xac thuc & Phan quyen Chuan OAuth" $p18_2 484 115 432 170 $script:Green $script:White 9.5

    $p18_3 = "- Quan ly trang thai van ban: Dang co hieu luc, Het hieu luc, Bi sua doi, Chua co hieu luc." + [Environment]::NewLine + "- Scheduler kiem tra dinh ky nguon van ban chinh thong." + [Environment]::NewLine + "- Tu dong kich hoat luong Re-index cap nhat do thi tri thuc khi co Nghi dinh moi ban hanh."
    Add-Card $s18 "3. Chu ky Cap nhat Van ban Phap luat (Freshness)" $p18_3 44 295 420 170 $script:Blue $script:White 9.5

    $p18_4 = "- Ghi nhan danh gia Hai long (GOOD) / Khong hai long (BAD) cua nguoi dung." + [Environment]::NewLine + "- Cho phep nguoi dung yeu cau tai sinh cau tra loi voi ngu canh duoc dieu chinh." + [Environment]::NewLine + "- Phuc vu cai tien chat luong he thong ma khong lam lo du lieu nhay cam."
    Add-Card $s18 "4. Thu thap Phan hoi & Tai sinh Cau tra loi (HITL)" $p18_4 484 295 432 170 $script:Gold $script:White 9.5

    # Slide 19: Contributions & Verification
    $s19 = $presentation.Slides.Add(19, $blankLayout)
    Add-Chrome $s19 "TONG KET & HUONG MO" "Tong Ket Dong Gop Cot Loi va Huong Phat Trien Tuong Lai" 19
    $p19_1 = "[*] Xay dung thanh cong Do thi Tri thuc Phap luat Lao dong 10 tang voi 29,575 nodes va 108,368 edges tu 74 van ban phap luat quy chuan." + [Environment]::NewLine + "[*] De xuat chien luoc Chunking theo cap bac phap ly (Hierarchy-Aware Chunking) va cua so truot W=360, O=70 bao toan 100% ngu canh dieu luat." + [Environment]::NewLine + "[*] Hien thuc hoa kien truc Adaptive Hybrid RAG (pgvector + BM25 + Neo4j) ket hop Reciprocal Rank Fusion va Evidence Gate chong ao giac." + [Environment]::NewLine + "[*] Xay dung bo Benchmark chuan RAGAS 100 cau hoi va danh gia thuc nghiem toan dien tren 8 tieu chi."
    Add-Card $s19 "Dong Gop Khoa Hoc & Ky Thuat Cot Loi" $p19_1 44 115 420 220 $script:Green $script:SoftGreen 9.2

    $p19_2 = "- Thoi gian sinh cau tra loi cua LLM con do tre duoi (p95 latency) do phu thuoc vao cloud API cua Vertex AI." + [Environment]::NewLine + "- Bo du lieu danh gia can mo rong them chuyen gia tham dinh cheo (Inter-rater Agreement)." + [Environment]::NewLine + "- Ke hoach tuong lai: Huan luyen mo hinh Reranker cuc bo de giam do tre, nap them kho An le Toa an (Layer 9), mo rong sang Luat Doanh nghiep va Luat Thue."
    Add-Card $s19 "Han Che Hien Tai & Huong Phat Trien" $p19_2 484 115 432 220 $script:Gold $script:White 9.2

    [void](Add-Rect $s19 44 350 872 115 $script:White $script:Line 8)
    [void](Add-Text $s19 "Minh chung Chat luong & Do tin cay cua Do an:" 60 360 840 20 11 $script:Dark $true)
    [void](Add-Pill $s19 "492 BACKEND UNIT TESTS PASSED" 60 390 230 $script:SoftGreen $script:Green 26 9.5)
    [void](Add-Pill $s19 "16 FRONTEND INTEGRATION TESTS PASSED" 305 390 270 $script:SoftBlue $script:Blue 26 9.5)
    [void](Add-Pill $s19 "100% CLOUD DEPLOYMENT READY" 590 390 230 $script:SoftGold $script:Gold 26 9.5)
    [void](Add-Text $s19 "Toan bo ma nguon, du lieu danh gia, database migrations va tai lieu bao cao deu co the tai lap (Reproducible) 100%." 60 430 840 20 9.5 $script:Muted $false)

    # Slide 20: Q&A Conclusion
    $s20 = $presentation.Slides.Add(20, $blankLayout)
    [void](Add-Rect $s20 0 0 $script:W $script:H $script:Dark $script:Dark 0)
    [void](Add-Rect $s20 0 0 12 $script:H $script:Green $script:Green 0)

    [void](Add-Text $s20 "CAM ON THAY CO & HOI DONG BAO VE" 56 120 800 40 28 $script:White $true 2 3)
    [void](Add-Text $s20 "NHOM THUC HIEN DE TAI VLEGALAI SAN SANG LANG NGHE Y KIEN DONG GOP & TRA LOI CAU HOI" 56 175 800 30 13 $script:Teal $true 2 3)
    [void](Add-Line $s20 180 220 780 220 $script:Green 2 $false)

    $qas = @(
        @{T="1. Chunking & Cat chuoi"; D="Hierarchy-Aware: Theo Dieu/Khoan/Diem. Cua so truot W=360, Overlap=70 tu; dem tu bang regex tieng Viet."; X=56; Y=240; W=250},
        @{T="2. Co Train LLM Khong?"; D="KHONG train/fine-tune weight. Dung Hosted Gemini 2.5 Flash + RAG/GraphRAG de giu 100% provenance & cap nhat luat."; X=320; Y=240; W=250},
        @{T="3. Danh Gia Do Chinh Xac"; D="Vector 8 chieu qua RAGAS (100 cau hoi luat thuc te): Faithfulness dat 0.9213, ID Recall dat 0.6800."; X=584; Y=240; W=250},
        @{T="4. Xu Ly & Vector Embedding"; D="Input contract: Title + Path + Text. Model gemini-embedding-001 (1024D), chuan hoa L2, caching SHA-256."; X=188; Y=355; W=260},
        @{T="5. Cau Truc Document Parsing"; D="Deterministic State Machine phan tich cu phap DOCX thanh Envelope 4 mang: source, document, nodes, edges, chunks."; X=462; Y=355; W=260}
    )
    foreach ($qa in $qas) {
        [void](Add-Rect $s20 $qa.X $qa.Y $qa.W 95 $script:CardDark 0 8)
        [void](Add-Text $s20 $qa.T ($qa.X + 10) ($qa.Y + 8) ($qa.W - 20) 20 10.5 $script:Gold $true 1 3)
        [void](Add-Text $s20 $qa.D ($qa.X + 10) ($qa.Y + 30) ($qa.W - 20) 60 8.6 $script:White $false 1 1)
    }
    [void](Add-Text $s20 "VlegalAI: Tro ly Phap ly Lao dong Viet Nam - Capstone Project 2026" 56 480 800 20 9 $script:Muted $false 2)

    # Save
    Write-Host "Saving presentation to $OutputFile..."
    $presentation.SaveAs($OutputFile)
    $presentation.Close()
    $presentation = $null
    $ppt.Quit()
    $ppt = $null

    Write-Host "Successfully generated presentation with 20 slides at: $OutputFile"
}
catch {
    Write-Error "Error generating slides: $_"
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
