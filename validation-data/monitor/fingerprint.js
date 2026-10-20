// 페이지의 줄 지문 만들기. 브라우저 도구의 javascript_tool 에 그대로 붙여 넣어 실행한다.
// 원문을 저장하지 않고도 "어떤 줄이 추가되거나 사라졌는지"를 비교할 수 있게, 줄마다 SHA-256 앞 8자리만 남긴다.
//   - main 요소가 있으면 그 안, 없으면 body 의 텍스트를 쓴다
//   - 줄 단위로 나누고 공백을 정리하며, 길이 1 이하(세로로 쪼개진 글자 조각 등)는 버린다
//   - 같은 줄은 한 번만 남기고 처음 나온 순서를 지킨다
//   - 결과 끝에 '#체크섬'(지문 전체의 SHA-256 앞 8자리)을 붙인다. 지문을 옮겨 적다가 한 글자가 틀리면
//     compare_fp.py 가 체크섬 불일치로 알려 준다 (2026-10-20: 손으로 옮기다 한 글자가 틀려 가짜 변화 1건이 나온 적이 있음)
const hex = async (s) => {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).slice(0, 4).map(b => b.toString(16).padStart(2, '0')).join('');
};
const el = document.querySelector('main') || document.body;
const lines = el.innerText.split('\n').map(s => s.replace(/\s+/g, ' ').trim()).filter(s => s.length > 1);
const seen = new Set();
const hs = [];
for (const l of lines) {
  const h = await hex(l);
  if (!seen.has(h)) { seen.add(h); hs.push(h); }
}
const joined = hs.join(',');
joined + '#' + await hex(joined);
