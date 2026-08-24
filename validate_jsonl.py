import json
p = "storage/graphrag/documents.jsonl"
total = 0
bad = []
paths = []
with open(p, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        s = line.strip()
        if not s:
            continue
        total += 1
        try:
            obj = json.loads(s)
            paths.append((i, obj.get("path", ""), obj.get("doc_id", "")))
        except Exception as e:
            bad.append((i, str(e)[:200]))

print(f"total={total} bad={len(bad)}")
for b in bad[:10]:
    print("BAD", b)
# Show ND-112 record
for idx, path, doc_id in paths:
    if "112-2021" in doc_id or "112-2021" in path:
        print(f"line {idx} doc_id={doc_id} path={path!r}")
        # raw line slice
        with open(p, encoding="utf-8") as f2:
            for j, raw in enumerate(f2, 1):
                if j == idx:
                    print("raw_len", len(raw))
                    # check escaping
                    import re
                    m = re.search(r'"path":\s*"([^"]*)"', raw)
                    if m:
                        print("raw_path_json_str", repr(m.group(0)[:120]))
                    # show if raw contains single backslash before legal
                    print("raw_contains_backslash_legal", "legal-documents" in raw)
                    print("raw_slice", repr(raw[max(0, raw.find("legal-documents")-20): raw.find("legal-documents")+60]))
                    break
        break
# Check raw escaping: does raw contain \\ (escaped) or single \ ?
with open(p, encoding="utf-8") as f:
    first = f.readline()
    print("first_line_raw_path_section", repr(first[first.find("legal-documents")-30:first.find("legal-documents")+80]) if "legal-documents" in first else "not found")
    print("first_line_contains_double_backslash", "\\\\" in first)
