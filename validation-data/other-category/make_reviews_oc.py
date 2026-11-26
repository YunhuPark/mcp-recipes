"""5개 주제에 맞는 후기 12개와 어디에도 안 맞는 후기 8개를 섞는다. 정답은 truth.json(해당 없음은 category null)에 저장.
사용: python make_reviews_oc.py <reviews.txt를 둘 폴더> <truth.json을 둘 폴더>"""
import json, os, random, sys
from pathlib import Path

rnd = random.Random(int.from_bytes(os.urandom(4), "big"))
IN = [("배송", "긍정", "주문한 다음 날 바로 도착했어요"), ("배송", "부정", "배송이 일주일이나 걸렸어요"),
      ("품질", "긍정", "마감이 깔끔하고 튼튼해요"), ("품질", "부정", "며칠 쓰니 바로 고장 났어요"),
      ("가격", "긍정", "가성비가 정말 훌륭합니다"), ("가격", "부정", "비슷한 제품보다 너무 비싸요"),
      ("응대", "긍정", "문의에 바로 답해 주셔서 감사했어요"), ("응대", "부정", "환불 요청했는데 계속 떠넘기기만 해요"),
      ("포장", "긍정", "포장이 꼼꼼해서 안전하게 왔어요"), ("포장", "부정", "상자가 찌그러진 채로 왔어요"),
      ("품질", "긍정", "한 달 써도 처음 그대로예요"), ("배송", "긍정", "약속한 날짜보다 일찍 왔어요")]
OUT = [("부정", "앱이 결제 화면에서 자꾸 꺼져요"), ("부정", "매장 주차장이 너무 좁았어요"), ("부정", "광고 문자가 하루에 세 번씩 와요"),
       ("부정", "회원 가입 절차가 너무 길어요"), ("긍정", "매장에서 나오던 음악이 좋았어요"), ("부정", "홈페이지 로그인이 계속 실패해요"),
       ("긍정", "홈페이지 디자인이 보기 편해졌네요"), ("부정", "영업시간이 너무 짧아 두 번 헛걸음했어요")]
items = [{"category": c, "sentiment": s, "text": t} for c, s, t in IN] + [{"category": None, "sentiment": s, "text": t} for s, t in OUT]
rnd.shuffle(items)
Path(sys.argv[1], "reviews.txt").write_text("\n".join(f"{i}. {x['text']}" for i, x in enumerate(items, 1)), encoding="utf-8")
Path(sys.argv[2], "truth.json").write_text(json.dumps([dict(x, n=i) for i, x in enumerate(items, 1)], ensure_ascii=False, indent=1), encoding="utf-8")
print("reviews.txt 20개")
