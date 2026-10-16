// 페이지의 줄 지문 만들기. 브라우저 도구의 javascript_tool 에 그대로 붙여 넣어 실행한다.
// 원문을 저장하지 않고도 "어떤 줄이 추가되거나 사라졌는지"를 비교할 수 있게, 줄마다 SHA-256 앞 8자리만 남긴다.
//   - main 요소가 있으면 그 안, 없으면 body 의 텍스트를 쓴다
//   - 줄 단위로 나누고 공백을 정리하며, 길이 1 이하(세로로 쪼개진 글자 조각 등)는 버린다
//   - 같은 줄은 한 번만 남기고 처음 나온 순서를 지킨다
const el = document.querySelector('main') || document.body;
const lines = el.innerText.split('\n').map(s => s.replace(/\s+/g, ' ').trim()).filter(s => s.length > 1);
const seen = new Set();
const hs = [];
for (const l of lines) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(l));
  const h = Array.from(new Uint8Array(buf)).slice(0, 4).map(b => b.toString(16).padStart(2, '0')).join('');
  if (!seen.has(h)) { seen.add(h); hs.push(h); }
}
hs.join(',');
