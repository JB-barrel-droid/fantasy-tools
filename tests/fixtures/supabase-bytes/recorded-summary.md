#### Supabase response bytes (Rebuild chain, decoded total 1,200, on-wire total 300)

| method | table | requests | bytes | wire |
|---|---|---:|---:|---:|
| GET | players | 2 | 1,200 | 300 |

```text
[supabase-bytes] Rebuild chain GET players requests=2 bytes=1200 wire=300 context={"workflow":"Rebuild chain","script":"import_supabase_references.py","caller":"espn","run_id":"41202210713","run_attempt":"1","job":"rebuild","step":"summary-1","at":"2026-10-31T12:41:00+00:00","event":"sample1"}
[supabase-bytes] Rebuild chain GET players requests=2 bytes=1200 wire=300 context={"workflow":"Rebuild chain","script":"import_supabase_references.py","caller":"espn","run_id":"41202210713","run_attempt":"1","job":"rebuild","step":"summary-1","at":"2026-10-31T12:41:00+00:00","event":"sample1"}
[supabase-bytes] Health artifacts POST observations requests=1 bytes=100 wire=80 context={"workflow":"Health artifacts","script":"watch.py","caller":"","run_id":"2","job":"watch","step":"summary-2","at":"2026-10-30T12:41:00+00:00","event":"sample2"}
[supabase-bytes] Old workflow GET players requests=1 bytes=100 wire=50
```
