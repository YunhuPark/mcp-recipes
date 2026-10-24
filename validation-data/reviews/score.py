"""후기 분류 시험 채점. 사용: python validation-data/reviews/score.py
truth.json(정답, 후기를 만들 때 함께 저장)과 extracted.json(AI가 후기만 보고 분류한 것)을 대조한다.
분류 결과는 정답을 보기 전에 저장했다."""
import json
import sys
from collections import defaultdict
from pathlib import Path

here = Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
truth = {i["n"]: i for i in json.loads((here / "truth.json").read_text(encoding="utf-8"))["items"]}
ext = json.loads((here / "extracted.json").read_text(encoding="utf-8"))
cat = sum(e["category"] == truth[e["n"]]["category"] for e in ext)
sen = sum(e["sentiment"] == truth[e["n"]]["sentiment"] for e in ext)
print(f"주제 {cat}/{len(ext)}, 감정 {sen}/{len(ext)}")
by = defaultdict(lambda: [0, 0])
for e in ext:
    t = truth[e["n"]]
    by[t["kind"]][1] += 1
    by[t["kind"]][0] += e["category"] == t["category"] and e["sentiment"] == t["sentiment"]
print({k: f"{a}/{b}" for k, (a, b) in by.items()})
