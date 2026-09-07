# Policy RAG — AI 부동산 대출 컨설턴트

**규칙 JSON 기반 대출 한도 계산(Rule Engine)** 과 **정책 문서 검색·자연어 설명(RAG + LLM)** 을 분리해, 숫자는 결정론으로 맞추고 해설·근거는 검색 결과로 붙이는 웹 앱입니다.

---

## 핵심 설계

| 구분 | 역할 | 비고 |
|------|------|------|
| Rule Engine | LTV·DTI·DSR·규제 유형·정책대출 등 **한도 계산** | `backend/rule_engine/`, API `POST /api/calculate-loan` |
| RAG | 크롤·PDF·시드 등을 Chroma에 넣고 **정책 근거·설명·실행 팁** | `backend/rag_chain.py` 등, API `POST /api/explain-loan-policy`, `/api/profile-insight` |
| LLM | 설명 문구 생성(Ollama 또는 OpenAI) | 계산식 대신 검색 컨텍스트 기반 생성 |

프론트는 **Local / OpenAI / Compare** 모드로 요약 방식을 바꿀 수 있고, 상단에서 **규칙 크롤·merge·벡터 재빌드**를 트리거할 수 있습니다.

---

## 기술 스택

| 영역 | 사용 |
|------|------|
| Frontend | React 19, TypeScript, Vite 8, MUI, axios |
| 발표(Slidev) | Vue 3, Slidev (`slidev/`) |
| Backend | FastAPI, Uvicorn, Pydantic |
| RAG·임베딩 | LangChain 계열, ChromaDB, Ollama / OpenAI |
| 데이터 | 국토부·금융위 등 크롤 JSON → `data/rules/merge`, 벡터용 문서는 `build_vectordb` 등 |

---

## 레포 구조(요약)

```text
policy-rag/
├── frontend/          # Vite React SPA — 자세한 표는 frontend/README.md
├── slidev/            # Slidev 발표 — npm run dev (기본 http://localhost:3030)
├── backend/
│   ├── app/           # FastAPI main, 스키마, 대출 오케스트레이션
│   ├── rule_engine/   # LoanCalculator, 규칙 로더
│   ├── data/
│   │   ├── rules/     # manual / crawled / merge / history
│   │   └── crawler/   # 크롤·run_crawler
│   ├── rag_chain.py
│   ├── vector_store.py
│   ├── build_vectordb.py
│   └── chroma_db/     # 로컬 Chroma 저장(생성 후)
└── README.md          # 본 문서
```

상세 API·환경 변수·규칙 JSON 출처는 **`backend/README.md`**, UI·프록시·컴포넌트는 **`frontend/README.md`** 를 참고하세요.

---

## 빠른 시작

### 1) 백엔드

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # Ollama / OpenAI 등 필요 시 수정
# Ollama 사용 시: 채팅·임베딩 모델 pull (.env.example 주석 참고)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2) 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

개발 시 `frontend/vite.config.ts` 가 `/api` 를 `http://127.0.0.1:8000` 으로 프록시합니다. 빌드물을 정적 호스팅할 때는 `VITE_API_BASE_URL` 로 백엔드 URL을 지정합니다.

### 3) Slidev (발표 자료)

```bash
cd slidev
npm install
npm run dev
```

슬라이드 본문은 `slidev/slides.md` 에서 수정합니다. 정적 배포는 `npm run build` 후 `slidev/dist` 를 호스팅하면 됩니다. 상세는 `slidev/README.md` 를 참고하세요.

---

## API 한눈에 보기

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/health` | 헬스체크 |
| `GET` | `/api/rules-update-log` | 규칙 merge 이력 일자 |
| `POST` | `/api/query` | 자유 질문 RAG(프론트 UI 미연결 가능) |
| `POST` | `/api/profile-insight` | 프로필 기반 정책 요약(`insight_mode`) |
| `POST` | `/api/calculate-loan` | Rule 엔진만 대출 한도 |
| `POST` | `/api/explain-loan-policy` | 엔진 스냅샷 + 정책 RAG·`action_items` |
| `POST` | `/api/run-crawlers` | 크롤·merge(기본 당일 갱신 시 스킵 옵션) |
| `POST` | `/api/refresh-knowledge` | 크롤·merge·벡터 DB 전체 재빌드 |

전체 설명·제약은 **`backend/README.md`** 를 따릅니다.

---

## 데이터 파이프라인(요약)

1. **크롤** → `backend/data/rules/crawled/`  
2. **수동 보정** → `backend/data/rules/manual/`  
3. **병합** → `backend/data/rules/merge/` (**엔진은 merge 우선 로드**)  
4. **벡터 인덱스** → `build_vectordb.py` 등으로 `chroma_db/` 생성·갱신  

정책 **설명(RAG)** 은 위 JSON과 별도로, 인덱싱된 문서 청크를 검색합니다.

---

## 참고 링크

- 국토교통부 정책 포털: [policy.main.jsp](https://www.molit.go.kr/policy/main.jsp)
- 영감·비교용 대출 관련 사이트: [xn--989a00af8jnslv3dba.com/loan](https://xn--989a00af8jnslv3dba.com/loan)
- LTV·DTI·DSR·스트레스 금리 등 비교용 계산기: [calc.boonyangnote.com](https://calc.boonyangnote.com/)

---

## 면책

본 프로젝트는 포트폴리오·학습용으로, 실제 금융·법률 자문을 대체하지 않습니다. 규정·세부 조건은 금융기관·최신 고시를 확인하세요.
