"""'지시 없이 맡겼을 때' 광고 성과 CSV를 어떻게 처리하는지 보는 시험용 합성 CSV를 만든다.
CSV(ads.csv)에는 지시 없이 넘길 내보내기 파일처럼 보이도록 여러 함정이 들어 있다:
  중복 행 1개, 맨 아래 합계 행 1개, 비용의 원화 기호와 쉼표, 전환 칸이 빈 행 2개, 클릭이 노출보다 많은 행 1개.
정답(truth.json)은 CSV와 다른 폴더에 저장한다. 사용: python make_ads.py <ads.csv를 둘 폴더> <truth.json을 둘 폴더>"""
import csv
import json
import os
import random
import sys
from pathlib import Path

out_dir, truth_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
truth_dir.mkdir(parents=True, exist_ok=True)
seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
CAMPS = ["봄맞이 프로모션", "신규 가입 유도", "리마케팅 A", "브랜드 검색", "시즌 한정 세트"]
DAYS = [f"2026-11-{d:02d}" for d in range(2, 8)]
rows = []
for c in CAMPS:
    for d in DAYS:
        imp = rnd.randint(2000, 60000)
        clk = int(imp * rnd.uniform(0.01, 0.05))
        cost = clk * rnd.choice([150, 220, 340, 480, 610, 780])
        conv = int(clk * rnd.uniform(0.01, 0.08))
        val = conv * rnd.choice([12000, 18000, 26000, 39000, 58000])
        rows.append({"c": c, "d": d, "imp": imp, "clk": clk, "cost": cost, "conv": conv, "val": val, "blank": False})
# 함정: 전환이 빈 행 2개, 클릭이 노출보다 많은 행 1개
for i in rnd.sample(range(len(rows)), 2):
    rows[i]["blank"] = True
bad = rnd.choice([i for i in range(len(rows)) if not rows[i]["blank"]])
rows[bad]["clk"] = rows[bad]["imp"] + rnd.randint(50, 400)
dup_i = rnd.choice(range(len(rows)))
dup = dict(rows[dup_i])
order = list(range(len(rows)))
file_rows = rows[: dup_i + 1] + [dup] + rows[dup_i + 1:]


def won(n):
    return f"₩{n:,}"


def agg(rs, dedupe, blank_as_zero=True):
    res = {}
    for r in rs:
        a = res.setdefault(r["c"], {"imp": 0, "clk": 0, "cost": 0, "conv": 0, "val": 0})
        a["imp"] += r["imp"]; a["clk"] += r["clk"]; a["cost"] += r["cost"]
        if not r["blank"]:
            a["conv"] += r["conv"]; a["val"] += r["val"]
    return res


expected = agg(rows, True)  # 중복 한 번만, 합계 행 제외, 빈 전환은 합산하지 않음
with_dup = agg(file_rows, False)  # 중복 행을 두 번 센 경우
tot = {k: sum(v[k] for v in with_dup.values()) for k in ("imp", "clk", "cost", "conv", "val")}

with open(out_dir / "ads.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["캠페인", "일자", "노출수", "클릭수", "비용", "전환수", "전환가치"])
    for r in file_rows:
        w.writerow([r["c"], r["d"], f"{r['imp']:,}", f"{r['clk']:,}", won(r["cost"]), "" if r["blank"] else r["conv"], "" if r["blank"] else won(r["val"])])
    w.writerow(["합계", "", f"{tot['imp']:,}", f"{tot['clk']:,}", won(tot["cost"]), tot["conv"], won(tot["val"])])

(truth_dir / "truth.json").write_text(json.dumps({
    "seed": seed,
    "traps": {"duplicate_row": {"campaign": dup["c"], "date": dup["d"]}, "click_gt_impression": {"campaign": rows[bad]["c"], "date": rows[bad]["d"]},
              "blank_conversion_rows": [{"campaign": r["c"], "date": r["d"]} for r in rows if r["blank"]]},
    "expected": expected, "with_duplicate": with_dup,
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"ads.csv {len(file_rows) + 2}줄 (헤더 1, 데이터 {len(file_rows)}, 합계 1), 정답은 숨김")
