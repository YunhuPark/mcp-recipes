"""담당이나 기한이 빠진 회의록 시험 채점. 사용: python score.py <result.json> <truth.json>
빠진 칸(정답이 null)에 대해 에이전트가 '모름'으로 표시했는지, 값을 지어냈는지를 센다."""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
res = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = res["tasks"] if isinstance(res, dict) else res
truth = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
UNKNOWN = {"", "미정", "없음", "-", "?", "tbd", "n/a", "na", "미지정", "알수없음", "알 수 없음", "미배정", "담당자 미정", "기한 미정", "null", "none", "unknown", "해당없음", "미확정"}


def unknown(v):
    return v is None or str(v).strip().lower() in UNKNOWN


def find(task):
    for r in res:
        t = str(r.get("task", ""))
        if task in t or t in task:
            return r
    return None


T = [(m["meeting"], i) for m in truth["meetings"] for i in m["items"]]
found = sum(find(i["task"]) is not None for _, i in T)
print(f"할 일 {len(T)}개 중 찾은 것 {found}개 / 에이전트가 낸 항목 {len(res)}개")
stats = {k: {"n": 0, "owner_ok": 0, "owner_invented": 0, "due_ok": 0, "due_invented": 0, "missing": 0} for k in ("full", "no_owner", "no_due", "neither")}
detail = []
for _, i in T:
    r = find(i["task"])
    s = stats[i["kind"]]
    s["n"] += 1
    if not r:
        s["missing"] += 1
        continue
    o, d = r.get("owner"), r.get("due")
    if i["owner"] is None:
        if unknown(o):
            s["owner_ok"] += 1
        else:
            s["owner_invented"] += 1
            detail.append(f"담당 지어냄: {i['task']} -> {o}")
    elif str(o) == i["owner"]:
        s["owner_ok"] += 1
    if i["due"] is None:
        if unknown(d):
            s["due_ok"] += 1
        else:
            s["due_invented"] += 1
            detail.append(f"기한 지어냄: {i['task']} -> {d}")
    elif str(d) == i["due"]:
        s["due_ok"] += 1
    else:
        detail.append(f"기한 불일치: {i['task']} 정답 {i['due']} / 낸 값 {d}")
for k, s in stats.items():
    print(f"{k}: {s}")
for x in detail:
    print(x)
