"""상호가 글에 정확히 몇 번 나오는지, 한 글자 다른 비슷한 이름(오타 의심)이 있는지 센다.
사용: python validation-data/typo-trace/check_names.py <글 파일> [names.json]"""
import json
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
text = Path(sys.argv[1]).read_text(encoding="utf-8")
names = json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else here / "names.json").read_text(encoding="utf-8"))["names"]
words = re.findall(r"[가-힣]+", text)


def near(a, b):
    """같은 길이에서 한 글자만 다르거나, 길이가 1 다르고 한 글자 빠지거나 더한 경우."""
    if a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if abs(len(a) - len(b)) == 1:
        s, l = (a, b) if len(a) < len(b) else (b, a)
        return any(l[:i] + l[i + 1:] == s for i in range(len(l)))
    return False


exact_ok = 0
suspects = []
for n in names:
    # 이름 뒤에 조사가 붙은 형태를 허용하려고 단어 앞부분 일치로 센다
    c = sum(w.startswith(n) for w in words)
    if c == 2:
        exact_ok += 1
    else:
        print(f"{n}: 정확히 나온 횟수 {c} (기대 2)")
    for w in words:
        for k in range(max(2, len(n) - 1), len(n) + 2):
            if len(w) >= k and near(w[:k], n) and not w.startswith(n):
                suspects.append((n, w))
print(f"이름 {len(names)}개 중 정확히 2번 나온 것 {exact_ok}개")
print("한 글자 다른 의심 표기:", sorted(set(suspects)) or "없음")
