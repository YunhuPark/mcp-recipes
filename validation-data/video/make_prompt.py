"""영상 속 글자 시험용 지시문을 만든다. 라벨 문구는 무작위이고 prompt.txt 에만 들어 있다.
채점할 때까지 Claude는 prompt.txt 를 열지 않는다(블라인드). 사용: python validation-data/video/make_prompt.py"""
import json
import os
import random
from pathlib import Path

here = Path(__file__).resolve().parent
seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
FRUIT = ["유자", "복숭아", "자두", "무화과", "블루베리", "망고", "감귤", "체리"]
KIND = ["잼", "차", "청", "그래놀라", "스프레드", "시럽"]
labels = [f"{f} {rnd.choice(KIND)} {rnd.choice([150, 200, 250, 300, 350, 400, 450])}g" for f in rnd.sample(FRUIT, 4)]
lines = "\n".join(f"{i}. {t}" for i, t in enumerate(labels, 1))
prompt = (
    "가상의 식품 브랜드 제품 4개가 선반에 나란히 놓여 있고, 카메라가 왼쪽에서 오른쪽으로 천천히 지나가며 각 제품 라벨을 가까이 보여주는 "
    "8초 길이의 영상을 만들어 줘. 각 제품 라벨에는 아래 한국어 문구가 한 글자도 바뀌지 않고 그대로, 영상 내내 같은 모양으로 보여야 해.\n\n"
    f"{lines}\n\n"
    "배경 음악이나 말소리는 필요 없어. 라벨 문구 외에 다른 글자는 넣지 마."
)
(here / "prompt.txt").write_text(prompt, encoding="utf-8")
(here / "meta.json").write_text(json.dumps({"seed": seed, "label_count": len(labels)}, indent=1), encoding="utf-8")
print("prompt.txt 를 만들었습니다 (문구 4개, 내용은 출력하지 않음)")
