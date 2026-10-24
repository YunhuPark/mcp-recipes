"""회의록 시험 채점. 사용: python validation-data/meetings/score.py
truth.json(정답, 회의록을 만들 때 함께 저장)과 extracted.json(AI가 회의록만 보고 뽑은 것)을 대조한다.
뽑은 결과는 정답을 보기 전에 저장했다."""
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
truth = json.loads((here / "truth.json").read_text(encoding="utf-8"))
ext = json.loads((here / "extracted.json").read_text(encoding="utf-8"))
T = {(m["meeting"], i["task"]): i for m in truth["meetings"] for i in m["items"]}
E = {(e["meeting"], e["task"]): e for e in ext}
matched = [k for k in E if k in T]
print(f"정답 {len(T)}개, 뽑은 것 {len(E)}개")
print("놓친 것:", [k for k in T if k not in E])
print("정답에 없는데 뽑은 것:", [k for k in E if k not in T])
print(f"담당 일치 {sum(E[k]['owner'] == T[k]['owner'] for k in matched)}/{len(matched)}, 기한 일치 {sum(E[k]['due'] == T[k]['due'] for k in matched)}/{len(matched)}")
