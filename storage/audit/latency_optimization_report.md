# VLegal AI LaborCare — latency optimization report

Ngày đo: 2026-07-18 (Asia/Saigon). Đây là báo cáo đo trên máy local hiện tại; không có số nào được suy diễn thành latency của Qwen3/SageMaker.

## 1. Luồng xử lý trước tối ưu và reconnaissance

Endpoint hỏi đáp thật là `POST /api/chat`, khai báo `async def` tại `app/api.py:418-430`. `ChatRequest` chỉ có `message`, `conversation_id`, `history` (`app/schemas.py:90-93`), không có mode theo từng request. Mode thực tế lấy từ `Settings.retriever_backend` với các giá trị `rag`, `graphrag`, `hybrid_rag`, `local_graphrag` (`app/core/config.py:57`); vì vậy profiler khởi tạo store tương ứng trực tiếp thay vì giả định frontend đã đổi backend của một request.

Luồng tuần tự/ song song của một câu hỏi:

```text
POST /api/chat — async def                                      app/api.py:418-430
├─ optional_user
│  └─ có token: PostgreSQL db.get(User, user_id)                app/auth.py:80-100
├─ khách: Redis transactional rate-limit pipeline               app/api.py:433-439
│                                                               app/services/guest_limit.py:28-38
├─ người dùng đăng nhập: ghi USER message + COMMIT PostgreSQL    app/api.py:440-470
├─ await _legal_sources(...)                                    app/api.py:477
│  ├─ await retrieval.retrieve(query)                           app/api.py:223
│  │  └─ sync vendor store chạy trong FastAPI threadpool        app/services/retrieval.py:58-61
│  │     ├─ rag: Qdrant query_points                            app/external_graphrag.py:432-438
│  │     ├─ graphrag: Neo4j full-text seed                      app/external_graphrag.py:550-573
│  │     │  ├─ ancestor/outgoing/incoming traversal, 1..4 hop   app/external_graphrag.py:604-635
│  │     │  └─ fetch chunks, LIMIT 250                          app/external_graphrag.py:675-706
│  │     └─ hybrid_rag: Qdrant seed                             app/external_graphrag.py:837-844
│  │        ├─ Neo4j ancestor/outgoing/incoming traversal       app/external_graphrag.py:854-885
│  │        └─ Neo4j fetch chunks, LIMIT 250                    app/external_graphrag.py:925-956
│  └─ await freshness.verify_sources(sources)                   app/api.py:227
│     ├─ các luật chạy gather, giới hạn concurrency=4           app/services/freshness.py:65,87
│     ├─ PostgreSQL cache hit nếu verified_at trong TTL          app/services/freshness.py:112-123
│     ├─ Redis distributed lock                                 app/services/freshness.py:125-150
│     └─ cache miss:
│        ├─ await Tavily search                                  app/services/freshness.py:153-162
│        │  └─ HTTP POST thật                                   app/services/tavily.py:46
│        ├─ await LLM complete_json để phán quyết hiệu lực       app/services/freshness.py:180-189
│        ├─ có thể index văn bản thay thế/sửa đổi                app/services/freshness.py:219-235
│        └─ COMMIT PostgreSQL                                   app/services/freshness.py:236
│     Nếu index đổi: retrieval + verify chạy lại                app/api.py:230-232
├─ await LLM sinh câu trả lời cuối                              app/api.py:478-484
└─ người dùng đăng nhập: ghi ASSISTANT message + COMMIT          app/api.py:486-499
```

Kết luận sync/async:

