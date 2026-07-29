import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  Clock3,
  ExternalLink,
  Eye,
  FilePenLine,
  FileText,
  MessageSquareText,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { articleApi } from "./api";
import type { Article, WebSource } from "./types";

type ArticlesPageProps = {
  slug?: string;
  onNavigate: (path: string) => void;
};

type ResearchResult = {
  summary: string;
  sources: WebSource[];
  providers: string[];
  warnings: string[];
  googleSearchEntryPoint: string;
};

const ALL_CATEGORIES = "Tất cả";
const coverTones = ["emerald", "navy", "gold", "clay"] as const;

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function articleMarkdown(value: string) {
  return escapeHtml((value || "").replace(/\r\n?/g, "\n").trim())
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/^[-•] (.*)$/gm, "<div class='md-list-item'>• $1</div>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/<\/div>\n+(?=<div class='md-list-item'>)/g, "</div>")
    .replace(/\n{2,}/g, "<span class='md-paragraph-gap'></span>")
    .replace(/\n/g, "<br />");
}

function formatArticleDate(value?: string | null) {
  if (!value) return "Chưa xác định";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Chưa xác định";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function readingMinutes(content: string) {
  const wordCount = content.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.ceil(wordCount / 220));
}

function coverTone(article: Article) {
  const seed = Array.from(`${article.category}:${article.title}`)
    .reduce((total, character) => total + character.codePointAt(0)!, 0);
  return coverTones[seed % coverTones.length];
}

function ArticleCover({
  article,
  large = false,
}: {
  article: Article;
  large?: boolean;
}) {
  return (
    <div className={`article-cover tone-${coverTone(article)}${large ? " is-large" : ""}`}>
      <span className="article-cover-category">{article.category}</span>
      <div className="article-cover-brand">
        <Scale size={large ? 34 : 25} />
        <strong>VLegal</strong>
      </div>
      <div className="article-cover-art" aria-hidden="true">
        <span />
        <BookOpen size={large ? 74 : 52} />
        <Scale size={large ? 55 : 40} />
      </div>
      <p>{article.title}</p>
    </div>
  );
}

function InlineError({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="article-error" role="alert">
      <ShieldCheck size={18} />
      <span>{message}</span>
      <button type="button" onClick={onClose} aria-label="Đóng thông báo">
        <X size={16} />
      </button>
    </div>
  );
}

