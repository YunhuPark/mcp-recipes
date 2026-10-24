"""합성 고객 후기 40개를 만든다. 정답(주제, 감정)은 reviews_truth.json 에만 저장하고 화면에는 후기만 출력한다.
규칙: 주제 = 후기에서 가장 중요하게 말한 것 (그러나/하지만 뒤의 내용이 주된 평가), 감정 = 전체 평가."""
import json
import os
import random
from pathlib import Path

seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
OUT = Path(__file__).resolve().parent

BANK = {
    ("배송", "긍정"): ["주문한 다음 날 바로 도착했어요", "배송이 정말 빨라서 놀랐습니다", "약속한 날짜보다 일찍 와서 좋았어요"],
    ("배송", "부정"): ["배송이 일주일이나 걸렸어요", "택배가 이틀 늦게 왔고 연락도 없었습니다", "배송 중에 분실될 뻔했어요"],
    ("품질", "긍정"): ["마감이 깔끔하고 튼튼해요", "사진보다 실물이 훨씬 좋습니다", "한 달 써도 처음 그대로예요"],
    ("품질", "부정"): ["받자마자 한쪽이 깨져 있었어요", "며칠 쓰니 바로 고장 났습니다", "색이 사진과 완전히 달라요"],
    ("가격", "긍정"): ["이 가격에 이 정도면 만족해요", "할인받아서 부담 없이 샀습니다", "가성비가 훌륭합니다"],
    ("가격", "부정"): ["비슷한 제품보다 너무 비싸요", "가격 대비 구성이 허술합니다", "며칠 뒤에 값이 내려서 속상했어요"],
    ("응대", "긍정"): ["문의에 바로 답해 주셔서 감사했어요", "교환 요청을 친절하게 처리해 주셨습니다", "상담원이 끝까지 챙겨 줬어요"],
    ("응대", "부정"): ["문의 글에 일주일째 답이 없어요", "환불을 요청했더니 계속 떠넘기기만 했습니다", "상담원 말투가 불친절했어요"],
    ("포장", "긍정"): ["포장이 꼼꼼해서 안전하게 왔어요", "선물하기 좋게 포장되어 있었습니다"],
    ("포장", "부정"): ["상자가 찌그러진 채로 왔어요", "포장이 너무 부실해서 걱정됐습니다"],
}
CATS = ["배송", "품질", "가격", "응대", "포장"]
reviews, truth = [], []


def add(text, cat, sent, kind):
    reviews.append(text)
    truth.append({"n": len(reviews), "category": cat, "sentiment": sent, "kind": kind})


# 일반 후기 30개 (주제 5개 x 감정 2개, 고르게)
combos = [(c, s) for c in CATS for s in ("긍정", "부정")] * 3
rnd.shuffle(combos)
for c, s in combos[:30]:
    add(rnd.choice(BANK[(c, s)]) + rnd.choice(["", ".", " 추천합니다", " 다음에 또 살게요", " 참고하세요"] if s == "긍정" else ["", "."]), c, s, "plain")

# 헷갈리는 후기 10개
add("배송은 빨랐는데 제품이 불량이었어요", "품질", "부정", "mixed")
add("가격은 비싸지만 품질이 정말 좋아서 만족합니다", "품질", "긍정", "mixed")
add("포장은 별로였지만 상담원이 끝까지 챙겨 줘서 고마웠어요", "응대", "긍정", "mixed")
add("배송 정말 빠르네요, 2주 만에 왔어요", "배송", "부정", "sarcasm")
add("품질 진짜 대단하네요, 하루 만에 부러졌어요", "품질", "부정", "sarcasm")
add("가격이 싸다고 했는데 배송비까지 합치면 전혀 싸지 않아요", "가격", "부정", "negation")
add("고장 난 적은 없어서 만족해요", "품질", "긍정", "negation")
add("답변이 느리다는 후기를 봤는데 저는 바로 받았어요", "응대", "긍정", "negation")
add("받자마자 상자가 눌려 있었지만 내용물은 멀쩡해서 괜찮았어요", "포장", "긍정", "mixed")
add("할인 쿠폰 쓰고도 비싸다고 느꼈어요", "가격", "부정", "plain")

order = list(range(len(reviews)))
rnd.shuffle(order)
shuffled = [reviews[i] for i in order]
shuffled_truth = [dict(truth[i], n=k + 1) for k, i in enumerate(order)]
(OUT / "reviews_truth.json").write_text(json.dumps({"seed": seed, "items": shuffled_truth}, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "reviews.txt").write_text("\n".join(f"{k + 1}. {t}" for k, t in enumerate(shuffled)), encoding="utf-8")
print("\n".join(f"{k + 1}. {t}" for k, t in enumerate(shuffled)))
