# Báo cáo review code và kiểm thử AI

- Ngày review: 2026-07-23
- Phạm vi: `app/services/ai.py`, cấu hình Gemini, readiness/lifecycle, các call site hỏi đáp pháp lý, hợp đồng, bài viết, memory, freshness và worker
- Hình thức: static review, unit/integration test bằng mock HTTP; không gọi Vertex AI thật và không sử dụng credential thật
- Kết luận: lớp kết nối Vertex AI có nền tảng tốt, nhưng chưa nên coi output AI là an toàn cho nghiệp vụ pháp lý có mức rủi ro cao trước khi xử lý các mục P0 bên dưới

## 1. Tóm tắt điều hành

Các điểm làm tốt:

- Credential được lấy qua service account hoặc ADC, access token không đưa ra frontend.
- Refresh token được khóa để tránh nhiều coroutine refresh cùng lúc.
- Có giới hạn đồng thời chung cho generation và Google Search grounding.
- Có retry cho lỗi mạng, `408`, `429`, `5xx`; mặc định ba lần gọi tương ứng hai lần retry.
- Structured output gửi `responseMimeType=application/json` và `responseSchema` đúng hướng dẫn Vertex AI.
- HTTP client dùng connection pool và chỉ tự đóng khi service sở hữu client.

Các rủi ro chính:

| ID | Mức độ | Phát hiện | Trạng thái test |
|---|---|---|---|
| AI-01 | Cao | Vẫn gọi AI khi retrieval không trả nguồn pháp lý | `xfail` |
| AI-02 | Cao | `complete_json()` không validate dữ liệu đã parse theo schema | `xfail`, gồm required/type/enum/range/extra/NaN/Infinity |
| AI-03 | Cao | Không kiểm citation đầu ra và chưa có lớp chống indirect prompt injection | Chưa có guardrail production |
| AI-04 | Cao | `legal_search_require_both` chấp nhận Google Search “thành công” nhưng không có evidence | `xfail` |
| AI-05 | Trung bình-cao | Nội dung dang dở/bị chặn với `finishReason != STOP` vẫn được chấp nhận | `xfail` |
| AI-06 | Trung bình | Readiness có cả false-negative ADC và false-positive credential file | `xfail` |
| AI-07 | Trung bình | Lỗi malformed candidate làm lọt `AttributeError` thay vì `GeminiError` | `xfail` |
| AI-08 | Trung bình | Handler trả nguyên chi tiết lỗi provider/đường dẫn nội bộ cho client | `xfail` |
| AI-09 | Trung bình | Dữ liệu pháp lý/hợp đồng được gửi ra Vertex AI chưa có redaction/policy gate | Cần quyết định sản phẩm |
| AI-10 | Trung bình | Model mặc định `gemini-2.5-flash` sắp đến hạn retirement | Cần kế hoạch migration |
| AI-11 | Thấp-trung bình | Một số vấn đề vận hành: DB lock qua network call, worker nuốt lỗi, shutdown thiếu `finally` | Chưa xử lý |

## 2. Phát hiện chi tiết

### AI-01 — AI có thể trả lời khi không có nguồn pháp lý

Mức độ: Cao

Bằng chứng:

- `app/api.py:239-242` trả `checked=true, all_current=true` khi retrieval rỗng.
- Chat sau đó vẫn gọi Gemini tại `app/api.py:586`.
- Draft/review/compare hợp đồng cũng tiếp tục với context nguồn rỗng.

Tác động:

- Model có thể tự sinh căn cứ hoặc kết luận pháp lý không được kiểm chứng.
- Trạng thái `all_current=true` gây hiểu nhầm rằng đã xác minh hiệu lực thành công.

Khuyến nghị:

1. Trả `409` hoặc `422` nếu không có nguồn hợp lệ.
2. Không gọi AI và không ghi message/artifact trong nhánh này.
3. Phân biệt rõ `no_sources`, `verification_failed` và `all_current`.

Test hồi quy: `tests/test_ai_guardrails.py::test_legal_ai_rejects_request_without_retrieved_sources`.

### AI-02 — Structured output không được validate tại trust boundary

Mức độ: Cao

Bằng chứng:

