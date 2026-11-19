"""더 어려운 합성 후기 40개를 만든다. 정답(주제, 감정)은 truth.json 에만 저장하고 화면에는 후기만 출력한다.
규칙(분류하는 쪽에 미리 알려 주는 것): 주제 = 후기가 가장 강조한 것. "그런데/근데", "무엇보다", "제일 중요한 건" 뒤의 내용을 강조한 것으로 본다.
감정 = 강조한 것에 대한 평가 (긍정/부정). 5개 주제: 배송, 품질, 가격, 응대, 포장.
1차(reviews/)보다 어려운 점: 줄임말과 오타, 이모지, 두 개 이상의 주제가 섞임, 강조한 것과 다른 것의 감정이 반대인 경우."""
import json
import os
import random
from pathlib import Path

here = Path(__file__).resolve().parent
seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)

BANK = {
    ("배송", "긍정"): ["배송이 진짜 빨랐어요", "다음 날 바로 와서 놀랐어요", "약속한 날에 딱 맞춰 왔어요", "배송 넘 빨라서 좋았음ㅎㅎ"],
    ("배송", "부정"): ["배송이 너무 늦었어요", "택배가 이틀이나 늦게 왔어요", "배송 넘 늦게옴ㅠㅠ", "주문하고 일주일 만에 왔네요"],
    ("품질", "긍정"): ["품질이 기대 이상이에요", "마감이 깔끔하고 튼튼해요", "생각보다 질이 좋음", "한 달 써도 멀쩡해요"],
    ("품질", "부정"): ["품질이 별로예요", "며칠 만에 고장 났어요", "마감이 엉망이에요", "색이 사진이랑 완전 달라요;;"],
    ("가격", "긍정"): ["가격이 착해요", "이 가격이면 대만족이에요", "가성비 최고예요", "할인받아서 싸게 샀어요"],
    ("가격", "부정"): ["가격이 너무 비싸요", "이 가격은 좀 아닌 듯해요", "다른 데보다 비싸서 아쉬워요", "값이 며칠 뒤에 내려서 속상해요"],
    ("응대", "긍정"): ["문의 답변이 빨랐어요", "상담원분이 친절했어요", "교환을 바로 해주셔서 감사했어요", "응대가 정말 좋았음"],
    ("응대", "부정"): ["문의에 답이 없어요", "상담원이 불친절했어요", "환불해달라니까 계속 미뤘어요", "응대가 최악이었음ㅠ"],
    ("포장", "긍정"): ["포장이 꼼꼼했어요", "선물용으로 포장이 예뻐요", "안전하게 잘 포장돼 왔어요", "포장 깔끔함"],
    ("포장", "부정"): ["포장이 너무 허술했어요", "상자가 찌그러져 왔어요", "포장 대충해서옴;;", "뽁뽁이도 없이 왔어요"],
}
CATS = ["배송", "품질", "가격", "응대", "포장"]
EMO = {"긍정": ["👍", "😊", "❤️"], "부정": ["😡", "😢", "👎"]}
items, truth = [], []


def phrase(cat, sent):
    return rnd.choice(BANK[(cat, sent)])


def pick_other(main):
    return rnd.choice([c for c in CATS if c != main])


def add(kind, text, cat, sent):
    if rnd.random() < 0.3:
        text += " " + rnd.choice(EMO[sent])
    items.append(text)
    truth.append({"kind": kind, "category": cat, "sentiment": sent})


plan = ["plain"] * 8 + ["but"] * 7 + ["above_all"] * 7 + ["most_important"] * 6 + ["three"] * 6 + ["cross"] * 6
for kind in plan:
    main = rnd.choice(CATS)
    sm = rnd.choice(["긍정", "부정"])
    other = pick_other(main)
    so = rnd.choice(["긍정", "부정"])
    if kind == "plain":
        add(kind, phrase(main, sm), main, sm)
    elif kind == "but":
        add(kind, f"{phrase(other, so)}. 그런데 {phrase(main, sm)}" if rnd.random() < 0.5 else f"{phrase(other, so)} 근데 {phrase(main, sm)}", main, sm)
    elif kind == "above_all":
        add(kind, f"{phrase(other, so)}. 무엇보다 {phrase(main, sm)}", main, sm)
    elif kind == "most_important":
        add(kind, f"{phrase(other, so)}. 근데 제일 중요한 건 {phrase(main, sm)}", main, sm)
    elif kind == "three":
        o2 = rnd.choice([c for c in CATS if c not in (main, other)])
        add(kind, f"{phrase(other, so)}. {phrase(o2, rnd.choice(['긍정', '부정']))}. 그런데 {phrase(main, sm)}", main, sm)
    else:  # cross: 강조한 것과 다른 것의 감정이 반대
        so2 = "부정" if sm == "긍정" else "긍정"
        add(kind, f"{phrase(other, so2)}. 무엇보다 {phrase(main, sm)}", main, sm)

order = list(range(len(items)))
rnd.shuffle(order)
shuffled = [items[i] for i in order]
(here / "truth.json").write_text(json.dumps({"seed": seed, "items": [dict(truth[i], n=k + 1) for k, i in enumerate(order)]},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
(here / "reviews.txt").write_text("\n".join(f"{k + 1}. {t}" for k, t in enumerate(shuffled)), encoding="utf-8")
print("\n".join(f"{k + 1}. {t}" for k, t in enumerate(shuffled)))