- Qdrant và Neo4j dùng SDK đồng bộ: `QdrantClient` và `GraphDatabase.driver` tại `app/external_graphrag.py:11-12,137-145`. Không có `AsyncQdrantClient`/`AsyncGraphDatabase`. Tuy nhiên endpoint không gọi trực tiếp chúng trên event loop: constructor, `retrieve`, `stats`, `close` đều được bọc `run_in_threadpool` tại `app/services/retrieval.py:40-69`. Vì vậy không phát hiện blocking vendor SDK trực tiếp trên event loop ở request retrieval hiện tại.
- Tavily dùng `httpx.AsyncClient` và `await` thật (`app/services/tavily.py:20,46,60`). Redis dùng `redis.asyncio.Redis` (`app/services/freshness.py:9,64`; `app/services/guest_limit.py:5,23`). PostgreSQL dùng SQLAlchemy `AsyncSession`/`asyncpg` (`app/db.py:5,12-25`).
- Qwen production trong repo không gọi SageMaker. Nó nạp checkpoint local và chạy `model.generate` trong `asyncio.to_thread` (`app/services/ai.py:159,195-201`). `rg` không tìm thấy `boto3`, `sagemaker`, `invoke_endpoint` hay endpoint name trong `app/`, `scripts/`, `infra/`. Đây là khác biệt quan trọng so với mô tả đầu vào.
- Redis DB 0 dùng cho guest rate-limit và freshness lock; không chứa freshness result. Freshness result/TTL nằm trong bảng PostgreSQL `LegalDocument`. Celery dùng Redis DB 1/2 làm broker/result và beat chạy `vlegal.verify_legal_corpus` mỗi 24 giờ (`app/worker.py:19-37,41-73`). API không gọi `.delay()`/`send_task()`; worker là đường định kỳ bổ sung, không thay thế freshness cache-miss đồng bộ trong `/api/chat`.

Môi trường thực tế:

- Repo không có `.git` và không có `.env`. `TAVILY_API_KEY` không có ở process/user/machine environment; một key không rỗng lại nằm trong `.env.example` và đã được dùng cho phép đo thật mà không ghi giá trị vào artifact. Cần chuyển secret sang `.env`/secret manager và rotate nếu key này đã từng commit.
- Tại thời điểm lấy baseline đầu tiên chưa có Docker Desktop/WSL/Java; Qdrant `v1.15.3` phải chạy bằng binary Windows. Trạng thái lịch sử này đã được khắc phục và được đo lại bằng Docker tại mục 8.
- SQLite index được build lại từ 57 DOCX: 23.633 node, 51.094 edge, 25.554 chunk. Ollama trả về `qwen3.6:latest`, artifact 22,29 GB.

## 2. Baseline trước tối ưu

Phương pháp: `scripts/profile_latency.py`, 20 câu lấy ngẫu nhiên từ `eval_legal_rag_graphrag_1000.json` bằng seed `20260718`, 10 lần/câu/mode, `top_k=10`, một warm-up ngoài số đo. Do đó `n=200` cho mỗi mode khả dụng. Timer dùng `time.perf_counter()`; raw data nằm tại `storage/audit/latency_runs/baseline_pre/raw.csv`, danh sách câu hỏi tại `selected_questions.json` cùng thư mục.

| Mode | Bước | n | Median (s) | p95 (s) | Min (s) | Max (s) | % median retrieval/e2e | Ghi chú |
|---|---|---:|---:|---:|---:|---:|---:|---|
| rag | Qdrant `query_points` | 200 | 0,011897 | 0,024735 | 0,006823 | 0,050042 | 51,83% | Call thật tới Qdrant v1.15.3 local |
| rag | retrieval other (hash vector + payload rerank/serialize) | 200 | 0,010029 | 0,017210 | 0,004438 | 0,168913 | 43,70% | CPU/application residual |
| rag | retrieval total | 200 | 0,022922 | 0,037783 | 0,013212 | 0,180973 | 100% | Không gồm freshness/generation |
| graphrag | Neo4j retrieval | 200 | 0,057358 | 0,104101 | 0,039693 | 0,245062 | 100% | Đo bổ sung sau khi Docker sẵn sàng; artifact `docker_external_baseline_pre` |
| hybrid_rag | Qdrant + Neo4j retrieval | 200 | 0,062152 | 0,097134 | 0,035126 | 0,116025 | 100% | Đo bổ sung sau khi Docker sẵn sàng; artifact `docker_external_baseline_pre` |
| local_graphrag | SQLite FTS | 200 | 0,158409 | 0,218282 | 0,110244 | 0,289721 | 20,52% | Call SQLite FTS thật |
| local_graphrag | SQLite vector scan | 200 | 0,585303 | 0,756284 | 0,513197 | 0,884904 | 75,83% | Bottleneck retrieval lớn nhất có thể sửa/đo local |
| local_graphrag | SQLite graph expansion | 200 | 0,015747 | 0,052320 | 0,003577 | 0,082603 | 2,04% | Call SQLite graph thật |
| local_graphrag | retrieval total | 200 | 0,771853 | 0,993839 | 0,655840 | 1,162325 | 100% | Không gồm freshness/generation |
| freshness cache miss | Tavily search | 10 | 11,245813 | 20,033492 | 7,980460 | 21,143152 | 100% của probe riêng | 10 call thật; không gồm PostgreSQL cache, verdict LLM, index update |
| rag/local | answer generation | 0 hợp lệ | N/A | N/A | N/A | N/A | N/A | **mock qua Ollama qwen3.6, không đại diện cho Qwen3/SageMaker thật**; full prompt timeout >300 s |

