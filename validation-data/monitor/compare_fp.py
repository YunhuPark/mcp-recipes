"""기준 지문과 새 지문을 비교한다.

사용: python validation-data/monitor/compare_fp.py <baseline.json> <page_key> <new_fp>

새 지문이 비었거나 기준의 절반에도 못 미치면 "변화"가 아니라 **읽기 실패(로딩이 덜 됨 등)**로 보고한다.
(2026-10-18: 토스 페이지를 열자마자 읽었더니 지문이 비어 있었다. 그대로 비교하면 "142줄 모두 삭제"로 보인다.)
종료 코드: 0 = 정상 비교(변화 유무와 무관), 2 = 읽기 실패 의심
"""
import json
import sys

LOW_RATIO = 0.5  # 새 줄 수가 기준의 이 비율보다 적으면 읽기 실패로 본다

base = json.load(open(sys.argv[1], encoding="utf-8"))
key, new = sys.argv[2], sys.argv[3]
old_list = base["pages"][key]["fp"].split(",")
new_list = [h for h in new.split(",") if h]
if len(new_list) < len(old_list) * LOW_RATIO:
    print(f"{key}: 읽기 실패 의심. 기준 {len(old_list)}줄인데 새로 읽은 것은 {len(new_list)}줄입니다. "
          "변화로 판단하지 말고 페이지가 다 뜬 뒤 다시 읽으세요.")
    sys.exit(2)
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