- `app/services/ai.py:309-332` chỉ chạy `json.loads()` và kiểm tra kết quả là `dict`.
- Không kiểm `required`, kiểu dữ liệu, enum, min/max hoặc `additionalProperties`.
- Python `json.loads()` mặc định còn chấp nhận `NaN` và `Infinity`.
- Các call site dùng trực tiếp `verdict["status"]`, `result["summary"]` và ghi DB.

Tác động:

- Verdict hiệu lực sai enum có thể đi vào pipeline cập nhật luật.
- Thiếu key gây `KeyError`/500 sau khi đã tiêu tốn request AI.
- Extra field từ model có thể xung đột field do server quản lý; ví dụ cách merge dictionary ở response hợp đồng cần được whitelist.

Structured output của Vertex giúp model tuân theo schema, nhưng response từ dịch vụ ngoài vẫn phải được validate cục bộ. Google mô tả `responseSchema` là một tập con OpenAPI, không phải sự thay thế cho validation tại application boundary: [GenerationConfig reference](https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/GenerationConfig).

Khuyến nghị:

1. Từ chối hằng số JSON không hữu hạn bằng `parse_constant`.
2. Validate bằng Pydantic model riêng cho verdict/review/compare hoặc JSON Schema validator.
3. Bật chính sách extra field `forbid`.
4. Chỉ trả/ghi các field đã whitelist.

Test hồi quy: nhóm `test_complete_json_validates_parsed_object_against_schema` trong `tests/test_ai.py`.

### AI-03 — Citation và prompt injection mới chỉ được kiểm soát bằng prompt

Mức độ: Cao

Bằng chứng:

- `LEGAL_SYSTEM_PROMPT` và prompt bài viết yêu cầu `[S1]`, `[W1]`, nhưng không có post-validator.
- Raw chunk/raw web content được ghép trực tiếp vào prompt.
- Output không citation, citation ngoài tập nguồn như `[S99]`, hoặc nội dung tuân theo chỉ dẫn độc hại từ source vẫn được chấp nhận và có thể persist.

Tác động:

- Citation có vẻ hợp lệ về hình thức nhưng không ánh xạ tới nguồn thật.
- Nội dung website hoặc tài liệu có thể chèn chỉ dẫn làm lệch system intent.

Khuyến nghị:

1. Đánh dấu source content là dữ liệu không tin cậy bằng delimiter rõ ràng.
2. Parse toàn bộ citation đầu ra và chỉ cho phép ID nguồn đã cấp.
3. Bắt buộc mỗi kết luận pháp lý có ít nhất một citation hợp lệ; nếu không, repair một lần hoặc từ chối.
4. Không cho nội dung source điều khiển tool/config/system instruction.
5. Bổ sung adversarial corpus test riêng cho prompt injection.

### AI-04 — “Require both” chưa yêu cầu evidence từ cả hai provider

Mức độ: Cao

Bằng chứng:

- `app/services/freshness.py:186-204` chỉ coi provider thất bại khi có exception.
- Google Search trả payload hợp lệ nhưng `results=[]` không được thêm vào `search_failures`.
- Khi Tavily có kết quả, freshness vẫn tiếp tục dù cấu hình `legal_search_require_both=true`.

Tác động:

- Yêu cầu đối chiếu Tavily và Google Search có thể bị vượt qua về mặt ngữ nghĩa.
- Báo cáo xác minh không thể chứng minh cả hai provider thực sự cung cấp evidence.

Khuyến nghị:

- Với chế độ require-both, coi `results=[]`, metadata malformed hoặc không có grounding chunk hợp lệ là provider failure.
- Lưu `providers_consulted` và `providers_with_evidence` riêng trong verification payload.

Test hồi quy: `tests/test_ai_guardrails.py::test_freshness_requires_evidence_from_both_search_providers`.

### AI-05 — Không kiểm tra `finishReason` khi có text

Mức độ: Trung bình-cao

Bằng chứng:

- `app/services/ai.py:57-74` chỉ dùng `finishReason` khi text rỗng.
- Text một phần với `MAX_TOKENS`, `SAFETY` hoặc `RECITATION` vẫn được trả như output hoàn chỉnh.

Tác động:

- Hợp đồng/tóm tắt có thể bị cắt giữa chừng rồi vẫn được lưu.
- Safety-blocked partial text có thể đi qua handler bình thường.