function ArticleDetail({
  article,
  loading,
  error,
  onBack,
  onNavigate,
}: {
  article: Article | null;
  loading: boolean;
  error: string;
  onBack: () => void;
  onNavigate: (path: string) => void;
}) {
  if (loading) {
    return (
      <section className="tool-page article-detail-page" aria-busy="true">
        <div className="article-reader-loading">
          <span />
          <span />
          <span />
        </div>
      </section>
    );
  }

  if (!article) {
    return (
      <section className="tool-page article-detail-page">
        <button className="article-back-button" type="button" onClick={onBack}>
          <ArrowLeft size={17} /> Quay lại danh sách
        </button>
        <div className="article-reader-empty">
          <BookOpen size={32} />
          <h1>Không thể mở bài viết</h1>
          <p>{error || "Bài viết không tồn tại hoặc chưa được xuất bản."}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="tool-page article-detail-page">
      <button className="article-back-button" type="button" onClick={onBack}>
        <ArrowLeft size={17} /> Quay lại thư viện bài viết
      </button>
      <div className="article-reader-layout">
        <article className="article-reader">
          <header className="article-reader-header">
            <span>{article.category}</span>
            <h1>{article.title}</h1>
            {article.excerpt && <p>{article.excerpt}</p>}
            <div className="article-reader-meta">
              <span><CalendarDays size={15} /> {formatArticleDate(article.published_at || article.created_at)}</span>
              <span><Eye size={15} /> {article.views.toLocaleString("vi-VN")} lượt xem</span>
              <span><Clock3 size={15} /> {readingMinutes(article.content)} phút đọc</span>
            </div>
          </header>
          <ArticleCover article={article} large />
          <div
            className="article-reader-content markdown"
            dangerouslySetInnerHTML={{ __html: articleMarkdown(article.content) }}
          />
        </article>

        <aside className="article-reader-aside">
          <section className="article-aside-card source-aside-card">
            <span className="article-aside-eyebrow"><ShieldCheck size={15} /> Căn cứ minh bạch</span>
            <h2>Nguồn tham khảo</h2>
            <p>Mở nguồn gốc để đối chiếu nội dung và thời điểm cập nhật.</p>
            {article.web_sources?.length ? (
              <div className="article-source-list">
                {article.web_sources.map((source) => (
                  <a key={`${source.id}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">
                    <span>{source.id}</span>
                    <strong>{source.title}</strong>
                    <ExternalLink size={14} />
                  </a>
                ))}
              </div>
            ) : (
              <p className="article-no-sources">Bài viết này chưa đính kèm nguồn web.</p>
            )}
          </section>
          <section className="article-aside-card article-question-card">
            <MessageSquareText size={21} />
            <h2>Bạn còn câu hỏi?</h2>
            <p>Đưa tình huống cụ thể cho trợ lý pháp lý để được phân tích theo căn cứ liên quan.</p>
            <button type="button" onClick={() => onNavigate("/")}>
              Hỏi đáp pháp luật <ArrowRight size={15} />
            </button>
          </section>
        </aside>
      </div>
    </section>
  );
}

export default function ArticlesPage({ slug, onNavigate }: ArticlesPageProps) {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState(ALL_CATEGORIES);
  const [articles, setArticles] = useState<Article[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(Boolean(slug));
  const [researchLoading, setResearchLoading] = useState(false);
  const [error, setError] = useState("");

  const loadArticles = useCallback(async (value = "") => {
    setListLoading(true);
    setError("");
    try {
      const data = await articleApi.list(value, 100);
      setArticles(data.items);
      setActiveQuery(value.trim());
      setActiveCategory(ALL_CATEGORIES);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    if (slug) return;
    void loadArticles("");
  }, [loadArticles, slug]);

  useEffect(() => {
    if (!slug) {
      setSelectedArticle(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setError("");
    articleApi.get(slug)
      .then((article) => {
        if (!cancelled) setSelectedArticle(article);
      })
      .catch((reason) => {
        if (!cancelled) {
          setSelectedArticle(null);
          setError((reason as Error).message);
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const categories = useMemo(
    () => [
      ALL_CATEGORIES,
      ...Array.from(new Set(articles.map((article) => article.category).filter(Boolean))),
    ],
    [articles],
  );
  const visibleArticles = useMemo(
    () => activeCategory === ALL_CATEGORIES
      ? articles
      : articles.filter((article) => article.category === activeCategory),
    [activeCategory, articles],
  );

  if (slug) {
    return (
      <ArticleDetail
        article={selectedArticle}
        loading={detailLoading}
        error={error}
        onBack={() => onNavigate("/bai-viet")}
        onNavigate={onNavigate}
      />
    );
  }

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    void loadArticles(query);
  };

  const runResearch = async () => {
    const researchQuery = query.trim() || activeQuery;
    if (researchQuery.length < 2) {
      setError("Hãy nhập chủ đề bạn muốn nghiên cứu.");
      return;
    }
    setResearchLoading(true);
    setError("");
    try {
      const data = await articleApi.webSearch(researchQuery);
      setResearch({
        summary: data.summary,
        sources: data.sources,
        providers: data.providers_used,
        warnings: data.search_warnings,
        googleSearchEntryPoint: data.google_search_entry_point || "",
      });
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setResearchLoading(false);
    }
  };

  return (
    <section className="tool-page articles-hub">
      <header className="articles-hero">
        <div>
          <span className="articles-kicker"><BookOpen size={15} /> Không gian kiến thức</span>
          <h1>Bài viết pháp luật</h1>
          <p>Cập nhật kiến thức, hướng dẫn thực tiễn và những thay đổi pháp lý đáng chú ý với nguồn dẫn có thể kiểm tra.</p>
        </div>
        <div className="articles-hero-stat">
          <strong>{articles.length}</strong>
          <span>bài viết đang có</span>
          <small>Cập nhật hằng ngày</small>
        </div>
      </header>

      {error && <InlineError message={error} onClose={() => setError("")} />}

      {categories.length > 1 && (
        <nav className="article-category-tabs" aria-label="Lọc bài viết theo chuyên mục">
          {categories.map((category) => (
            <button
              className={activeCategory === category ? "active" : ""}
              key={category}
              type="button"
              onClick={() => setActiveCategory(category)}
            >
              {category}
            </button>
          ))}
        </nav>
      )}

      {research && (
        <section className="article-research-result">
          <header>
            <div>
              <span><Sparkles size={15} /> Nghiên cứu theo yêu cầu</span>
              <h2>Kết quả tổng hợp từ nguồn công khai</h2>
            </div>
            <button type="button" onClick={() => setResearch(null)} aria-label="Đóng kết quả nghiên cứu">
              <X size={17} />
            </button>
          </header>
          {research.warnings.length > 0 && <p className="article-research-warning">{research.warnings.join(" · ")}</p>}
          <div
            className="article-research-copy markdown"
            dangerouslySetInnerHTML={{ __html: articleMarkdown(research.summary) }}
          />
          <div className="article-research-sources">
            {research.sources.map((source) => (
              <a key={`${source.id}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">
                <span>{source.id}</span>
                <strong>{source.title}</strong>
                <ExternalLink size={14} />
              </a>
            ))}
          </div>
          {research.googleSearchEntryPoint && (
            <iframe
              className="article-google-search-entry"
              title="Thông tin đối chiếu từ Google Search"
              sandbox="allow-popups"
              referrerPolicy="no-referrer"
              srcDoc={research.googleSearchEntryPoint}
            />
          )}
          {research.providers.length > 0 && (
            <small>Nguồn tìm kiếm: {research.providers.map((provider) => provider === "google" ? "Google" : "Tavily").join(" + ")}</small>
          )}
        </section>
      )}

      <div className="articles-layout">
        <main className="article-feed">
          <header className="article-feed-heading">
            <div>
              <span>Bài viết mới nhất</span>
              <h2>{activeQuery ? `Kết quả cho “${activeQuery}”` : "Kiến thức pháp lý dành cho bạn"}</h2>
            </div>
            <small>{visibleArticles.length} kết quả</small>
          </header>

          {listLoading ? (
            <div className="article-list-loading" aria-label="Đang tải bài viết" aria-busy="true">
              {[0, 1, 2].map((item) => <span key={item} />)}
            </div>
          ) : visibleArticles.length > 0 ? (
            <div className="article-magazine-list">
              {visibleArticles.map((article) => (
                <article className="article-magazine-card" key={article.id}>
                  <button
                    className="article-cover-button"
                    type="button"
                    onClick={() => onNavigate(`/bai-viet/${encodeURIComponent(article.slug)}`)}
                    aria-label={`Đọc bài: ${article.title}`}
                  >
                    <ArticleCover article={article} />
                  </button>
                  <div className="article-card-copy">
                    <span className="article-card-category">{article.category}</span>
                    <button
                      className="article-title-button"
                      type="button"
                      onClick={() => onNavigate(`/bai-viet/${encodeURIComponent(article.slug)}`)}
                    >
                      <h3>{article.title}</h3>
                    </button>
                    <p>{article.excerpt || "Mở bài viết để xem nội dung phân tích và các nguồn tham khảo liên quan."}</p>
                    <footer>
                      <span><CalendarDays size={14} /> {formatArticleDate(article.published_at || article.created_at)}</span>
                      <span><Eye size={14} /> {article.views.toLocaleString("vi-VN")} lượt xem</span>
                      <button type="button" onClick={() => onNavigate(`/bai-viet/${encodeURIComponent(article.slug)}`)}>
                        Đọc bài <ArrowRight size={14} />
                      </button>
                    </footer>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="article-feed-empty">
              <BookOpen size={34} />
              <h3>{activeQuery ? "Chưa tìm thấy bài viết phù hợp" : "Bản tin pháp luật đang được chuẩn bị"}</h3>
              <p>
                {activeQuery
                  ? "Bạn có thể đổi từ khóa hoặc yêu cầu AI nghiên cứu chủ đề này từ các nguồn công khai."
                  : "Bài viết đầu tiên sẽ xuất hiện sau lịch cập nhật gần nhất. Bạn vẫn có thể nghiên cứu ngay một chủ đề cụ thể."}
              </p>
              {(query.trim() || activeQuery) && (
                <button type="button" onClick={() => void runResearch()} disabled={researchLoading}>
                  <Sparkles size={16} /> {researchLoading ? "Đang nghiên cứu…" : "Nghiên cứu chủ đề này"}
                </button>
              )}
            </div>
          )}
        </main>

        <aside className="article-sidebar">
          <form className="article-search-card" onSubmit={submitSearch}>
            <label htmlFor="article-search">Tìm trong thư viện</label>
            <div>
              <Search size={19} />
              <input
                id="article-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm kiếm bài viết…"
              />
              {query && (
                <button type="button" onClick={() => { setQuery(""); void loadArticles(""); }} aria-label="Xóa từ khóa">
                  <X size={15} />
                </button>
              )}
            </div>
            <button type="submit" disabled={listLoading}>Tìm bài viết</button>
          </form>

          <section className="article-ai-card">
            <span><Sparkles size={16} /> Nghiên cứu bằng AI</span>
            <h2>Chưa có bài bạn cần?</h2>
            <p>VLegal có thể tổng hợp một chủ đề mới từ các nguồn công khai và trình bày kèm dẫn nguồn.</p>
            <button type="button" onClick={() => void runResearch()} disabled={researchLoading}>
              {researchLoading ? "Đang tổng hợp…" : "Nghiên cứu chủ đề"}
              {!researchLoading && <ArrowRight size={15} />}
            </button>
          </section>

          <section className="article-quick-actions">
            <h2>Công cụ pháp lý</h2>
            <button type="button" onClick={() => onNavigate("/")}>
              <MessageSquareText size={19} />
              <span><strong>Hỏi đáp pháp luật</strong><small>Phân tích tình huống với căn cứ liên quan.</small></span>
              <ArrowRight size={15} />
            </button>
            <button type="button" onClick={() => onNavigate("/tao-hop-dong")}>
              <FilePenLine size={19} />
              <span><strong>Tạo hợp đồng</strong><small>Soạn thảo theo nhu cầu và điều kiện cụ thể.</small></span>
              <ArrowRight size={15} />
            </button>
            <button type="button" onClick={() => onNavigate("/review-hop-dong")}>
              <ClipboardCheck size={19} />
              <span><strong>Review hợp đồng</strong><small>Nhận diện rủi ro và điều khoản bất lợi.</small></span>
              <ArrowRight size={15} />
            </button>
            <button type="button" onClick={() => onNavigate("/so-sanh-hop-dong")}>
              <FileText size={19} />
              <span><strong>So sánh hợp đồng</strong><small>Làm rõ nội dung thêm, xóa và chỉnh sửa.</small></span>
              <ArrowRight size={15} />
            </button>
          </section>
        </aside>
      </div>
    </section>
  );
}