Tavily có nằm trên `/api/chat`, nhưng chỉ khi cache miss/expired: `/api/chat` chờ `_legal_sources` (`app/api.py:477`), `_legal_sources` chờ `verify_sources` (`app/api.py:227`), cache hit trả ở `app/services/freshness.py:122-123`, cache miss chờ Tavily ở `app/services/freshness.py:143,157`. TTL hiện là 24 giờ (`app/core/config.py:59`). Probe baseline đo cache miss Tavily cô lập, không giả thành latency của mọi câu chat; PostgreSQL đã được dựng sau đó nhưng cache vẫn rỗng vì verdict Ollama timeout (mục 7–8).

Kiểm định tuần tự/song song: trên từng raw run, `Qdrant + retrieval_other` giải thích median 99,9907% `e2e_total` của rag; `SQLite FTS + vector + graph + retrieval_other` giải thích 99,9998% của local_graphrag. Phần retrieval trong mỗi store đang tuần tự. Ở tầng request, retrieval phải hoàn tất trước freshness, và freshness phải hoàn tất trước answer generation theo chuỗi `await` trên. Riêng nhiều luật trong một freshness pass được chạy song song với `asyncio.gather` và semaphore=4 (`app/services/freshness.py:65,87`), nên không được nhân latency Tavily với số luật.

Generation diagnostic, không dùng cho SLA:

- Smoke ngắn, warm, giới hạn 16 output token: 5,652515 s, `n=1`.
- Full prompt với 10 nguồn, `max_tokens=2200` giống `/api/chat`: không hoàn tất trong timeout 300 s, `n=1`.
- Cả hai là **mock qua Ollama qwen3.6, không đại diện cho Qwen3/SageMaker thật**; không đủ `n>=10`, nên không báo median/p95.

## 3. Kết quả từng hạng mục tối ưu thực sự đã làm

| Hạng mục | Áp dụng? | Latency trước (median) | Latency sau (median) | % cải thiện | Rủi ro/đánh đổi |
|---|---|---:|---:|---:|---|
| Vector hóa SQLite scan bằng ma trận NumPy, stable sort | Có | vector 0,585303 s; local retrieval 0,771853 s | vector 0,003834 s; local retrieval 0,193429 s | vector 99,34%; end-to-end retrieval 74,94% | Thêm dependency NumPy và buffer vector liên tục trong RAM. Đã kiểm chứng output parity tuyệt đối trên 20 câu: cùng Hit@10=0,800000, MRR=0,380833 và cùng SHA-256 thứ tự nguồn `e2679d983a896e4aa53fe9d261e4d54e5b0d00fba56bbe81d0354b3882f29988`. |
| Tái sử dụng một `httpx.AsyncClient` cho Tavily thay vì mở TLS/client mỗi call | Có | cache-miss Tavily 11,245813 s; p95 20,033492 s | 1,634874 s; p95 6,048549 s | median 85,46%; p95 69,81% | Network/API variance lớn và n=10; không quy toàn bộ chênh lệch cho pooling. Search vẫn `advanced`, cùng official domains, `include_raw_content=True`; không giảm độ đúng đắn. Phải đóng client ở lifespan/worker. |

