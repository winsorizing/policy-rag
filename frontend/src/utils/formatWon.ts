/** 상세·표용 금액 (억·만 병기) */
export function won(n: number): string {
  const value = Math.max(0, Math.floor(n));
  const eok = Math.floor(value / 100_000_000);
  const restAfterEok = value % 100_000_000;
  const man = Math.floor(restAfterEok / 10_000);
  const wonUnit = restAfterEok % 10_000;

  let detailed = '';
  if (eok > 0) detailed += `${eok}억`;
  if (man > 0) detailed += ` ${man}만`;
  if (wonUnit > 0) detailed += ` ${wonUnit}원`;
  if (!detailed) detailed = '0원';

  return `${value.toLocaleString('ko-KR')}원(${detailed.trim()})`;
}
