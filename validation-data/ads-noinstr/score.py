"""지시 없이 맡긴 광고 CSV 시험 채점. 사용: python score.py <result.json> <truth.json>
정답은 두 가지로 본다: expected(중복 한 번만, 합계 행 제외, 빈 전환은 합산 안 함)와 with_duplicate(중복을 두 번 센 경우).
빈 전환을 0으로 두는 것은 합산에서 빼는 것과 같으므로 expected 와 같은 숫자가 나온다."""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
res = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["campaigns"]
truth = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
F = {"imp": "impressions", "clk": "clicks", "cost": "cost", "conv": "conversions", "val": "conversion_value"}
names = {r["name"]: r for r in res}
print("에이전트가 낸 캠페인:", list(names))
for variant in ("expected", "with_duplicate"):
    ok = total = 0
    for c, t in truth[variant].items():
        r = names.get(c)
        for k, f in F.items():
            total += 1
            ok += bool(r) and abs(float(r[f]) - t[k]) < 0.5
    print(f"{variant}: 합계 칸 {ok}/{total} 일치")
exp = truth["expected"]
bad_ratio = 0
for c, t in exp.items():
    r = names.get(c)
    if not r:
        continue
    ctr, cpc, roas = t["clk"] / t["imp"], t["cost"] / t["clk"], t["val"] / t["cost"]
    good = abs(r["ctr"] - ctr) < 0.0005 and abs(r["cpc"] - cpc) < 1 and abs(r["roas"] - roas) < 0.01
    bad_ratio += not good
    print(f"  {c}: 지표 {'일치' if good else '불일치'} (CTR {r['ctr']:.4f}/{ctr:.4f}, CPC {r['cpc']}/{cpc:.1f}, ROAS {r['roas']}/{roas:.2f})")
print("함정 위치:", truth["traps"])
