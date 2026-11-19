"""상호가 글에 정확히 몇 번 나오는지, 한두 글자 다른 비슷한 표기(오타 의심)가 있는지 센다.
사용: python check_names2.py <글 파일> [기대 횟수=4]"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
NAMES = ["씁쓸한초콜릿", "뒤엉킨실타래", "꼼꼼히마켓", "닭갈비연구소", "읊조림스튜디오", "곰곰이랩",
         "Quillbert Studio", "Zephyrine", "Brühlmann", "Mo-Ning Bloom 7", "OATHKEEPER-3000", "홀쭉이 Café"]
text = Path(sys.argv[1]).read_text(encoding="utf-8")
expect = int(sys.argv[2]) if len(sys.argv) > 2 else 4


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


ok = 0
suspects = []
for n in NAMES:
    c = text.count(n)
    if c == expect:
        ok += 1
    else:
        print(f"{n}: 정확히 나온 횟수 {c} (기대 {expect})")
    # 이름과 한 글자 다른 조각 찾기 (정확히 같은 조각은 제외)
    L = len(n)
    for i in range(len(text) - L + 1):
        w = text[i:i + L]
        if w != n and lev(w, n) == 1 and w.strip() and (n[:2] in w or n[-2:] in w):
            suspects.append((n, w))
print(f"이름 {len(NAMES)}개 중 정확히 {expect}번 나온 것 {ok}개")
print("한 글자 다른 의심 표기:", sorted(set(suspects)) or "없음")
print("글자 수:", len(text))
