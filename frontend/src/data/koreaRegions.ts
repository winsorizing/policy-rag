/** 시·도 → 시·군·구 (간략 목록, 규제 키워드 매칭용 문자열 생성) */

export const SIDO_LIST = [
  '전체',
  '서울특별시',
  '부산광역시',
  '대구광역시',
  '인천광역시',
  '광주광역시',
  '대전광역시',
  '울산광역시',
  '세종특별자치시',
  '경기도',
  '강원특별자치도',
  '충청북도',
  '충청남도',
  '전북특별자치도',
  '전라남도',
  '경상북도',
  '경상남도',
  '제주특별자치도',
  '기타',
] as const;

export type SidoId = (typeof SIDO_LIST)[number];

export const SIGUNGU_BY_SIDO: Record<string, readonly string[]> = {
  전체: ['전국'],
  서울특별시: [
    '전체',
    '강남구',
    '강동구',
    '강북구',
    '강서구',
    '관악구',
    '광진구',
    '구로구',
    '금천구',
    '노원구',
    '도봉구',
    '동대문구',
    '동작구',
    '마포구',
    '서대문구',
    '서초구',
    '성동구',
    '성북구',
    '송파구',
    '양천구',
    '영등포구',
    '용산구',
    '은평구',
    '종로구',
    '중구',
    '중랑구',
    '기타',
  ],
  부산광역시: ['전체', '해운대구', '기타'],
  대구광역시: ['전체', '기타'],
  인천광역시: ['전체', '기타'],
  광주광역시: ['전체', '기타'],
  대전광역시: ['전체', '기타'],
  울산광역시: ['전체', '기타'],
  세종특별자치시: ['전체', '기타'],
  경기도: ['전체', '성남시', '용인시', '수원시', '고양시', '기타'],
  강원특별자치도: ['전체', '기타'],
  충청북도: ['전체', '기타'],
  충청남도: ['전체', '기타'],
  전북특별자치도: ['전체', '기타'],
  전라남도: ['전체', '기타'],
  경상북도: ['전체', '기타'],
  경상남도: ['전체', '기타'],
  제주특별자치도: ['전체', '기타'],
  기타: ['기타 지역'],
};

/** API·계산기에 넘길 단일 region 문자열 */
export function formatRegionString(sido: string, sigungu: string): string {
  if (sido === '전체') return '기타 지역';
  if (sido === '기타') return '기타 지역';
  if (sigungu === '전국') return '기타 지역';
  if (sigungu === '전체') return sido;
  if (sigungu === '기타') return `${sido} 기타`;
  return `${sido} ${sigungu}`;
}

const LEGACY_REGION: Record<string, { sido: string; sigungu: string }> = {
  '서울 강남구': { sido: '서울특별시', sigungu: '강남구' },
  '서울 서초구': { sido: '서울특별시', sigungu: '서초구' },
  '서울 송파구': { sido: '서울특별시', sigungu: '송파구' },
  '서울 기타': { sido: '서울특별시', sigungu: '기타' },
  '경기 성남시': { sido: '경기도', sigungu: '성남시' },
  '경기 용인시': { sido: '경기도', sigungu: '용인시' },
  '경기 기타': { sido: '경기도', sigungu: '기타' },
  '기타 지역': { sido: '기타', sigungu: '기타 지역' },
};

export function splitRegionToParts(region: string): { sido: string; sigungu: string } {
  const legacy = LEGACY_REGION[region];
  if (legacy) return legacy;

  const sidosOrdered = [...SIDO_LIST].filter((s) => s !== '전체').sort((a, b) => b.length - a.length);
  for (const sido of sidosOrdered) {
    if (region === sido) return { sido, sigungu: '전체' };
    if (region.startsWith(`${sido} `)) {
      const tail = region.slice(sido.length + 1);
      return { sido, sigungu: tail || '전체' };
    }
  }

  return { sido: '서울특별시', sigungu: '강남구' };
}

export function getSigunguList(sido: string): readonly string[] {
  return SIGUNGU_BY_SIDO[sido] ?? ['전체', '기타'];
}
