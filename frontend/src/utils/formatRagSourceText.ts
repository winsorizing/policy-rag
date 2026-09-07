/**
 * RAG/벡터 스토어에 섞인 HTML 조각을 읽기 쉬운 일반 텍스트로 정리.
 * (화면에 `<br>` 그대로 나오는 문제 방지)
 */
export function formatRagSourceText(raw: string | undefined | null): string {
  let t = (raw ?? '').trim();
  if (!t) return '';

  t = t.replace(/<br\s*\/?>/gi, '\n');
  t = t.replace(/<\/p>/gi, '\n');
  t = t.replace(/<p[^>]*>/gi, '');
  t = t.replace(/<[^>]+>/g, '');
  t = t.replace(/&nbsp;/gi, ' ');
  t = t.replace(/&amp;/g, '&');
  t = t.replace(/&lt;/g, '<');
  t = t.replace(/&gt;/g, '>');
  t = t.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
  t = t.replace(/\n{3,}/g, '\n\n');
  return t.trim();
}