Không chuyển Qdrant/Neo4j sang async SDK: endpoint đã cô lập sync SDK bằng threadpool; Qdrant chỉ 11,897 ms median ở baseline cũ, còn toàn bộ Docker `graphrag`/`hybrid_rag` chỉ 57,358/62,152 ms median. Không tinh chỉnh top-k/rerank vì thay đổi candidate set có rủi ro chất lượng không cần thiết. Redis/PostgreSQL nay đã chạy qua Docker, nhưng freshness result vẫn chưa warm được do verdict Ollama timeout; vì vậy không có số cache-hit thật để biện minh thêm result cache.

TTL 24 giờ hiện tại cân bằng hợp lý: văn bản pháp luật không thường thay đổi theo phút, nightly worker có thể prewarm, còn rút ngắn TTL làm tăng cache miss/Tavily; kéo dài hơn 24 giờ tăng rủi ro trả lời theo trạng thái hiệu lực cũ. Với văn bản vừa có dấu hiệu `AMENDED/REPLACED`, logic vẫn index lại và re-retrieve trong cùng request (`app/services/freshness.py:219-235`; `app/api.py:230-232`).

## 4. Tổng kết retrieval-only theo mode

Raw after nằm tại `storage/audit/latency_runs/optimized_post/raw.csv`; cùng 20 câu, seed, 10 lần/câu và top-k như baseline.

| Mode | Latency retrieval trước, median (p95) | Latency retrieval sau, median (p95) | Đạt tiến bộ đáng kể? |
|---|---:|---:|---|
| rag | 0,022922 s (0,037783 s) | 0,022289 s (0,036728 s) | Không; 2,76% nằm trong jitter, không tuyên bố là hiệu quả code Qdrant |
| graphrag | 0,057358 s (0,104101 s) | 0,048002 s (0,074761 s) | Đã thấp hơn mục tiêu rất xa; không tuyên bố cải thiện code vì không có thay đổi Cypher giữa hai lượt |
| hybrid_rag | 0,062152 s (0,097134 s) | 0,062433 s (0,095742 s) | Ổn định trong jitter; không có thay đổi retrieval code |
| local_graphrag | 0,771853 s (0,993839 s) | 0,193429 s (0,244325 s) | Có; median giảm 74,94%, p95 giảm 75,41%, chất lượng/order không đổi |

Freshness cache-miss Tavily sau tối ưu là 1,634874 s median, p95 6,048549 s (`n=10`). Nó được tách khỏi bảng retrieval vì cache hit không gọi Tavily và vì full freshness còn PostgreSQL + Redis lock + verdict LLM + có thể index lại.

## 5. Còn thiếu gì để kết luận mục tiêu tổng thể dưới 3–4 giây

Chưa thể kết luận đạt SLA full-question cho `rag`, `graphrag` hoặc `hybrid_rag`:

