"""합성 회의록 3개를 만든다. 정답(할 일, 담당, 기한)은 truth.json 에만 저장하고 화면에는 회의록만 출력한다."""
import json
import random
import os
from datetime import date, timedelta
from pathlib import Path

seed = int.from_bytes(os.urandom(4), "big")
rnd = random.Random(seed)
OUT = Path(__file__).resolve().parent

PEOPLE = ["하늘", "도윤", "서아", "지호", "나은", "건우", "예린"]
TASKS = [
    "신규 캠페인 랜딩 문구 초안 작성", "주간 성과 리포트 정리", "인스타그램 카드뉴스 6장 제작", "뉴스레터 발송 일정 확정",
    "경쟁사 가격표 조사", "광고 소재 A/B 안 2개 준비", "고객 인터뷰 질문지 작성", "블로그 글 3편 일정 잡기",
    "쿠폰 정산 숫자 확인", "제휴 문의 메일 회신", "촬영 장소 후보 3곳 확인", "이벤트 당첨자 안내문 작성",
]
DISTRACT_DONE = ["지난 회의에서 정한 로고 수정은 이미 끝났음", "예산 승인은 지난주에 완료됨", "촬영 섭외는 어제 마무리됨"]
DISTRACT_IDEA = ["숏폼 영상을 해볼지는 의견만 나눴고 결정하지 않음", "새 채널 개설은 다음에 다시 이야기하기로 함", "가격 인상은 논의만 하고 보류"]
WD = "월화수목금토일"


def fmt_rel(meet, due):
    d = (due - meet).days
    base = f"{due.month}월 {due.day}일({WD[due.weekday()]})"
    style = rnd.choice(["abs", "abs", "rel"])
    if style == "rel" and 1 <= d <= 7:
        return f"이번 주 {WD[due.weekday()]}요일까지" if due.isocalendar()[1] == meet.isocalendar()[1] else f"다음 주 {WD[due.weekday()]}요일까지", due
    return f"{base}까지", due


meetings, truth = [], []
used = rnd.sample(TASKS, 12)
start = date(2026, 10, 26)
for i in range(3):
    meet = start + timedelta(days=i)
    people = rnd.sample(PEOPLE, 4)
    n = rnd.choice([4, 5])
    lines, items = [], []
    for k in range(n):
        task = used.pop()
        who = rnd.choice(people)
        due = meet + timedelta(days=rnd.randint(2, 12))
        while due.weekday() >= 5:
            due += timedelta(days=1)
        phrase, due = fmt_rel(meet, due)
        form = rnd.choice(["{w}가 {p} {t}하기로 함", "{t}은(는) {w} 담당, {p} 마감", "{w}: {t} ({p})"])
        form = form.replace("{t}하기", "{t} 진행하기") if rnd.random() < 0.0 else form
        lines.append("- " + form.format(w=who, p=phrase, t=task))
        items.append({"task": task, "owner": who, "due": due.isoformat()})
    lines.insert(rnd.randint(0, len(lines)), "- " + rnd.choice(DISTRACT_DONE))
    lines.insert(rnd.randint(0, len(lines)), "- " + rnd.choice(DISTRACT_IDEA))
    text = f"회의록 {i + 1} ({meet.year}-{meet.month:02d}-{meet.day:02d} {WD[meet.weekday()]})\n참석: {', '.join(people)}\n" + "\n".join(lines)
    meetings.append(text)
    truth.append({"meeting": i + 1, "date": meet.isoformat(), "items": items})

(OUT / "meeting_truth.json").write_text(json.dumps({"seed": seed, "meetings": truth}, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "meeting_notes.txt").write_text("\n\n".join(meetings), encoding="utf-8")
print("\n\n".join(meetings))
