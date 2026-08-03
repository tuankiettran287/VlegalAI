import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";

import { ApiError, legalDocumentApi } from "./api";
import type { LegalDocumentDetail } from "./types";

const statusLabels: Record<string, string> = {
  IN_FORCE: "Còn hiệu lực",
  PARTIALLY_IN_FORCE: "Còn hiệu lực một phần",
  AMENDED: "Đã sửa đổi",
  EXPIRED: "Hết hiệu lực",
  REPLACED: "Đã được thay thế",
  UNKNOWN: "Chưa xác minh hiệu lực",
  UNVERIFIED: "Chưa xác minh hiệu lực",
};

function safeOfficialUrl(value?: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export default function LegalDocumentPage({
  code,
  citation,
  onNavigate,
}: {
  code: string;
  citation: string;
  onNavigate: (path: string) => void;
}) {
  const [page, setPage] = useState(1);
  const [document, setDocument] = useState<LegalDocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setPage(1);
  }, [code, citation]);

  useEffect(() => {
    if (!code) {
      setDocument(null);
      setError("Liên kết căn cứ không chứa số hiệu văn bản.");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    legalDocumentApi.get(code, citation, page)
      .then((result) => {
        if (active) setDocument(result);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setDocument(null);
        setError(
          reason instanceof ApiError
            ? reason.message
            : "Không thể mở căn cứ này. Vui lòng thử lại.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [citation, code, page]);

  const officialUrl = safeOfficialUrl(document?.source_url);
  const totalPages = useMemo(() => {
    if (!document || document.focused) return 1;
    return Math.max(1, Math.ceil(document.total / document.page_size));
  }, [document]);

  return (
    <section className="legal-document-page" aria-labelledby="legal-document-title">
      <button className="legal-document-back" type="button" onClick={() => onNavigate("/")}>
        <ArrowLeft size={16} />
        Quay lại hỏi đáp
      </button>

      {loading && (
        <div className="legal-document-state" role="status">
          <LoaderCircle className="spin" size={28} />
          <strong>Đang mở căn cứ…</strong>
          <span>VLegal đang lấy đúng nội dung đã dùng để tạo câu trả lời.</span>
        </div>
      )}

      {!loading && error && (
        <div className="legal-document-state error" role="alert">
          <FileText size={28} />
          <strong>Không thể mở căn cứ</strong>
          <span>{error}</span>
        </div>
      )}

      {!loading && document && (
        <>
          <header className="legal-document-hero">
            <div className="legal-document-kicker"><BookOpen size={15} /> Căn cứ pháp lý</div>
            <h1 id="legal-document-title">{document.title}</h1>
            <div className="legal-document-meta">
              <strong>{document.code}</strong>
              <span>{statusLabels[document.status] || document.status}</span>
              {document.issuer && <span>{document.issuer}</span>}
              {document.law_version && <span>Phiên bản {document.law_version}</span>}
            </div>
            <div className="legal-document-actions">
              <span><ShieldCheck size={15} /> Nội dung lấy trực tiếp từ kho dữ liệu VLegal</span>
              {officialUrl && (
                <a href={officialUrl} target="_blank" rel="noopener noreferrer">
                  Mở nguồn chính thức <ExternalLink size={14} />
                </a>
              )}
            </div>
          </header>

          {document.focused && (
            <div className="legal-document-focus-note">
              <ShieldCheck size={17} />
              <span>Đang hiển thị đúng điều khoản được dùng làm căn cứ trong câu trả lời.</span>
            </div>
          )}

          <div className="legal-document-sections">
            {document.sections.map((section, index) => (
              <article key={`${section.ordinal}-${section.citation}`}>
                <div className="legal-section-index">
                  {String(
                    document.focused
                      ? index + 1
                      : (document.page - 1) * document.page_size + index + 1,
                  ).padStart(2, "0")}
                </div>
                <div>
                  <span className="legal-section-path">
                    {section.path_label || section.citation || section.chunk_type}
                  </span>
                  <h2>{section.title || section.citation}</h2>
                  <p>{section.text}</p>
                </div>
              </article>
            ))}
          </div>

          {!document.sections.length && (
            <div className="legal-document-state">
              <FileText size={28} />
              <strong>Văn bản chưa có nội dung có thể hiển thị</strong>
            </div>
          )}

          {!document.focused && totalPages > 1 && (
            <nav className="legal-document-pagination" aria-label="Phân trang văn bản">
              <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                <ChevronLeft size={16} /> Trang trước
              </button>
              <span>Trang {page}/{totalPages}</span>
              <button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>
                Trang sau <ChevronRight size={16} />
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
