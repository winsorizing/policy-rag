# Backend 정리

## 구성

| 사용 | 설명 |
|------|----------------|
| `OLLAMA_MODEL` | `gemma4:latest` |
| `OLLAMA_EMBED_MODEL` | `joonoh/HyperCLOVAX-SEED-Text-Instruct-1.5B:latest` |
| `OPENAI_API_KEY` |  |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` |

---

## 1) API 개요

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/` | 로컬에서 루트 URL만 열었을 때 짧은 안내 JSON |
| `GET` | `/api/health` | `{"ok": true}` 헬스체크 |
| `GET` | `/api/rules-update-log` | `data/rules/history/update_log.json`의 `updateDate`(없으면 `null`) |
| `POST` | `/api/query` | 자유 질문 RAG. `llm_mode`: `local` \| `openai`, `user_profile` 선택 |
| `POST` | `/api/profile-insight` | 프로필 기반 정책 요약. `insight_mode`: `local` \| `openai` \| `compare` |
| `POST` | `/api/run-crawlers` | `data/crawler/run_crawler.run_all_crawlers` 실행. 쿼리 `skip_if_fresh`(기본 `true`) — 오늘(KST) 기준 merge가 이미 반영됐으면 크롤 생략·엔진 캐시만 리셋 |
| `POST` | `/api/refresh-knowledge` | **항상** 크롤·merge·벡터DB 전체 재빌드(당일 중복 여부 무관). RAG 싱글톤 무효화 |
| `POST` | `/api/calculate-loan` | Rule 엔진만으로 대출 한도 계산(결정론). RAG 미사용 |
| `POST` | `/api/explain-loan-policy` | 동일 프로필로 엔진 재계산 후 정책 RAG 설명·출처·`action_items`. 실패 시 HTTP 503 가능 |

---

## 2) 대출 계산(Rule Engine)

| 파일(상대: `backend/`) | 역할 |
|-------------------------|------|
| `rule_engine/loan_calculator.py` | JSON 규칙 기반 LTV·DTI·DSR·정책대출 판정·`calculate()` |
| `rule_engine/data_loader.py` | `data/rules/...` JSON 로드·캐시 |
| `app/rule_engine_loan.py` | 프로필 → `LoanCalculator` 인자, **`merge/` 우선·없으면 `manual/`**, 싱글톤·`reset_loan_calculator()` |
| `app/loan_orchestrator.py` | API/`LoanCalculationResult`, RAG용 계산 스냅샷·페이로드 |
| `app/schemas.py` | `UserProfile`, `LoanCalculationResult` 등 |

계산 요약:

- 규제 유형(지역) → LTV·DTI·DSR 규정 한도
- DTI·DSR 역산: 만기 기준 **원금 균등 분할** 가정, 금리 미사용
- 기존 부채 월 상환액은 엔진에서 반영 가능하나, 현재 API 매핑은 `existing_debt_monthly_payment = 0` 고정
- 최종 한도 = `min(LTV상한, DTI상한, DSR상한)` 후 **`product_cap_amount`가 0보다 크면 그만큼 추가 캡**

`/api/calculate-loan` 응답의 `explanation` 은 사용자용 한 줄 안내(`loan_orchestrator.calculate_engine_only`).

---

## 3) RAG

| 파일(상대: `backend/`) | 역할 |
|-------------------------|------|
| `rag_chain.py` | Ollama / OpenAI + Chroma, `ask_loan_explanation` 구조화 프롬프트 |
| `vector_store.py` | Chroma 로드·검색 |
| `utils/text_cleaner.py` | 답변 정제·액션 블록 추출(대출 설명은 길이 한도 별도) |

흐름: 청크 인덱싱 → 검색(k=3) → LLM 생성 → 출처·선택적 `action_items`.

---

## 4) 규제 JSON·크롤

### 크롤·스크립트

| 파일(상대: `backend/`) | 역할 |
|-------------------------|------|
| `data/crawler/run_crawler.py` | `run_all_crawlers` — API `POST /api/run-crawlers` 진입 |
| `data/crawler/molit_policy_crawler.py` | 국토부 경로 등(규제·LTV·정책대출 JSON) |
| `data/crawler/dti_dsr_rules_crawler.py` | DTI/DSR 규칙 JSON |
| `app/rules_merge_freshness.py` | 오늘(KST) merge 반영 여부 → 크롤 스킵 판단 |

### 디렉터리·이력

| 경로(상대: `backend/`) | 내용 |
|------------------------|------|
| `data/rules/crawled/` | 크롤 원본 JSON |
| `data/rules/manual/` | 수동 보정 규칙 |
| `data/rules/merge/` | 크롤·수동 병합본 — **엔진은 여기 우선 로드** |
| `data/rules/history/update_log.json` | 병합·갱신 이력(`updateDate` 등) |
| `data/raw/test_*.json` | 있으면 벡터 갱신 시 함께 로드(선택) |
| `data/raw/unified_corpus.json` | 일부 파이프라인에서 생성·참조 |

### 규칙 JSON 출처(요약)

| JSON 키(병합 파일명) | 출처·병합 |
|---------------------|-----------|
| `regulation_areas`, `ltv_rules`, `policy_loans` | 국토부 공개 페이지 크롤 + `manual/` 병합 → `merge/` |
| `dti_dsr_rules` | 금융위 보도자료(PDF) 등 + baseline, 해설 참고 KB Think 가이드 |

**정책 설명(RAG)** 은 위 규칙 JSON과 별도로, 벡터 DB에 올린 문서(크롤·PDF·시드 등)를 검색한다.

---

## 5) 벡터 DB

| 파일·경로(상대: `backend/`) | 역할 |
|------------------------------|------|
| `build_vectordb.py` | 시드·룰 문서 등 청크 후 Chroma 생성 |
| `chroma_db/` (예) | Chroma 저장 디렉터리 |

`/api/refresh-knowledge` 가 내부에서 벡터 재빌드를 호출한다.

---

