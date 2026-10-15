#!/usr/bin/env python3
"""게시 전 점검 (공개 저장소용).

무엇을 검사하나
  1. 비밀값과 개인 정보 패턴: 이메일, 토큰, 키, 전화번호 등 (모든 텍스트 파일)
  2. 로컬 차단 목록: `.check-blocklist.local` 에 적은 단어 (저장소에 올라가지 않음)
  3. 글 점검: posts/daily 글의 500자 제한, 글자 수 표기, 브랜드명 철자
  4. 상태 일치: posts/schedule.md 의 상태와 각 글 파일의 상태
  5. 아직 푸시하지 않은 커밋: 작성자 이메일이 noreply 인지, 메시지에 비밀값이 없는지
  6. 근거표: 검수완료/게시됨 글은 `## 근거표`가 있어야 한다. 각 행의 인용이 근거 파일에 실제로 있는지,
     본문이 대조한 뒤에 바뀌지 않았는지(해시)를 확인한다. 근거표가 **맞는지**는 사람과 대조 작업이 판단한다.

한계
  - 패턴으로 찾기 때문에 패턴에 없는 형태의 민감 정보는 놓친다. 올리기 전에 직접 훑어볼 것.
  - 사실 확인과 과장 여부는 검사하지 못한다. 사람이 확인해야 한다.

사용법
  python scripts/check.py              # 파일 + 푸시 전 커밋 점검
  python scripts/check.py --pre-push   # 푸시 훅에서 호출 (동일, 실패 시 푸시 중단)
  python scripts/check.py --root DIR   # 다른 폴더를 점검 (테스트용)
  python scripts/check.py --stamp D03  # 근거표 대조를 끝낸 뒤, 그 시점의 본문 해시와 날짜를 기록
종료 코드: 0 = 통과(경고만 있어도 0), 1 = 오류 있음
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from threads_text import LIMIT as THREADS_LIMIT, threads_len  # noqa: E402  (이모지는 바이트로 세는 한도 계산)

BLOCKLIST_FILE = ".check-blocklist.local"
ALLOWED_EMAIL_DOMAINS = {"users.noreply.github.com", "example.com", "example.org"}
# 도메인 전체가 아니라 정확한 주소만 허용한다 (커밋 메시지의 공동 작성자 표기용 공개 noreply 주소)
ALLOWED_EMAILS = {"noreply@anthropic.com"}
EVIDENCE_STATUSES = {"검수완료", "게시됨"}  # 이 상태의 글은 근거표가 필요하다
EVIDENCE_RESULTS = ("일치", "표현 수정", "미확인")
SKIP_DIRS = {".git"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GitHub 토큰", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("GitHub 토큰(fine-grained)", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("sk- 형태 키", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("Meta/Instagram 토큰", re.compile(r"\b(?:EAA|IGQ)[A-Za-z0-9_-]{20,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("AWS 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Bearer 토큰", re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{16,}")),
    (
        "키 = 값 형태",
        re.compile(
            r"(?i)\b(?:access_?token|api_?key|client_?secret|secret|password|passwd)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{12,}"
        ),
    ),
    ("한국 휴대전화 번호", re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b")),
    ("주민등록번호 형태", re.compile(r"\b\d{6}-[1-4]\d{6}\b")),
]

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name == BLOCKLIST_FILE:
            continue
        yield path, rel


def load_blocklist(root: Path) -> list[str]:
    path = root / BLOCKLIST_FILE
    if not path.exists():
        warn(f"로컬 차단 목록({BLOCKLIST_FILE})이 없습니다. 개인 키워드 검사를 건너뜁니다.")
        return []
    text = read_text(path) or ""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def scan_text(label: str, text: str, blocklist: list[str]) -> None:
    for m in EMAIL_RE.finditer(text):
        domain = m.group(1).lower()
        if m.group(0).lower() in ALLOWED_EMAILS:
            continue
        if domain not in ALLOWED_EMAIL_DOMAINS:
            err(f"{label}: 이메일 주소로 보이는 문자열 (도메인 {domain})")
    for name, rx in SECRET_PATTERNS:
        if rx.search(text):
            err(f"{label}: {name} 패턴이 발견되었습니다")
    lowered = text.lower()
    for word in blocklist:
        if word.lower() in lowered:
            # 차단 단어 자체를 출력하지 않는다 (출력도 기록에 남을 수 있음)
            err(f"{label}: 로컬 차단 목록의 단어가 발견되었습니다")


def check_files(root: Path, blocklist: list[str]) -> None:
    for path, rel in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        scan_text(str(rel).replace("\\", "/"), text, blocklist)


def first_code_block(text: str) -> str | None:
    m = re.search(r"```[^\n]*\r?\n(.*?)\r?\n```", text, re.S)
    return m.group(1).replace("\r", "") if m else None


def all_code_blocks(text: str) -> list[str]:
    return [b.replace("\r", "") for b in re.findall(r"```[^\n]*\r?\n(.*?)\r?\n```", text, re.S)]


def check_brand_spelling(label: str, blocks: list[str]) -> None:
    for block in blocks:
        if "모닝블름" in block and "모닝블룸" not in block:
            err(f"{label}: 브랜드명 오타('모닝블름')가 올바른 표기('모닝블룸') 없이 단독으로 있습니다")


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def body_hash(block: str) -> str:
    return hashlib.sha256(norm_ws(block.replace("\r", "")).encode("utf-8")).hexdigest()[:12]


def evidence_section(text: str) -> str | None:
    m = re.search(r"^## 근거표[^\n]*\n(.*?)(?=^## |\Z)", text.replace("\r", ""), re.S | re.M)
    return m.group(1) if m else None


def check_evidence(label: str, text: str, block: str, root: Path) -> None:
    """검수완료/게시됨 글의 근거표를 점검한다. 내용이 사실인지는 판단하지 못한다."""
    section = evidence_section(text)
    if section is None:
        err(f"{label}: '## 근거표'가 없습니다 (본문의 사실 주장마다 근거 파일과 인용, 대조 결과가 필요)")
        return
    stamp = re.search(r"대조일:\s*(\d{4}-\d{2}-\d{2}).*?본문 해시:\s*([0-9a-f]{12})", section)
    if not stamp:
        err(f"{label}: 근거표에 '- 대조일: YYYY-MM-DD / 본문 해시: …' 줄이 없습니다 (`check.py --stamp`로 기록)")
    elif stamp.group(2) != body_hash(block):
        err(f"{label}: 본문이 근거표를 대조한 뒤에 바뀌었습니다. 다시 대조하고 `check.py --stamp`로 기록하세요")
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|?$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[:1] == ["본문 주장"]:
            continue
        rows.append(cells)
    if not rows:
        err(f"{label}: 근거표에 행이 없습니다")
    for i, cells in enumerate(rows, 1):
        if len(cells) != 4 or not all(cells):
            err(f"{label}: 근거표 {i}번째 행은 '본문 주장 | 근거 파일 | 근거 인용 | 결과' 네 칸이 모두 채워져야 합니다")
            continue
        _, src, quote, result = cells
        if not result.startswith(EVIDENCE_RESULTS):
            err(f"{label}: 근거표 {i}번째 행의 결과는 {'/'.join(EVIDENCE_RESULTS)} 중 하나로 시작해야 합니다")
        src = src.strip("`")
        if src.startswith("외부:"):
            if not re.search(r"\d{4}-\d{2}-\d{2}", quote):
                err(f"{label}: 근거표 {i}번째 행은 외부 근거를 직접 확인한 날짜(YYYY-MM-DD)를 인용 칸에 적어야 합니다")
            continue
        path = (root / src).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            err(f"{label}: 근거표 {i}번째 행의 근거 파일 '{src}'을 저장소에서 찾지 못했습니다")
            continue
        wanted = norm_ws(quote.strip("`\"' "))
        if not wanted or wanted not in norm_ws(read_text(path) or ""):
            err(f"{label}: 근거표 {i}번째 행의 인용이 '{src}'에 그대로 있지 않습니다 (파일이 바뀌었거나 인용이 틀림)")


def file_status(text: str) -> str:
    m = re.search(r"-\s*상태:\s*\*\*([^*]+)\*\*", text)
    return m.group(1).strip().split()[0] if m else ""


def stamp_post(root: Path, post_id: str) -> int:
    matches = sorted((root / "posts" / "daily").glob(f"{post_id}-*.md"))
    if len(matches) != 1:
        print(f"{post_id} 글 파일을 하나 찾지 못했습니다")
        return 1
    path = matches[0]
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    block = first_code_block(text)
    if block is None or not re.search(r"^## 근거표[^\n]*\n", text, re.M):
        print(f"{path.name}: 본문 코드 블록이나 '## 근거표'가 없습니다")
        return 1
    line = f"- 대조일: {datetime.date.today().isoformat()} / 본문 해시: {body_hash(block)}"
    if re.search(r"^- 대조일:[^\n]*$", text, re.M):
        text = re.sub(r"^- 대조일:[^\n]*$", lambda m: line, text, count=1, flags=re.M)
    else:
        text = re.sub(r"(^## 근거표[^\n]*\n)", lambda m: m.group(1) + line + "\n", text, count=1, flags=re.M)
    path.write_bytes(text.replace("\n", nl).encode("utf-8"))
    print(f"{path.name}: {line}")
    return 0


def check_posts(root: Path) -> None:
    daily = root / "posts" / "daily"
    if daily.exists():
        for path in sorted(daily.glob("D*.md")):
            text = read_text(path) or ""
            label = f"posts/daily/{path.name}"
            block = first_code_block(text)
            if block is None:
                err(f"{label}: 게시 본문(코드 블록)을 찾지 못했습니다")
                continue
            n = len(block)
            limit_n = threads_len(block)  # 이모지는 UTF-8 바이트로 센 값(보수적)
            if limit_n > THREADS_LIMIT:
                err(f"{label}: 본문이 Threads 기준 {limit_n}로 {THREADS_LIMIT} 제한을 넘습니다 (이모지는 바이트로 셈)")
            m = re.search(r"글자 수:\s*(\d+)자", text)
            if m and int(m.group(1)) != n:
                warn(f"{label}: 표기된 글자 수({m.group(1)}자)와 실제({n}자)가 다릅니다")
            check_brand_spelling(label, [block])
            if file_status(text) in EVIDENCE_STATUSES:
                check_evidence(label, text, block, root)
    for path in sorted((root / "posts").glob("0*.md")) if (root / "posts").exists() else []:
        text = read_text(path) or ""
        label = f"posts/{path.name}"
        blocks = all_code_blocks(text)
        for i, b in enumerate(blocks, 1):
            if threads_len(b) > THREADS_LIMIT:
                err(f"{label}: {i}번째 글이 Threads 기준 {threads_len(b)}로 {THREADS_LIMIT} 제한을 넘습니다")
        check_brand_spelling(label, blocks)


def check_status_consistency(root: Path) -> None:
    schedule = root / "posts" / "schedule.md"
    daily = root / "posts" / "daily"
    if not schedule.exists() or not daily.exists():
        return
    text = read_text(schedule) or ""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(D\d{2})\s*\|(.+)\|\s*$", line)
        if not m:
            continue
        cols = [c.strip() for c in ("|" + m.group(2)).split("|")[1:]]
        # 열: 날짜 | 글 | 상태 | 비고
        if len(cols) >= 3:
            rows[m.group(1)] = cols[2]
    files = {p.name[:3]: p for p in daily.glob("D*.md")}
    for key, status in rows.items():
        path = files.get(key)
        if path is None:
            if status not in ("미정", ""):
                err(f"posts/schedule.md: {key} 상태가 '{status}'인데 글 파일이 없습니다")
            continue
        ftext = read_text(path) or ""
        m = re.search(r"-\s*상태:\s*\*\*([^*]+)\*\*", ftext)
        fstatus = m.group(1).strip().split()[0] if m else ""
        if fstatus != status:
            err(f"{key}: 일정표 상태('{status}')와 글 파일 상태('{fstatus}')가 다릅니다")
    for key in files:
        if key not in rows:
            warn(f"posts/daily/{files[key].name}: 일정표에 없는 글입니다")


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True
        )
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_unpushed_commits(root: Path, blocklist: list[str]) -> None:
    upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream is None:
        warn("업스트림 브랜치가 없어 푸시 전 커밋 점검을 건너뜁니다.")
        return
    rng = "@{u}..HEAD"
    shas = (git(root, "rev-list", rng) or "").split()
    if not shas:
        return
    for sha in shas:
        email = (git(root, "log", "-1", "--format=%ae", sha) or "").strip()
        domain = email.split("@")[-1].lower() if "@" in email else ""
        if domain != "users.noreply.github.com":
            err(f"커밋 {sha[:7]}: 작성자 이메일이 noreply 주소가 아닙니다")
        msg = git(root, "log", "-1", "--format=%B", sha) or ""
        scan_text(f"커밋 {sha[:7]} 메시지", msg, blocklist)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="공개 저장소 게시 전 점검")
    ap.add_argument("--root", default=None, help="점검할 폴더 (기본: 이 스크립트의 저장소 루트)")
    ap.add_argument("--pre-push", action="store_true", help="푸시 훅에서 호출")
    ap.add_argument("--no-commits", action="store_true", help="푸시 전 커밋 점검을 건너뜀")
    ap.add_argument("--stamp", metavar="ID", help="근거표 대조를 끝낸 글(예: D03)의 날짜와 본문 해시를 기록")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if args.stamp:
        return stamp_post(root, args.stamp)
    blocklist = load_blocklist(root)

    check_files(root, blocklist)
    check_posts(root)
    check_status_consistency(root)
    if not args.no_commits and (root / ".git").exists():
        check_unpushed_commits(root, blocklist)

    for w in warnings:
        print(f"[경고] {w}")
    for e in errors:
        print(f"[오류] {e}")
    if errors:
        print(f"\n점검 실패: 오류 {len(errors)}개, 경고 {len(warnings)}개."
              + (" 푸시를 중단합니다." if args.pre_push else ""))
        return 1
    print(f"점검 통과: 오류 0개, 경고 {len(warnings)}개. (패턴 기반 점검이라 완전하지 않습니다. 직접 한 번 훑어보세요.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
