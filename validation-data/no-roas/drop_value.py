"""ads-noinstr 와 같은 방식의 CSV에서 '전환가치' 열을 없앤다 (ROAS를 계산할 수 없게). 사용: python drop_value.py <in.csv> <out.csv>"""
import csv, sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
    rows = list(csv.reader(f))
i = rows[0].index("전환가치")
with open(sys.argv[2], "w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows([r[:i] + r[i + 1:] for r in rows])
print("전환가치 열을 뺐습니다")
