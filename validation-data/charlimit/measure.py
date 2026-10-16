"""글자 수 제한 시험의 채점. 사용: python validation-data/charlimit/measure.py

A.json, B.json 의 각 문구를 파이썬 len() 으로 센다 (공백과 문장부호 포함, 유니코드 문자 수).
글을 쓴 뒤에 이 스크립트로 처음 세므로, 글 쓰는 쪽이 결과를 미리 알 수 없다.
"""
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
for name in ("A.json", "B.json"):
    data = json.loads((here / name).read_text(encoding="utf-8"))
    items = data["items"]
    over = [len(i["text"]) - i["limit"] for i in items if len(i["text"]) > i["limit"]]
    print(f"== {data['condition']}")
    print(f"제한을 넘은 문구 {len(over)}/{len(items)}", end="")
    print(f", 넘은 글자 수 평균 {sum(over) / len(over):.1f}, 최대 {max(over)}" if over else "")
    for limit in sorted({i["limit"] for i in items}):
        group = [i for i in items if i["limit"] == limit]
        print(f"  제한 {limit}자: 초과 {sum(len(i['text']) > limit for i in group)}/{len(group)}")