1. `rag` retrieval nội bộ đã thấp hơn 0,04 s ở p95, và `local_graphrag` thấp hơn 0,25 s ở p95 sau sửa. Đây là phần đã đo chắc chắn.
2. Tavily cache miss sau pooling có median 1,635 s nhưng p95 6,049 s, tự nó có thể vượt SLA trước generation. Cache hit 24 giờ có thể tránh call này; PostgreSQL nay đã chạy, nhưng warm không ghi được row do verdict Ollama timeout nên vẫn chưa có số cache-hit end-to-end thật.
3. Qwen3/SageMaker là ẩn số. Repo không có SageMaker provider/cấu hình/payload contract; `LLM_PROVIDER=qwen3_sagemaker` hiện không phải giá trị được implement. Không thể chỉ “thêm credential” rồi chạy lại cho tới khi code provider thật được cung cấp. Khi có provider, phải chạy lại profiler `n>=10` với cùng seed/questions, đo riêng freshness verdict generation và answer generation.
4. Ollama local không thay thế số thật: smoke 16 token đã 5,653 s và full prompt timeout >300 s. Đây là **mock qua Ollama qwen3.6, không đại diện cho Qwen3/SageMaker thật**.
5. Blocker Docker/Neo4j/Redis/PostgreSQL đã được gỡ: bốn service thật trong compose (`postgres`, `redis`, `neo4j`, `qdrant`; `docker-compose.yml:70,84,95,109`) đều chạy; PostgreSQL migrate đủ 11 bảng, Neo4j/Qdrant đã sync corpus. `SHOW INDEXES`/`SHOW CONSTRAINTS` xác nhận các index/constraint ứng dụng đều `ONLINE`. Không sửa Cypher và không chạy tối ưu bằng `PROFILE`, vì toàn retrieval Neo4j đã chỉ 48,002 ms median/74,761 ms p95 ở lượt hậu kiểm; đây không phải bottleneck có ý nghĩa so với freshness/generation.
6. DB audit/auth latency chưa đo: request đăng nhập có PostgreSQL commits trước retrieval và sau generation (`app/api.py:470,497`); request khách có Redis rate-limit (`app/api.py:435`; `app/services/guest_limit.py:33-38`).

Streaming: repo không có SageMaker streaming config để xác nhận hỗ trợ. Local Qwen dùng blocking `model.generate`, Ollama mock đang `stream=False`. Khi endpoint thật hỗ trợ response stream, thiết kế nên giữ retrieval + freshness hoàn tất trước, sau đó trả `StreamingResponse` và forward token/chunk; đo time-to-first-token riêng. Đây chỉ cải thiện latency cảm nhận, không giảm latency tới token cuối và không được ghi là đạt SLA trước khi đo endpoint thật.

## 6. Danh sách thay đổi local và kiểm tra bàn giao

| File/artifact | Thay đổi |
|---|---|
| `scripts/profile_latency.py` | Profiler tái lập: seed cố định, raw CSV, median/p95/min/max, per-vendor timers, environment availability, Tavily cache-miss probe, note generation mock. |
| `app/core/config.py` | Thêm `LLM_PROVIDER` mặc định `qwen_local`, cấu hình Ollama mock; production behavior giữ nguyên khi không set flag. |
| `app/services/ai.py` | Thêm nhánh `/api/generate` cho `ollama_mock`, cùng system/user/context và JSON schema; `think=False` để khớp local Qwen `enable_thinking=False`. Code có comment TEMP tại `app/services/ai.py:212` và phải tiếp tục feature-flag hoặc gỡ trước production merge. |
| `.env.example` | Tài liệu hóa feature flag/config Ollama. File hiện chứa Tavily key không rỗng từ trạng thái repo; cần xử lý secret ngoài phạm vi latency. |
| `app/services/tavily.py` | Persistent async HTTP connection pool; thêm `close()`. |
| `app/main.py`, `app/worker.py` | Đóng Tavily client đúng lifecycle. |
| `app/legal_graphrag.py` | NumPy contiguous vector matrix + vectorized dot product + stable ordering. |
| `requirements.txt` | Ghi dependency NumPy rõ ràng. |
| `storage/graphrag/legal_graphrag.sqlite` | Index local được build từ 57 DOCX (artifact binary bị `.gitignore`). |
| `storage/audit/latency_runs/baseline_pre/*` | Raw baseline, summary và 20 câu đã chọn. |
| `storage/audit/latency_runs/optimized_post/*` | Raw after, summary và 20 câu đã chọn. |

Không có commit/push/PR hoặc thao tác GitHub nào được thực hiện. Thư mục hiện tại không có metadata `.git`, nên không thể dùng `git diff/status`; tất cả thay đổi chỉ ở local workspace.

Definition of Done tại thời điểm báo cáo:

