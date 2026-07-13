const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const clearButton = document.querySelector("#clear-chat");
const backendSelect = document.querySelector("#backend-select");
const modeInputs = Array.from(document.querySelectorAll("input[name='retrieval-mode']"));
const MODE_STORAGE_KEY = "vlegalai-retrieval-mode";

function iconRefresh() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function selectedModeInput() {
  return modeInputs.find((modeInput) => modeInput.checked);
}

function selectedBackend() {
  return selectedModeInput()?.value || backendSelect?.value || "hybrid_rag";
}

function selectedModeLabel() {
  return selectedModeInput()?.dataset.label || "Hybrid RAG";
}

function syncBackendSelect(value) {
  if (backendSelect) {
    backendSelect.value = value;
  }
}

function restoreSelectedMode() {
  const saved = window.localStorage?.getItem(MODE_STORAGE_KEY);
  const mode = modeInputs.find((modeInput) => modeInput.value === saved);
  if (mode) {
    mode.checked = true;
  }
  syncBackendSelect(selectedBackend());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderText(value) {
  const safe = escapeHtml(value);
  return safe
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function welcomeTemplate() {
  return `
    <div class="welcome-container">
      <div class="welcome-icon-box" aria-hidden="true">
        <i data-lucide="landmark"></i>
      </div>
      <p class="eyebrow">Luật lao động Việt Nam</p>
      <h1 class="welcome-title">Bạn cần làm rõ vấn đề lao động nào?</h1>
      <p class="welcome-subtitle">
        Đặt câu hỏi cụ thể về hợp đồng, lương, bảo hiểm, kỷ luật lao động hoặc chấm dứt hợp đồng.
      </p>

      <div class="suggestions-grid">
        <button type="button" class="suggestion-card" data-question="Quyền lợi bảo hiểm xã hội của tôi gồm những gì?">
          <i data-lucide="shield-check"></i>
          <span>Quyền lợi bảo hiểm xã hội của tôi gồm những gì?</span>
        </button>
        <button type="button" class="suggestion-card" data-question="Cách tính lương làm thêm giờ theo luật hiện hành?">
          <i data-lucide="timer"></i>
          <span>Cách tính lương làm thêm giờ theo luật hiện hành?</span>
        </button>
        <button type="button" class="suggestion-card" data-question="Chế độ thai sản được nghỉ bao lâu và hưởng thế nào?">
          <i data-lucide="heart-handshake"></i>
          <span>Chế độ thai sản được nghỉ bao lâu và hưởng thế nào?</span>
        </button>
        <button type="button" class="suggestion-card" data-question="Thủ tục chấm dứt hợp đồng lao động hợp pháp?">
          <i data-lucide="file-signature"></i>
          <span>Thủ tục chấm dứt hợp đồng lao động hợp pháp?</span>
        </button>
      </div>
    </div>
  `;
}

function renderWelcome() {
  messages.innerHTML = welcomeTemplate();
  iconRefresh();
}

function addMessage(role, content) {
  const welcome = messages.querySelector(".welcome-container");
  if (welcome) {
    messages.innerHTML = "";
  }

  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = role === "assistant" ? '<div class="avatar">LC</div>' : "";
  article.innerHTML = `
    ${avatar}
    <div class="bubble">${renderText(content)}</div>
  `;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function setLoading(isLoading) {
  const button = form.querySelector("button");
  button.disabled = isLoading;
  input.disabled = isLoading;
  modeInputs.forEach((modeInput) => {
    modeInput.disabled = isLoading;
  });

  const span = button.querySelector("span");
  if (span) {
    span.textContent = isLoading ? "Đang tra" : "Gửi";
  }
}

function renderInlineSources(sources) {
  if (!sources.length) return "";

  return `
    <div class="message-sources">
      <details class="sources-details">
        <summary>
          <i data-lucide="file-text"></i>
          <span>Xem ${sources.length} căn cứ pháp lý</span>
          <i data-lucide="chevron-down" class="chevron-icon"></i>
        </summary>
        <div class="sources-inline-list">
          ${sources
            .map(
              (source) => `
                <div class="source-inline-card">
                  <div class="source-inline-header">
                    <span class="source-inline-id">${escapeHtml(source.source_id)}</span>
                    <span class="source-inline-citation">${escapeHtml(source.citation || source.title || "Nguồn pháp lý")}</span>
                  </div>
                  <p class="source-inline-text">${escapeHtml(source.text)}</p>
                </div>
              `,
            )
            .join("")}
        </div>
      </details>
    </div>
  `;
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 148)}px`;
}

async function ask(question) {
  const trimmed = question.trim();
  if (!trimmed) return;

  addMessage("user", trimmed);
  input.value = "";
  resizeInput();
  setLoading(true);

  const backend = selectedBackend();
  const modeLabel = selectedModeLabel();
  const loading = addMessage("assistant", `Đang tra cứu bằng ${modeLabel}...`);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed, top_k: 10, backend }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Không gọi được API");
    }

    const sources = data.sources || [];
    loading.querySelector(".bubble").innerHTML = renderText(data.answer) + renderInlineSources(sources);
    iconRefresh();
  } catch (error) {
    loading.querySelector(".bubble").innerHTML = renderText(`Lỗi: ${error.message}`);
  } finally {
    setLoading(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

input.addEventListener("input", resizeInput);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ask(input.value);
  }
});

modeInputs.forEach((modeInput) => {
  modeInput.addEventListener("change", () => {
    if (!modeInput.checked) return;
    syncBackendSelect(modeInput.value);
    window.localStorage?.setItem(MODE_STORAGE_KEY, modeInput.value);
  });
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (button) {
    input.value = button.dataset.question || "";
    resizeInput();
    ask(input.value);
  }
});

clearButton?.addEventListener("click", () => {
  renderWelcome();
  input.focus();
});

window.addEventListener("load", () => {
  restoreSelectedMode();
  resizeInput();
  iconRefresh();
  initGraphSidebar();
});

/* ==========================================================================
   Multi-Layer Graph Sidebar Logic
   ========================================================================== */
const LAYERS_CONFIG = [
  {
    index: 1,
    name: "Lớp 1: Cấu trúc & Liên kết Văn bản",
    vnName: "Document Hierarchy",
    desc: "Mô hình hóa cấu trúc hình học của văn bản luật như Chương, Mục, Điều, Khoản, Điểm, Cơ quan ban hành để tra cứu nguồn pháp lý gốc.",
    nodeTypes: ["VănBản", "Chương", "Mục", "Điều", "Khoản", "Điểm", "CơQuanBanHành"],
    relations: ["THUỘC_VỀ", "HƯỚNG_DẪN", "DẪN_CHIẾU_ĐẾN", "SỬA_ĐỔI", "THAY_THẾ", "BAN_HÀNH"]
  },
  {
    index: 2,
    name: "Lớp 2: Thuật ngữ & Định nghĩa Pháp lý",
    vnName: "Legal Semantic Spectrum",
    desc: "Định nghĩa sâu sắc thuật ngữ chuyên ngành luật, cách tính công thức và các tham số/con số định lượng đặc thù.",
    nodeTypes: ["ThuậtNgữ", "CáchTính_CôngThức", "ThamSố_ConSố"],
    relations: ["ĐƯỢC_ĐỊNH_NGHĨA_LÀ", "ÁP_DỤNG_CHO", "CÓ_THAM_SỐ"]
  },
  {
    index: 3,
    name: "Lớp 3: Tình huống & Thực thể Quan hệ",
    vnName: "Domain Ontology",
    desc: "Ánh xạ từ ngôn ngữ đời sống của NLĐ sang thực thể luật: Chủ thể (NLĐ, NSDLĐ, Công đoàn), loại HĐLĐ, hành vi vi phạm, chế độ quyền lợi.",
    nodeTypes: ["ChủThể", "HợpĐồngLaoĐộng", "HànhVi_SựKiện", "ChếĐộ_QuyềnLợi"],
    relations: ["KÝ_KẾT", "THỰC_HIỆN", "CÓ_QUYỀN_HƯỞNG", "BỊ_NẰM_TRONG_DANH_MỤC_CẤM"]
  },
  {
    index: 4,
    name: "Lớp 4: Logic Thời gian & Thời hiệu",
    vnName: "Temporal & State Transition",
    desc: "Quản lý thời hạn và trạng thái hiệu lực pháp lý (thời hiệu khởi kiện, thời hạn báo trước) kích hoạt bởi sự kiện thực tế.",
    nodeTypes: ["SựKiệnKíchHoạt", "MốcThờiGian_LuậtĐịnh", "TrạngTháiPhápLý"],
    relations: ["BẮT_ĐẦU_TÍNH_THỜI_HIỆU", "CHUYỂN_TRẠNG_THÁI"]
  },
  {
    index: 5,
    name: "Lớp 5: Quy trình & Thủ tục Hành chính",
    vnName: "Process-Oriented",
    desc: "Xây dựng các bước thủ tục hành chính (nhận BHXH 1 lần, rút thai sản, trợ cấp thất nghiệp...), yêu cầu hồ sơ giấy tờ, cơ quan thụ lý.",
    nodeTypes: ["ThủTục_ChếĐộ", "HồSơ_GiấyTờ", "ĐiềuKiện", "CơQuanGiảiQuyết", "ThờiHạn_ThờiGian"],
    relations: ["YÊU_CẦU_ĐIỀU_KIỆN", "BAO_GỒM_HỒ_SƠ", "NỘP_TẠI", "CÓ_THỜI_HẠN_LÀ"]
  },
  {
    index: 6,
    name: "Lớp 6: Vòng đời NLĐ & Doanh nghiệp",
    vnName: "Lifecycle-Based",
    desc: "Mô hình hóa toàn bộ vòng đời của NLĐ (tuyển dụng -> thử việc -> ký HĐ -> nghỉ hưu) và Doanh nghiệp nhằm tự động kích hoạt nghĩa vụ pháp lý.",
    nodeTypes: ["GiaiĐoạn_NLĐ", "GiaiĐoạn_DoanhNghiệp", "NghĩaVụ_ThờiĐiểm"],
    relations: ["GIAI_ĐOẠN_TIẾP_THEO", "KÍCH_HOẠT_NGHĨA_VỤ"]
  },
  {
    index: 7,
    name: "Lớp 7: Tuân thủ & Quản trị Rủi ro",
    vnName: "Compliance & Risk Matrix",
    desc: "Xác định hành vi doanh nghiệp cấu thành vi phạm, đánh giá thang rủi ro (Thấp - Vừa - Nghiêm trọng) và khuyến nghị biện pháp khắc phục.",
    nodeTypes: ["HànhViDoanhNghiệp", "MứcĐộRủiRo", "BiệnPhápKhắcPhục"],
    relations: ["GÂY_RA_RỦI_RO", "KHẮC_PHỤC_BẰNG"]
  },
  {
    index: 8,
    name: "Lớp 8: Án lệ & Thực tế xét xử",
    vnName: "Precedent & Case-Based Reasoning",
    desc: "Phân tích án lệ và bản án mẫu (tòa án tối cao, tòa địa phương) để đối sánh tình tiết tranh chấp cốt lõi và dự báo phán quyết.",
    nodeTypes: ["ÁnLệ", "BảnÁnMẫu", "TìnhTiếtCốtLõi", "PhánQuyết"],
    relations: ["ÁP_DỤNG_ĐIỀU_LUẬT", "CÓ_TÌNH_TIẾT_TƯƠNG_TỰ", "DẪN_ĐẾN_PHÁN_QUYẾT"]
  }
];

let globalStats = null;

async function initGraphSidebar() {
  const toggleBtn = document.querySelector("#toggle-sidebar");
  const sidebar = document.querySelector("#graph-sidebar");
  
  if (!toggleBtn || !sidebar) return;
  
  // Collapse toggle
  toggleBtn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    toggleBtn.classList.toggle("active");
  });
  
  try {
    const backend = selectedBackend();
    const res = await fetch(`/api/stats?backend=${backend}`);
    if (!res.ok) throw new Error("Failed to fetch stats");
    const data = await res.json();
    globalStats = data;
    renderLayersList(data);
  } catch (err) {
    console.error("Error loading graph stats:", err);
    document.querySelector("#layers-stats-list").innerHTML = `
      <div style="color: var(--muted); text-align: center; padding: 12px; font-size: 12px;">
        Chưa tải được cấu trúc đồ thị. Thử lại sau.
      </div>
    `;
  }
}

function renderLayersList(stats) {
  const listEl = document.querySelector("#layers-stats-list");
  if (!listEl) return;
  
  const nodeTypesCounts = stats.node_types || {};
  let totalNodesAcrossLayers = 0;
  
  // Compute counts for each layer
  const layerStats = LAYERS_CONFIG.map(layer => {
    let count = 0;
    layer.nodeTypes.forEach(type => {
      count += nodeTypesCounts[type] || 0;
    });
    totalNodesAcrossLayers += count;
    return { ...layer, count };
  });
  
  // Find max count to set progress bar percentages relatively
  const maxCount = Math.max(...layerStats.map(l => l.count), 1);
  
  listEl.innerHTML = layerStats.map(layer => {
    const percentage = Math.round((layer.count / maxCount) * 100);
    return `
      <div class="layer-card" data-layer-index="${layer.index}">
        <div class="layer-card-header">
          <span class="layer-card-title">${escapeHtml(layer.name)}</span>
          <span class="layer-card-count">${layer.count} nodes</span>
        </div>
        <div class="layer-progress-bar">
          <div class="layer-progress-fill" style="width: ${percentage}%"></div>
        </div>
      </div>
    `;
  }).join("");
  
  // Bind click handlers to layer cards
  const cards = listEl.querySelectorAll(".layer-card");
  cards.forEach(card => {
    card.addEventListener("click", () => {
      const idx = parseInt(card.dataset.layerIndex);
      cards.forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      showLayerDetails(idx, layerStats.find(l => l.index === idx));
    });
  });
}

function showLayerDetails(index, layerData) {
  const detailsBox = document.querySelector("#layer-details-box");
  if (!detailsBox) return;
  
  detailsBox.classList.add("active");
  
  // Render entity type badges
  const nodesBadges = layerData.nodeTypes.map(type => 
    `<span class="details-tag node">${escapeHtml(type)}</span>`
  ).join("");
  
  // Render relation type badges
  const relsBadges = layerData.relations.map(rel => 
    `<span class="details-tag rel">${escapeHtml(rel)}</span>`
  ).join("");
  
  detailsBox.innerHTML = `
    <h3 class="details-title">${escapeHtml(layerData.name)}</h3>
    <div class="details-sub">${escapeHtml(layerData.vnName)}</div>
    <p class="details-desc">${escapeHtml(layerData.desc)}</p>
    
    <div class="details-lists">
      <div class="details-group">
        <h4>Loại thực thể (${layerData.nodeTypes.length})</h4>
        <div class="details-tags">
          ${nodesBadges}
        </div>
      </div>
      <div class="details-group">
        <h4>Loại quan hệ liên kết (${layerData.relations.length})</h4>
        <div class="details-tags">
          ${relsBadges}
        </div>
      </div>
    </div>
  `;
  
  iconRefresh();
}

