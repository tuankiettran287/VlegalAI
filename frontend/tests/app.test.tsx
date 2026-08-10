import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPage, CitationMarkdown, SourcePanel } from "../src/App";
import { askLegalQuestion, conversationApi } from "../src/api";
import type { Source } from "../src/types";

vi.mock("../src/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api")>();
  return {
    ...actual,
    askLegalQuestion: vi.fn(),
    conversationApi: {
      ...actual.conversationApi,
      list: vi.fn(),
    },
  };
});

const source: Source = {
  source_id: "S1",
  score: 0.99,
  chunk_type: "article",
  citation: "Điều 12 Bộ luật Lao động",
  title: "Bộ luật Lao động",
  text: "Nội dung căn cứ pháp lý.",
  reasons: [],
  source_url: "https://vanban.chinhphu.vn/bo-luat-lao-dong",
};

afterEach(() => vi.restoreAllMocks());

describe("SourcePanel", () => {
  it("opens official source links in a new protected tab", () => {
    render(<SourcePanel sources={[source]} />);

    fireEvent.click(screen.getByText("1 căn cứ được sử dụng"));

    expect(screen.getByRole("link", { name: "Mở văn bản gốc: Điều 12 Bộ luật Lao động" }))
      .toHaveAttribute("href", source.source_url);
    expect(screen.getByRole("link", { name: "Mở văn bản gốc: Điều 12 Bộ luật Lao động" }))
      .toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "Mở văn bản gốc: Điều 12 Bộ luật Lao động" }))
      .toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not render non-HTTPS source links", () => {
    render(<SourcePanel sources={[{ ...source, source_url: "javascript:alert(1)" }]} />);

    fireEvent.click(screen.getByText("1 căn cứ được sử dụng"));

    expect(screen.queryByRole("link", { name: /Mở văn bản gốc/ })).not.toBeInTheDocument();
  });
});

describe("CitationMarkdown", () => {
  it("shows source context on hover and links inline citations to the official document", () => {
    render(<CitationMarkdown text="Áp dụng theo [S1]." sources={[source]} />);

    const citation = screen.getByRole("link", {
      name: "Mở căn cứ S1: Điều 12 Bộ luật Lao động",
    });
    expect(citation).toHaveTextContent("[S1]");
    expect(citation).toHaveAttribute("href", source.source_url);
    expect(citation).toHaveAttribute("target", "_blank");
    expect(citation).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Điều 12 Bộ luật Lao động");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Nội dung căn cứ pháp lý.");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Bấm để mở văn bản gốc");
  });

  it("still shows a tooltip when a citation has no verified URL", () => {
    render(<CitationMarkdown text="Áp dụng theo [S1]." sources={[{ ...source, source_url: null }]} />);

    expect(screen.getByRole("button", { name: "Xem thông tin căn cứ S1" }))
      .toHaveTextContent("[S1]");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Nguồn này chưa có liên kết chính thức");
  });
});

describe("ChatPage", () => {
  it("sends the typed question and renders the returned answer", async () => {
    vi.mocked(conversationApi.list).mockResolvedValue([]);
    vi.mocked(askLegalQuestion).mockResolvedValue({
      conversation_id: "conversation-1",
      message_id: "answer-1",
      replaces_message_id: null,
      answer: "Bạn cần báo trước theo thời hạn áp dụng.",
      sources: [],
      verification: { checked: false, all_current: false, items: [], note: "" },
      temporary: true,
      cache_hit: false,
      cache_similarity: null,
      cache_mode: "miss",
    });
    const onConversationChange = vi.fn();

    render(
      <ChatPage
        onNavigate={vi.fn()}
        userName="Nam"
        initialConversationId={null}
        onActiveConversationChange={onConversationChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Tình huống cần tư vấn"), {
      target: { value: "Tôi cần báo trước bao lâu khi nghỉ việc?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));

    await waitFor(() => expect(askLegalQuestion).toHaveBeenCalledWith(
      "Tôi cần báo trước bao lâu khi nghỉ việc?",
      null,
      { attachments: [] },
    ));
    expect(await screen.findByText("Bạn cần báo trước theo thời hạn áp dụng.")).toBeInTheDocument();
    expect(onConversationChange).toHaveBeenCalledWith("conversation-1");
  });
});