- Báo cáo này tồn tại và chứa số retrieval thật trước/sau: đạt.
- Có before/after đủ `n=200` cho `rag` và `local_graphrag`; có Tavily call thật `n=10`: đạt.
- Output parity local GraphRAG đã kiểm tra; bước `py_compile/compileall` cuối phải được chạy sau khi ghi báo cáo: xem log bàn giao của phiên làm việc.
- `graphrag` và `hybrid_rag` retrieval đã đo đủ `n=200/mode` sau khi Docker sẵn sàng. Full PostgreSQL freshness/cache hit và Qwen3/SageMaker thật vẫn chưa đo được, có blocker cụ thể; không có số ước lượng.

## 7. Kịch bản demo thực tế (warm cache)

Phần này cập nhật trạng thái môi trường sau mục 1–6: ban đầu PostgreSQL 16.14 portable được dùng để chẩn đoán; sau khi Docker Desktop/WSL2 sẵn sàng, service `postgres:16-alpine` thật trong compose đã thay thế runtime audit, bind local-only `127.0.0.1:5432`. Database/role `vlegal` đã tạo và Alembic đã migrate đủ 11 bảng tới revision `20260714_0001`. Vì vậy blocker hiện tại không còn là PostgreSQL.

Corpus `storage/graphrag/documents.jsonl` có 57 dòng và 57 mã văn bản duy nhất. Script `scripts/warm_freshness_cache.py` đọc danh sách này, gọi đúng `LegalFreshnessService.verify_sources(...)` theo batch (`scripts/warm_freshness_cache.py:23-43,88`) và chỉ coi là warm thành công khi PostgreSQL thực sự có `verified_at` trong TTL.

### Kết quả warm thật và blocker

1. Lần chẩn đoán đầu tiên cho `20/2016/TT-BTC` kết thúc sau 5,044835 s với Tavily HTTP 400: query dài hơn 400 ký tự; 0/1 văn bản được ghi cache. Artifact: `storage/audit/freshness_warm_diagnostic.json`.
2. Query Tavily được giới hạn mà không bỏ mã văn bản hay các từ khóa hiệu lực (`app/services/freshness.py:59-66,166-167`). Kiểm tra trên đủ 57 văn bản: query dài nhất 400 ký tự, 0 query vượt limit. Call Tavily thật sau sửa cho văn bản đầu trả 8 kết quả sau 2,396829 s; tổng nguồn thô 305.718 ký tự và bundle bằng chứng sau giới hạn hiện hành là 54.133 ký tự.
3. Pipeline đầy đủ sau sửa query vẫn thất bại: 323,996991 s cho 1 văn bản, do Ollama mock timeout sau khi Tavily đã trả bằng chứng; 0/1 thành công. Giới hạn output mock từ 1.500 xuống 256 token, giữ nguyên bundle bằng chứng, vẫn timeout: 307,702139 s, 0/1 thành công. Artifacts: `freshness_warm_diagnostic_post_query_fix.json` và `freshness_warm_diagnostic_256.json`.
4. Trước chẩn đoán đơn lẻ, lần warm full corpus với batch 4 đã chờ hơn 1.200 s ngay batch đầu mà không có batch kết quả, nên được dừng để không tạo thêm hàng giờ timeout. Truy vấn PostgreSQL sau các lần thử đều cho `legal_document`: `total=0`, `verified=0`, `fresh trong 24h=0`.

Kết luận: cache chưa được warm. Không chạy/ghi nhãn `warm_cache_post`, vì làm như vậy sẽ biến cache-miss hoặc retrieval-only thành số cache-hit giả. Cũng không thể thử mixed hit/miss bằng cách lùi `verified_at` của 2–3 văn bản: hiện không có bản ghi fresh nào để hết hạn. `profile_latency.py` đã có thêm `--with-freshness`; nó gọi thật `verify_sources`, ghi Tavily = 0 chỉ khi không có network call, và đếm tổng call Tavily (`scripts/profile_latency.py:282-285`).

### So sánh ba trạng thái

