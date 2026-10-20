"""기준 지문과 새 지문을 비교한다.

사용: python validation-data/monitor/compare_fp.py <baseline.json> <page_key> <new_fp>

new_fp 는 fingerprint.js 가 내는 문자열 그대로(끝의 '#체크섬' 포함)를 넣을 수 있다.
  - 체크섬이 맞지 않으면 옮겨 적다가 틀린 것이므로 비교하지 않고 종료한다 (종료 코드 3)
  - 새 지문이 비었거나 기준의 절반에도 못 미치면 "변화"가 아니라 **읽기 실패(로딩이 덜 됨 등)**로 보고한다 (종료 코드 2)
    (2026-10-18: 토스 페이지를 열자마자 읽었더니 지문이 비어 있었다. 그대로 비교하면 "142줄 모두 삭제"로 보인다.)
  - 정상 비교는 종료 코드 0 (변화 유무와 무관)
"""
import hashlib
import json
import sys

LOW_RATIO = 0.5  # 새 줄 수가 기준의 이 비율보다 적으면 읽기 실패로 본다


def checksum(fp: str) -> str:
    return hashlib.sha256(fp.encode("utf-8")).hexdigest()[:8]


def main(argv: list[str]) -> int:
    base = json.load(open(argv[1], encoding="utf-8"))
    key, new = argv[2], argv[3]
    if "#" in new:
        new, given = new.rsplit("#", 1)
        if checksum(new) != given:
            print(f"{key}: 체크섬이 맞지 않습니다. 지문을 옮겨 적다가 틀렸을 수 있어 비교하지 않습니다. 다시 붙여 넣으세요.")
            return 3
    old_list = base["pages"][key]["fp"].split(",")
    new_list = [h for h in new.split(",") if h]
    if len(new_list) < len(old_list) * LOW_RATIO:
        print(f"{key}: 읽기 실패 의심. 기준 {len(old_list)}줄인데 새로 읽은 것은 {len(new_list)}줄입니다. "
              "변화로 판단하지 말고 페이지가 다 뜬 뒤 다시 읽으세요.")
        return 2
    old_set, new_set = set(old_list), set(new_list)
    added = [h for h in new_list if h not in old_set]
    removed = [h for h in old_list if h not in new_set]
    print(f"{key}: 기준 {len(old_list)}줄, 새 {len(new_list)}줄, 추가 {len(added)}, 삭제 {len(removed)}")
    if added:
        print("추가된 줄 지문:", ",".join(added))
    if removed:
        print("삭제된 줄 지문:", ",".join(removed))
    same_order = [h for h in new_list if h in old_set] == [h for h in old_list if h in new_set]
    print("공통 줄의 순서:", "같음" if same_order else "바뀜")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
