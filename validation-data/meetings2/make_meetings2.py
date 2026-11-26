"""담당이나 기한이 빠진 할 일이 섞인 합성 회의록 3개를 만든다. 정답(원래 없는 칸은 null)은 truth.json 에 저장한다.
회의록(notes.txt)에는 담당만 없는 할 일, 기한만 없는 할 일, 둘 다 없는 할 일이 섞여 있고, 에이전트에게는 이런 말을 하지 않는다.
사용: python make_meetings2.py <notes.txt를 둘 폴더> <truth.json을 둘 폴더>"""
import json
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

in_dir, secret_dir = Path(sys.argv[1]), Path(sys.argv[2])
in_dir.mkdir(parents=True, exist_ok=True)
secret_dir.mkdir(parents=True, exist_ok=True)
seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
WD = "월화수목금토일"
PEOPLE = ["하늘", "도윤", "서아", "지호", "나은", "건우", "예린"]
TASKS = [
    "신규 캠페인 랜딩 문구 초안 작성", "주간 성과 리포트 정리", "인스타그램 카드뉴스 6장 제작", "뉴스레터 발송 일정 확정",
    "경쟁사 가격표 조사", "광고 소재 A/B 안 2개 준비", "고객 인터뷰 질문지 작성", "블로그 글 3편 일정 잡기",
    "쿠폰 정산 숫자 확인", "제휴 문의 메일 회신", "촬영 장소 후보 3곳 확인", "이벤트 당첨자 안내문 작성",
    "상세페이지 이미지 교체", "고객 문의 템플릿 정리", "경품 배송 업체 견적 받기", "행사 현수막 시안 요청",
]
DONE = ["지난 회의에서 정한 로고 수정은 이미 끝났음", "예산 승인은 지난주에 완료됨", "촬영 섭외는 어제 마무리됨"]
IDEA = ["숏폼 영상을 해볼지는 의견만 나눴고 결정하지 않음", "새 채널 개설은 다음에 다시 이야기하기로 함", "가격 인상은 논의만 하고 보류"]
V2 = len(sys.argv) > 3 and sys.argv[3] == "v2"  # v2: 네 유형 4개씩, "둘 다 없음"에 의견 같은 문구를 쓰지 않는다
kinds = ["full", "no_owner", "no_due", "neither"] * 4 if V2 else ["full"] * 6 + ["no_owner"] * 4 + ["no_due"] * 4 + ["neither"] * 1
rnd.shuffle(kinds)
tasks = rnd.sample(TASKS, len(kinds))
PER = [6, 5, 5] if V2 else [5, 5, 5]
meetings, truth = [], []
start = date(2026, 11, 23)
k = 0
for i in range(3):
    meet = start + timedelta(days=i)
    people = rnd.sample(PEOPLE, 4)
    lines, items = [], []
    for _ in range(PER[i]):
        t, kind = tasks[k], kinds[k]
        k += 1
        owner = rnd.choice(people) if kind in ("full", "no_due") else None
        due = None
        if kind in ("full", "no_owner"):
            d = meet + timedelta(days=rnd.randint(2, 12))
            while d.weekday() >= 5:
                d += timedelta(days=1)
            due = d
        phrase = f"{due.month}월 {due.day}일({WD[due.weekday()]})까지" if due else ""
        if kind == "full":
            line = rnd.choice(["{w}가 {p} {t} 하기로 함", "{t}은(는) {w} 담당, {p} 마감", "{w}: {t} ({p})"]).format(w=owner, p=phrase, t=t)
        elif kind == "no_owner":
            line = rnd.choice(["{t} 필요함, {p}", "{t} ({p})", "{p} {t} 진행해야 함"]).format(p=phrase, t=t)
        elif kind == "no_due":
            line = rnd.choice(["{w}가 {t} 하기로 함", "{t}은(는) {w} 담당", "{w}: {t}"]).format(w=owner, t=t)
        else:
            line = rnd.choice(["{t} 해야 함", "{t} 진행하기로 함"] if V2 else ["{t} 해야 함", "{t} 논의 필요", "{t}도 해야 한다는 의견"]).format(t=t)
        lines.append("- " + line)
        items.append({"task": t, "owner": owner, "due": due.isoformat() if due else None, "kind": kind})
    lines.insert(rnd.randint(0, len(lines)), "- " + rnd.choice(DONE))
    lines.insert(rnd.randint(0, len(lines)), "- " + rnd.choice(IDEA))
    meetings.append(f"회의록 {i + 1} ({meet.year}-{meet.month:02d}-{meet.day:02d} {WD[meet.weekday()]})\n참석: {', '.join(people)}\n" + "\n".join(lines))
    truth.append({"meeting": i + 1, "date": meet.isoformat(), "items": items})
(in_dir / "notes.txt").write_text("\n\n".join(meetings), encoding="utf-8")
(secret_dir / "truth.json").write_text(json.dumps({"seed": seed, "meetings": truth}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"notes.txt 3개 회의, 할 일 {len(kinds)}개 (유형은 숨김)")
