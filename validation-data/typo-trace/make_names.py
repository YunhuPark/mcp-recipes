"""오타가 생성 단계에서 생기는지 옮겨 적는 단계에서 생기는지 가리는 시험용 무작위 상호 12개를 만든다.
사용: python validation-data/typo-trace/make_names.py  (names.json 에 저장하고 화면에도 출력)"""
import json
import os
import random
from pathlib import Path

here = Path(__file__).resolve().parent
seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
SYL = list("모닝블룸하늘새봄달빛솔향루미나온린채담결도윤서아지호건예은율휘려담온새")
names = []
while len(names) < 12:
    n = "".join(rnd.choice(SYL) for _ in range(rnd.choice([3, 4])))
    if n not in names and len(set(n)) == len(n):
        names.append(n)
(here / "names.json").write_text(json.dumps({"seed": seed, "names": names}, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(names, ensure_ascii=False))