| Chỉ số | Cold-cache (`baseline_pre`) | Optimized cold-cache (`optimized_post`) | Warm-cache (`warm_cache_post`) |
|---|---:|---:|---:|
| Số call Tavily hợp lệ | 10 | 10 | N/A — không warm được |
| Tavily median (p95) | 11,245813 s (20,033492 s) | 1,634874 s (6,048549 s) | N/A — PostgreSQL có 0 fresh row |
| `rag` retrieval median | 0,022922 s | 0,022289 s | N/A — không có run cache-hit |
| `local_graphrag` retrieval median | 0,771853 s | 0,193429 s | N/A — không có run cache-hit |
| Tổng median component `rag retrieval + Tavily` | 11,268735 s | 1,657163 s | N/A |
| Tổng median component `local retrieval + Tavily` | 12,017666 s | 1,828303 s | N/A |

Hai dòng “tổng component” chỉ là phép cộng hai median đo riêng để nhìn quy mô; không phải median end-to-end, không gồm PostgreSQL/Redis lock, verdict LLM, index update hay answer generation. Do đó chưa có con số latency kỳ vọng hợp lệ cho buổi demo warm-cache, và cũng chưa có số để tuyên bố tỷ lệ hit gần 100%. Kịch bản xấu nhất đã đo được chỉ là Tavily cache-miss: median 1,634874 s, p95 6,048549 s sau tối ưu; full request còn có các phần chưa đo.

### Hướng dẫn vận hành trước demo