Khuyến nghị:

- Xây whitelist `STOP` cho text completion thông thường.
- Với `MAX_TOKENS`, trả trạng thái incomplete hoặc retry có kiểm soát; không persist như kết quả hoàn tất.
- Ánh xạ các finish reason bị chặn sang `GeminiError` an toàn.

Test hồi quy: `test_response_text_rejects_incomplete_or_blocked_finish_reason`.

### AI-06 — Readiness không nhất quán với runtime credential loading

Mức độ: Trung bình

Bằng chứng:

- `app/core/config.py:179-182` yêu cầu `GEMINI_PROJECT_ID` khi dùng ADC.
- `GeminiService._load_credentials()` lại hỗ trợ project ID do ADC tự phát hiện.
- Ở chiều ngược lại, readiness chỉ kiểm tra file tồn tại; file text/Python bất kỳ cũng được coi là credential sẵn sàng.
- Readiness chưa phản ánh Tavily khi freshness bắt buộc.

Khuyến nghị:

- Tách `configured` khỏi `ready`.
- Khi startup/readiness, load/parse credential một lần có cache, nhưng không trả chi tiết secret.
- Nếu `require_freshness_check=true`, kiểm cả Tavily và dependency Google grounding.

### AI-07 — Malformed success payload có thể trở thành lỗi 500

Mức độ: Trung bình

Bằng chứng:

- `_response_text()` giả định `candidates[0]` là dictionary.
- `{"candidates":[null]}` gây `AttributeError`, không đi qua `GeminiError` handler.

Khuyến nghị:

- Validate candidate/content/parts bằng type guard trước khi truy cập.
- Mọi lỗi response contract phải được chuẩn hóa thành `GeminiError`.

### AI-08 — Rò rỉ chi tiết lỗi nội bộ

Mức độ: Trung bình

Bằng chứng:

- `app/main.py:87-92` trả nguyên `str(exc)` về client.
- Nội dung này có thể chứa đường dẫn credential, project/model hoặc response detail của provider.

Khuyến nghị:

- Client chỉ nhận mã lỗi và thông báo chung.
- Chi tiết đầy đủ chỉ ghi server log gắn request ID; lọc token, path và project nhạy cảm.

Test hồi quy: `test_gemini_error_handler_does_not_expose_internal_details`.

### AI-09 — Chưa có data-classification/redaction trước Vertex AI

Mức độ: Trung bình, có thể nâng thành Cao tùy chính sách dữ liệu

Bằng chứng:

- Câu hỏi, history, summary, hợp đồng dài và source text được gửi tới Vertex.
- Conversation memory tiếp tục gửi transcript đã giải mã để tóm tắt.

Khuyến nghị:

- Xác định rõ loại dữ liệu được phép gửi ra dịch vụ model.
- Redact secret/PII có cấu trúc trước khi gọi AI.
- Có policy/consent cho tài liệu hợp đồng nhạy cảm.
- Log metadata/usage, không log prompt thô.

### AI-10 — Cần kế hoạch model migration trước 2026-10-16

Mức độ: Trung bình

Default hiện là `gemini-2.5-flash`. Release notes mới nhất của Google cập nhật retirement các model Gemini 2.5, gồm 2.5 Flash, sang ngày 2026-10-16: [Vertex AI release notes](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/release-notes).

Tại ngày review 2026-07-23, thời gian chuẩn bị migration còn dưới ba tháng.

Khuyến nghị:

1. Không đổi model trực tiếp nếu chưa benchmark.
2. Chạy bộ eval pháp lý/contract/freshness trên model kế nhiệm còn được hỗ trợ.
3. So sánh structured output, Google grounding, latency, cost và citation adherence.
4. Chốt model mới bằng biến môi trường, có canary và rollback.

### AI-11 — Các vấn đề vận hành phụ

Mức độ: Thấp-trung bình

- `ConversationMemoryService.refresh()` giữ advisory transaction lock và DB session trong suốt Gemini + embedding call.
- Worker tăng biến `failed` nhưng không log nguyên nhân exception.
- Lifespan shutdown gọi `retrieval.close()` rồi mới `ai.close()` mà không có `try/finally`.
- Retry hiện dùng exponential backoff đúng hướng, nhưng chưa có jitter và cho phép cấu hình tới sáu lần gọi. Google khuyến nghị tối thiểu một giây, exponential backoff và không quá hai lần retry: [Vertex AI API errors](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors).

