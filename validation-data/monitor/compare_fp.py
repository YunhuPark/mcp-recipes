"""기준 지문과 새 지문을 비교한다. 사용: python compare_fp.py <baseline.json> <page_key> <new_fp>"""
import json
import sys

base = json.load(open(sys.argv[1], encoding="utf-8"))
key, new = sys.argv[2], sys.argv[3]
old_list = base["pages"][key]["fp"].split(",")
new_list = new.split(",")
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
