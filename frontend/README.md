# Frontend 정리

## 구성

| 파일 | 설명 |
|------|------|
| `ActionItems.tsx` | RAG `action_items` 카드. 난이도 칩·효과·본문 펼침, 빈 목록이면 렌더 생략 |
| `FriendlyAiAnalysis.tsx` | RAG 설명 문자열에서 `##`·`###`·`---` 파싱 후 제목·본문으로 표시 |
| `InsightPanel.tsx` | 로딩 단계·단일/비교 모드 답변·`LoanResult`·출처 리스트 |
| `LoanResult.tsx` | 엔진 한도·규제·제한 요인·LTV·DTI·DSR 상세·출처·데이터 출처 안내 |
| `RegionPicker.tsx` | 시·도·시·군·구 선택, 키 있을 때 실거래가 API |
| `UserProfile.tsx` | 프로필 입력·인사이트 모드·저장·`알아보기`에서 API 순차 호출 |
| `App.tsx` | 레이아웃·헬스 폴링·규칙 merge 일자·지식 새로고침·상태 연결 |
| `services/api.ts` | Axios·백엔드 `/api/*` 래퍼·타임아웃·에러 메시지 |

---

## 디렉터리·기타 파일

| 경로(상대: `frontend/`) | 역할 |
|-------------------------|------|
| `src/main.tsx` | 엔트리 |
| `src/index.css`, `src/App.css` | 글로벌·앱 스타일 |
| `src/constants/loanUi.ts` | 대출 UI 상수 |
| `src/utils/formatWon.ts` | 원 단위 표기 |
| `src/utils/formatRagSourceText.ts` | 출처 문자열 정리 |
| `src/data/koreaRegions.ts`, `src/data/regionSeed.json` | 행정구역 데이터 |
| `vite.config.ts` | React 플러그인·프록시 |
| `public/icons.svg` | 정적 아이콘 |

---