## 3. Bộ test AI được tạo lại

### Trước review

- `tests/test_ai.py`: 5 test.
- Chủ yếu bao phủ happy path structured output, credential missing, ADC và Google grounding payload.

### Sau review

Files:

- `tests/test_ai.py`
- `tests/test_ai_guardrails.py`

Ma trận đã bao phủ:

- Chuyển JSON Schema sang Vertex schema, nullable/nested/enum/range và không mutate input.
- Parse response parts, bỏ thought, empty candidate/prompt feedback.
- Service-account, ADC, project override, lỗi file, lỗi ADC và concurrent initialization.
- Token cache, refresh, refresh failure, empty token và concurrent refresh.
- URL/payload/header structured output.
- Blank prompt/query.
- Retry toàn bộ `408/429/500/502/503/504`.
- Retry lỗi transport, exhaustion và backoff.
- `400` không retry; `401` refresh rồi retry.
- Invalid JSON/non-object HTTP 200.
- Fenced JSON, invalid JSON, non-object JSON.
- Google Search grounding payload.
- Semaphore và lifecycle HTTP client.
- Guardrails không nguồn, sanitized error và require-both evidence.

Các case `xfail(strict=True)` là lỗi đã tái hiện, không phải test bị bỏ qua ngẫu nhiên. Khi production code được sửa, chúng sẽ thành `XPASS` và làm CI báo để đội ngũ chuyển test về trạng thái pass bình thường.

Kết quả riêng AI tại thời điểm lập report:

```text
42 passed, 15 xfailed
```

Không có network call thật; toàn bộ Vertex HTTP được mô phỏng bằng `httpx.MockTransport`.

## 4. Kết quả regression

Lệnh chuẩn trên máy hiện tại:

```powershell
$env:PYTHONPATH='F:\VlegalAI'
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest tests/test_ai.py tests/test_ai_guardrails.py -q -rxX
```

Không nên dùng Python hệ thống vì môi trường đó không khớp dependency/runtime của dự án.

Client key-value store cũ và test hạ tầng riêng đã được gỡ vì ứng dụng không còn sử dụng. Regression hiện không cần loại riêng test hạ tầng đó:

```text
67 passed, 15 xfailed
```

`compileall` và `git diff --check` đều thành công; các cảnh báo LF/CRLF là cảnh báo line-ending của worktree hiện hữu.

## 5. Kế hoạch xử lý đề xuất

### P0 — Trước khi coi output là an toàn cho production pháp lý

1. Fail closed khi không có nguồn.
2. Validate structured output cục bộ, gồm `NaN`/`Infinity`.
3. Reject/handle mọi non-`STOP` finish reason.
4. Bắt buộc citation phải ánh xạ nguồn thật.
5. Require evidence thực tế từ cả Tavily và Google khi cấu hình require-both.

### P1 — Sprint kế tiếp

1. Sửa readiness credential/dependency.
2. Sanitize lỗi trả client.
3. Thiết kế chống indirect prompt injection.
4. Chốt policy dữ liệu/redaction/consent.
5. Bổ sung integration test endpoint để bảo đảm output lỗi không được persist.

### P2 — Vận hành và lifecycle

1. Benchmark model kế nhiệm trước retirement 2026-10-16.
2. Thêm observability: latency, retry count, finish reason, token usage, model version và grounding coverage.
3. Log lỗi worker có request/document identifier an toàn.
4. Thu hẹp thời gian giữ DB transaction lock và bảo đảm AI client luôn đóng khi shutdown.

## 6. Quyết định review

Trạng thái đề xuất: **Needs remediation**.

Lớp transport/auth/retry đủ tốt để tiếp tục phát triển và staging. Tuy nhiên, ba trust-boundary quan trọng — nguồn pháp lý, structured output và citation — hiện vẫn phụ thuộc quá nhiều vào hành vi của model. Cần hoàn thành P0 trước khi dùng kết quả để đưa ra hoặc lưu trữ kết luận pháp lý có độ tin cậy cao.