Sau khi có provider LLM đủ nhanh/ổn định để verdict freshness hoàn tất, chạy từ root repo:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://vlegal:vlegal@127.0.0.1:5432/vlegal'
$env:REDIS_URL='redis://127.0.0.1:6379/0'
$env:LLM_PROVIDER='ollama_mock'
python scripts/warm_freshness_cache.py --env-file .env --batch-size 4 --strict
```

`.env` phải chứa `TAVILY_API_KEY` không rỗng; không ghi key vào command/log. Chỉ cho phép bắt đầu demo khi summary báo `corpus_fresh_documents=57`, `errors=0` và process thoát mã 0. Không thể khuyến nghị trung thực “chạy trước 5 phút” trên máy audit này: một văn bản đã timeout sau hơn 5 phút và full warm chưa từng hoàn tất. Sau khi provider được sửa, phải chạy rehearsal để lấy `warm_minutes` thật, rồi chọn lead time lớn hơn con số đó.

TTL 24 giờ (`app/core/config.py:59`; cache-hit tại `app/services/freshness.py:124-133`) nghĩa là mỗi văn bản chỉ tránh Tavily khi `verified_at` không cũ hơn 24 giờ. Không warm từ hôm trước nếu từ lúc warm đến demo có thể vượt 24 giờ; phải warm lại và xác nhận summary ngay trong cửa sổ 24 giờ. Nếu quên warm, warm thất bại, hoặc cache hết TTL, `/api/chat` đi lại đường cache-miss đồng bộ và chờ Tavily + verdict LLM; Tavily riêng lẻ đã đo từ 1,634874 s median/6,048549 s p95 sau tối ưu, hoặc 11,245813 s/20,033492 s ở baseline.

Mọi thay đổi và artifact trong mục này chỉ nằm local. Không commit, push, mở PR hay thực hiện thao tác GitHub nào.

## 8. Đo bổ sung sau khi Docker Desktop và WSL2 sẵn sàng

Ngày 18/07/2026, Docker Desktop báo Engine running; đo trực tiếp xác nhận Docker Engine `29.6.1`, Compose `5.3.0`. Đúng bốn service trong `docker-compose.yml` được dựng: `postgres:16-alpine`, `redis:7.4-alpine`, `neo4j:5.26-community`, `qdrant/qdrant:v1.15.3`. File override local-only `docker-compose.audit.yml` chỉ publish các cổng lên `127.0.0.1` để profiler host truy cập; không mở datastore ra LAN.

Trạng thái dữ liệu sau sync thật bằng `scripts/sync_external_graphrag.py --skip-sqlite-build --reset-neo4j --reset-qdrant`:

- PostgreSQL: revision `20260714_0001`, 11 bảng public.
- Neo4j: 49.187 node tổng, gồm 23.633 `LegalNode` và 25.554 `LegalChunk`; 76.648 relationship. Full-text index `legal_chunk_fulltext`, các range index và hai uniqueness constraint đều `ONLINE`.
- Qdrant collection `vlegal_legal_chunks`: exact count 25.554 point.
- Redis: `PONG`; `used_memory_human=988,12 KiB`, `maxmemory=0` tại lúc kiểm tra, nên chưa có dấu hiệu áp lực bộ nhớ.

Baseline external modes dùng 20 câu, seed `20260718`, 10 lần/câu/mode, `top_k=10`, một warm-up ngoài số đo (`n=200/mode`). Raw data: `storage/audit/latency_runs/docker_external_baseline_pre/raw.csv`. Lượt hậu kiểm đủ bốn mode dùng cấu hình giống hệt; raw data: `storage/audit/latency_runs/docker_all_modes_post/raw.csv`.

| Mode | Bước chính | n | Median (s) | p95 (s) | Kết luận |
|---|---|---:|---:|---:|---|
| rag | retrieval total | 200 | 0,022606 | 0,036145 | Qdrant retrieval thấp hơn mục tiêu 3–4 s rất xa |
| graphrag | Neo4j seed | 200 | 0,010012 | 0,012675 | Không phải bottleneck |
| graphrag | Neo4j expand | 200 | 0,017952 | 0,033486 | Bước Neo4j lớn nhất nhưng chỉ 17,952 ms median |
| graphrag | Neo4j chunks | 200 | 0,010749 | 0,023387 | Không phải bottleneck |
| graphrag | retrieval total | 200 | 0,048002 | 0,074761 | Đạt mục tiêu retrieval; không cần sửa Cypher |
| hybrid_rag | Qdrant | 200 | 0,024635 | 0,032392 | Call thật tới Qdrant Docker |
| hybrid_rag | Neo4j expand | 200 | 0,018205 | 0,039478 | Không phải bottleneck |
| hybrid_rag | Neo4j chunks | 200 | 0,014120 | 0,030268 | Không phải bottleneck |
| hybrid_rag | retrieval total | 200 | 0,062433 | 0,095742 | Đạt mục tiêu retrieval; không cần song song hóa thêm |
| local_graphrag | retrieval total | 200 | 0,172269 | 0,218691 | NumPy vector optimization vẫn giữ hiệu quả |

`graphrag` baseline đầu tiên là 0,057358 s median/0,104101 s p95; lượt hậu kiểm là 0,048002 s/0,074761 s. Không có thay đổi Cypher giữa hai lượt, nên chênh lệch này được xem là warm-cache/jitter và không ghi thành phần trăm tối ưu code. `hybrid_rag` tương ứng 0,062152 s/0,097134 s và 0,062433 s/0,095742 s, gần như không đổi.

Kết luận cập nhật: cả bốn mode retrieval đều dưới 0,22 s ở p95 trên máy audit; phần retrieval không còn là trở ngại cho SLA tổng 3–4 s. Freshness warm-cache và answer generation vẫn là khoảng trống: Docker giải quyết PostgreSQL/Redis nhưng không làm Ollama qwen3.6 xử lý bundle freshness 54.133 ký tự nhanh hơn. Database Docker mới vẫn có `legal_document total=0, verified=0, fresh=0`; do đó các kết luận N/A cho `warm_cache_post` ở mục 7 vẫn giữ nguyên và không được thay bằng số retrieval.

Qdrant Python client cài trên host là `1.18.0`, cao hơn server `1.15.3` và phát cảnh báo compatibility, dù toàn bộ sync/query đã thành công. Đây là rủi ro cấu hình cần ghim client tương thích trước production; không ảnh hưởng việc ghi nhận các run đã hoàn tất, nhưng cần chạy regression lại nếu thay version.
