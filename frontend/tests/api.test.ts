import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  articleApi,
  askLegalQuestion,
  authApi,
  conversationApi,
  legalDocumentApi,
  uploadChatAttachment,
} from "../src/api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(response: Response | (() => Promise<Response>)) {
  const fetchMock = vi.fn();
  if (response instanceof Response) fetchMock.mockResolvedValue(response);
  else fetchMock.mockImplementation(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function requestBody(fetchMock: ReturnType<typeof vi.fn>) {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(String(init.body));
}

function requestUrl(fetchMock: ReturnType<typeof vi.fn>) {
  return new URL(String(fetchMock.mock.calls[0][0]));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API request construction", () => {
  it("builds a return URL for Google login", () => {
    const url = new URL(authApi.loginUrl("/bai-viet/moi?tab=all"));

    expect(url.pathname).toBe("/api/auth/google/login");
    expect(url.searchParams.get("return_to")).toBe("/bai-viet/moi?tab=all");
  });

  it("sends chat attachment tokens but never attachment metadata", async () => {
    const fetchMock = mockFetch(jsonResponse({ answer: "Đã nhận." }));

    await askLegalQuestion("Kiểm tra tài liệu này", "conversation-7", {
      regenerateFromMessageId: "message-6",
      attachments: [
        {
          token: "upload-token-1",
          filename: "hop-dong.pdf",
          content_type: "application/pdf",
          kind: "document",
          size_bytes: 1234,
          truncated: false,
        },
        {
          filename: "local-only.txt",
          content_type: "text/plain",
          kind: "document",
          size_bytes: 12,
          truncated: false,
        },
      ],
    });

    expect(requestUrl(fetchMock).pathname).toBe("/api/chat");
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ method: "POST", credentials: "include" }));
    expect(await requestBody(fetchMock)).toEqual({
      message: "Kiểm tra tài liệu này",
      conversation_id: "conversation-7",
      regenerate_from_message_id: "message-6",
      attachments: [{ token: "upload-token-1" }],
    });
  });

  it("encodes article search parameters", async () => {
    const fetchMock = mockFetch(jsonResponse({ items: [], total: 0, offset: 10, limit: 15, has_more: false }));

    await articleApi.list("lao động & tiền lương", 15, 10);

    const url = requestUrl(fetchMock);
    expect(url.pathname).toBe("/api/articles");
    expect(url.searchParams.get("q")).toBe("lao động & tiền lương");
    expect(url.searchParams.get("limit")).toBe("15");
    expect(url.searchParams.get("offset")).toBe("10");
  });

  it("encodes legal document filters and pagination", async () => {
    const fetchMock = mockFetch(jsonResponse({ sections: [] }));

    await legalDocumentApi.get("45/2019/QH14", "Điều 34 khoản 1", 2, 25);

    const url = requestUrl(fetchMock);
    expect(url.pathname).toBe("/api/laws/detail");
    expect(url.searchParams.get("code")).toBe("45/2019/QH14");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("citation")).toBe("Điều 34 khoản 1");
  });

  it("uses FormData without forcing a JSON content type for attachments", async () => {
    const fetchMock = mockFetch(jsonResponse({ token: "token-1" }));
    const file = new File(["nội dung"], "ghi-chu.txt", { type: "text/plain" });

    await uploadChatAttachment(file);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({});
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("attachment")).toBe(file);
  });
});

describe("API response handling", () => {
  it("normalizes stored messages while discarding malformed records", async () => {
    mockFetch(jsonResponse({
      conversation: { id: "conversation-1", title: "Lao động" },
      messages: [
        null,
        { role: "system", content: "not shown" },
        {
          role: "ASSISTANT",
          content: "Câu trả lời",
          sources: [
            null,
            {
              citation: "Điều 34",
              score: "not-a-number",
              reasons: ["hybrid", 1],
              source_url: "https://vanban.chinhphu.vn/example",
            },
          ],
          verification: {
            checked: 1,
            all_current: 0,
            note: 12,
            items: [{ code: "45/2019/QH14", status: "INVALID", index_updated: "yes" }],
          },
          attachments: [
            { filename: "scan.png", kind: "image", size_bytes: 20, truncated: 1 },
            "invalid",
          ],
          feedback_rating: "good",
        },
      ],
    }));

    const result = await conversationApi.get("conversation-1");

    expect(result.messages).toEqual([
      expect.objectContaining({
        id: "conversation-1-2",
        conversation_id: "conversation-1",
        role: "assistant",
        content: "Câu trả lời",
        feedback_rating: "good",
        sources: [{
          source_id: "S2",
          score: 0,
          chunk_type: "",
          citation: "Điều 34",
          title: "",
          text: "",
          reasons: ["hybrid"],
          doc_id: null,
          source_url: "https://vanban.chinhphu.vn/example",
          document_code: null,
        }],
        verification: expect.objectContaining({
          checked: true,
          all_current: false,
          note: "",
          items: [expect.objectContaining({ status: "UNKNOWN", index_updated: true })],
        }),
        attachments: [expect.objectContaining({
          filename: "scan.png",
          kind: "image",
          content_type: "application/octet-stream",
          size_bytes: 20,
          truncated: true,
        })],
      }),
    ]);
  });

  it("returns undefined for successful no-content endpoints", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await expect(authApi.logout()).resolves.toBeUndefined();
    expect(requestUrl(fetchMock).pathname).toBe("/api/auth/logout");
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ method: "POST", credentials: "include" }));
  });

  it("maps unauthenticated API failures to a helpful Vietnamese message", async () => {
    mockFetch(jsonResponse({}, 401));

    await expect(authApi.me()).rejects.toEqual(
      expect.objectContaining({
        message: "Vui lòng đăng nhập để tiếp tục.",
        status: 401,
      }),
    );
  });

  it("preserves a safe API error detail and error code", async () => {
    mockFetch(jsonResponse({ detail: "Tệp vượt quá dung lượng cho phép.", code: "FILE_TOO_LARGE" }, 422));

    try {
      await uploadChatAttachment(new File(["x"], "too-large.txt"));
      throw new Error("Expected upload to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        message: "Tệp vượt quá dung lượng cho phép.",
        status: 422,
        code: "FILE_TOO_LARGE",
      });
    }
  });

  it("turns network failures into the application availability error", async () => {
    mockFetch(async () => Promise.reject(new TypeError("Network unavailable")));

    await expect(articleApi.list()).rejects.toMatchObject({
      message: "Tính năng này đang tạm gián đoạn. Vui lòng thử lại sau.",
      status: 0,
      code: "UNAVAILABLE",
    });
  });
});
