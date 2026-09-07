from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    LoanCalculationResult,
    PolicyExplainResponse,
    PolicyResponse,
    ProfileInsightRequest,
    QueryRequest,
    Source,
    SourceMetadata,
    UserProfile,
)
from app.loan_orchestrator import LoanOrchestrator

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_RULES_UPDATE_LOG_PATH = _BACKEND_ROOT / "data" / "rules" / "history" / "update_log.json"
load_dotenv(_BACKEND_ROOT / ".env")

logger = logging.getLogger(__name__)

_rag_singleton: Any | None = None
_rag_openai_singleton: Any | None = None


def _rag_debug_stub_print(label: str, text: str) -> None:
    """RAG 스텁일 때도 질문·payload 확인용 (``rag_chain`` 과 동일 ``RAG_DEBUG_PRINT``)."""
    import sys

    v = os.getenv("RAG_DEBUG_PRINT", "0").strip().lower()
    if v in ("0", "false", "off", "no"):
        return
    n = len(text)
    preview = text if n <= 8000 else text[:8000] + f"\n... [생략, 전체 {n}자]"
    block = f"\n{'=' * 16} [RAG DEBUG] {label} (총 {n}자) {'=' * 16}\n{preview}\n{'=' * 72}\n"
    print(block, file=sys.stderr, flush=True)
    print(block, flush=True)
    uv = logging.getLogger("uvicorn.error")
    uv.warning("[RAG DEBUG stub] %s (total %d chars)", label, n)
    for line in preview.splitlines()[:120]:
        uv.warning("[RAG DEBUG stub] | %s", line[:600])


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, Any]:
    """브라우저에서 ``http://127.0.0.1:8000/`` 만 열었을 때 안내(기본은 404였음)."""
    return {
        "service": "policy-rag backend",
        "health": "/api/health",
        "rag_debug": "/api/rag-debug",
        "rag_debug_poke": "POST /api/rag-debug-poke",
        "openapi": "/docs",
        "ui": "프론트 실행 후 http://localhost:5173 (Vite가 /api 를 이 서버로 프록시)",
    }


def _loan_orchestrator() -> LoanOrchestrator:
    return LoanOrchestrator(
        rag_ask=_rag_ask_for_orchestrator,
        normalize_sources=_normalize_sources,
    )


def _rag_ask_for_orchestrator(q: str | dict[str, Any]) -> dict[str, Any]:
    """자유 질의(str)와 대출 설명(dict)을 ``RealEstateRAG`` 에 위임."""
    rag = get_rag()
    if isinstance(q, dict):
        return rag.ask_loan_explanation(q)
    return rag.ask(q)


def get_rag() -> Any:
    """RAG 초기화 실패 시 스텁으로 동작해 서버 기동은 유지."""
    global _rag_singleton
    if _rag_singleton is not None:
        return _rag_singleton
    try:
        from rag_chain import RealEstateRAG

        _rag_singleton = RealEstateRAG()
    except Exception as e:
        # 임베딩 404·Chroma 오류·Ollama 미기동 등 — API(알아보기)는 500 없이 스텁으로 응답
        logger.warning("RealEstateRAG 초기화 실패 (스텁 사용): %s", e, exc_info=True)
        reason = str(e).strip() or type(e).__name__

        class _StubRAG:
            llm_model_label = os.getenv("OLLAMA_MODEL", "gemma4:latest")

            def ask(self, question: str) -> dict[str, Any]:
                _rag_debug_stub_print("StubRAG.ask (RealEstateRAG 미기동) · 전달된 질문 문자열", question)
                return {
                    "answer": (
                        "RAG 엔진을 불러오지 못했습니다.\n\n"
                        f"(원인 요약: {reason})\n\n"
                        "로컬 Ollama 사용 시 확인 순서:\n"
                        "1) Ollama 실행 (`ollama serve`) 및 채팅 모델 설치: `ollama pull "
                        f"{os.getenv('OLLAMA_MODEL', 'gemma4:latest')}`\n"
                        "2) 임베딩 모델 설치: `ollama pull "
                        f"{os.getenv('OLLAMA_EMBED_MODEL', 'joonoh/HyperCLOVAX-SEED-Text-Instruct-1.5B:latest')}`\n"
                        "3) backend에서 `python build_vectordb.py` 로 chroma_db 생성 "
                        "(이전에 다른 설정으로 만든 chroma_db가 있으면 폴더 삭제 후 다시 빌드)\n"
                        "4) 필요 시 `.env`에 OLLAMA_BASE_URL(기본 http://127.0.0.1:11434)\n\n"
                        f"(요약 질문 길이: {len(question)}자)"
                    ),
                    "sources": [],
                    "action_items": [],
                }

            def ask_loan_explanation(self, calculation_result: dict[str, Any]) -> dict[str, Any]:
                import json

                try:
                    payload_preview = json.dumps(
                        calculation_result, ensure_ascii=False, indent=2
                    )
                except TypeError:
                    payload_preview = str(calculation_result)
                _rag_debug_stub_print(
                    "StubRAG.ask_loan_explanation · 계산 payload (LLM 미호출)",
                    payload_preview,
                )
                return self.ask("대출 정책 설명")

        _rag_singleton = _StubRAG()
    return _rag_singleton


def get_rag_openai() -> Any:
    """OpenAI 챗 + 동일 Chroma — OPENAI_API_KEY 필요."""
    global _rag_openai_singleton
    if _rag_openai_singleton is not None:
        return _rag_openai_singleton
    from rag_chain import RealEstateRAGOpenAI

    _rag_openai_singleton = RealEstateRAGOpenAI()
    return _rag_openai_singleton


def _rag_llm_label(rag: Any) -> str | None:
    return getattr(rag, "llm_model_label", None)


def _map_openai_failure(exc: Exception) -> HTTPException:
    msg = str(exc).lower()
    if (
        "401" in msg
        or "incorrect api key" in msg
        or "invalid_api_key" in msg
        or "authentication" in msg
    ):
        return HTTPException(
            status_code=401,
            detail="OpenAI API 키를 확인하세요. backend/.env 의 OPENAI_API_KEY 를 설정합니다.",
        )
    if "429" in msg or "rate" in msg:
        return HTTPException(
            status_code=503,
            detail="OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.",
        )
    return HTTPException(status_code=500, detail=str(exc))


def _coerce_chunk_index(value: Any) -> int:
    """Chroma/LangChain 메타에 리스트·문자 등이 섞여도 응답 검증 오류(500)를 피한다."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _normalize_sources(raw: list[dict[str, Any]]) -> list[Source]:
    out: list[Source] = []
    for item in raw:
        meta_raw = item.get("metadata") or {}
        if not isinstance(meta_raw, dict):
            meta_raw = {}
        out.append(
            Source(
                content=str(item.get("content", "")),
                metadata=SourceMetadata(
                    title=str(meta_raw.get("title", "문서")),
                    source=str(meta_raw.get("source", "unknown")),
                    date=str(meta_raw.get("date", "-")),
                    category=str(meta_raw.get("category", "정책")),
                    chunk_index=_coerce_chunk_index(meta_raw.get("chunk_index", 0)),
                ),
            )
        )
    return out


def _rule_crawl_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """응답용 짧은 요약(단계별 traceback 등은 제외)."""
    merge = payload.get("merge")
    merge_ok: bool | None = None
    if isinstance(merge, dict):
        merge_ok = merge.get("all_ok")  # type: ignore[assignment]
    steps_in = payload.get("steps") or []
    step_names_ok: list[dict[str, Any]] = []
    if isinstance(steps_in, list):
        for s in steps_in:
            if not isinstance(s, dict):
                continue
            step_names_ok.append(
                {
                    "name": s.get("name"),
                    "ok": s.get("ok"),
                    "skipped": s.get("skipped"),
                }
            )
    return {
        "all_ok": payload.get("all_ok"),
        "crawl_all_ok": payload.get("crawl_all_ok"),
        "merge_all_ok": merge_ok,
        "steps": step_names_ok,
    }


def _rebuild_vector_db_with_latest_crawled(*, force: bool = False) -> dict[str, Any]:
    """
    1) 규제지역·DTI/DSR 크롤 + ``rules/merge`` 병합(``history/update_log.json`` 갱신)
    2) ``build_vectordb``: AIHub 전처리 + ``rules/crawled``·``rules/merge`` 규칙 텍스트화,
       청킹 후 Chroma 전체 재빌드

    ``force``가 False이고 ``update_log``/merge 날짜가 한국 기준 오늘이면
    크롤·벡터 재빌드를 생략하고(시간 절약), ``rules/merge`` JSON을 다시 읽도록
    대출 계산기 캐시만 무효화한다.
    """
    from build_vectordb import build_vectordb

    from app.rule_engine_loan import reset_loan_calculator
    from app.rules_merge_freshness import should_skip_heavy_refresh

    if not force:
        skip, detail = should_skip_heavy_refresh()
        if skip:
            reset_loan_calculator()
            logger.info("refresh: 크롤·Chroma 생략 (%s)", detail)
            return {
                "skipped": True,
                "skip_reason": detail,
                "doc_count": 0,
                "chunk_count": 0,
                "persist_directory": None,
                "corpus_json": None,
                "rule_crawl": {"skipped": True, "note": "merge 규칙이 오늘(KST) 이미 반영됨"},
            }

    try:
        from data.crawler.run_crawler import run_all_crawlers

        rule_payload = run_all_crawlers()
    except Exception as e:
        logger.exception("refresh: run_all_crawlers 예외 — 벡터 단계는 계속")
        rule_payload = {
            "steps": [{"name": "_runner", "ok": False, "error": str(e)}],
            "all_ok": False,
            "crawl_all_ok": False,
        }

    vec_stats = build_vectordb(
        aihub_dir=_BACKEND_ROOT / "data" / "aihub",
        processed_out=_BACKEND_ROOT / "data" / "processed" / "aihub_rag_documents.json",
        persist_dir=_BACKEND_ROOT / "chroma_db",
        prepare_only=False,
        quiet=True,
    )

    reset_loan_calculator()

    return {
        "doc_count": vec_stats["doc_count"],
        "chunk_count": vec_stats["chunk_count"],
        "persist_directory": vec_stats["persist_directory"],
        "corpus_json": vec_stats.get("corpus_json"),
        "rule_crawl": _rule_crawl_summary(rule_payload),
    }


@app.post("/api/query", response_model=PolicyResponse)
def query_policy(request: QueryRequest) -> PolicyResponse:
    if request.user_profile:
        p = request.user_profile
        enhanced = (
            "사용자 상황:\n"
            f"- 생애최초 주택구입: {'예' if p.first_time_buyer else '아니오'}\n"
            f"- 혼인 여부: {'기혼' if p.married else '미혼'}\n"
            f"- 보유주택 수: {int(p.house_count)}채\n"
            f"- 연소득: {p.annual_income:,.0f}원\n"
            f"- 대상 주택 지역: {p.region}\n"
            f"- 주택 가격: {p.house_price:,.0f}원\n\n"
            f"질문: {request.question}"
        )
    else:
        enhanced = request.question

    try:
        if request.llm_mode == "openai":
            try:
                rag_o = get_rag_openai()
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            try:
                raw = rag_o.ask(enhanced)
            except Exception as e:
                raise _map_openai_failure(e) from e
            return PolicyResponse(
                answer=str(raw.get("answer", "")),
                sources=_normalize_sources(raw.get("sources") or []),
                mode="openai",
                llm_model=_rag_llm_label(rag_o),
            )

        rag = get_rag()
        raw = rag.ask(enhanced)
        return PolicyResponse(
            answer=str(raw.get("answer", "")),
            sources=_normalize_sources(raw.get("sources") or []),
            mode="local",
            llm_model=_rag_llm_label(rag),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _build_profile_insight_prompt(profile: UserProfile) -> str:
    return (
        "당신은 부동산 규제·주택 관련 정책 안내를 돕는 도우미입니다. "
        "제공된 정책 문서(컨텍스트)만 근거로 답하고, 없으면 분명히 한계를 밝히세요.\n\n"
        "사용자 조건:\n"
        f"- 생애최초 주택구입: {'예' if profile.first_time_buyer else '아니오'}\n"
        f"- 혼인 여부: {'기혼' if profile.married else '미혼'}\n"
        f"- 보유주택 수: {int(profile.house_count)}채\n"
        f"- 연소득: {profile.annual_income:,.0f}원\n"
        f"- 대상 주택 지역: {profile.region}\n"
        f"- 주택 가격: {profile.house_price:,.0f}원\n\n"
        "위 조건에 대해 규제지역(투기과열·조정대상 등) 관련 유의사항, "
        "LTV·DTI 등 문서에 나온 내용을 가능한 범위에서 요약해 주세요."
    )


@app.post("/api/profile-insight", response_model=PolicyResponse)
def profile_insight(body: ProfileInsightRequest) -> PolicyResponse:
    """
    Chroma에 인덱싱된 정책 문서 + LLM:
    - local: Ollama(rag_chain 기본)
    - openai: OpenAI 챗(OPENAI_API_KEY, OPENAI_CHAT_MODEL)
    - compare: 위 둘 답변을 나란히 반환
    """
    profile = UserProfile(
        first_time_buyer=body.first_time_buyer,
        married=body.married,
        house_count=body.house_count,
        annual_income=body.annual_income,
        region=body.region,
        house_price=body.house_price,
        product_cap_amount=body.product_cap_amount,
    )
    prompt = _build_profile_insight_prompt(profile)
    mode = body.insight_mode

    try:
        if mode == "local":
            rag = get_rag()
            raw = rag.ask(prompt)
            return PolicyResponse(
                answer=str(raw.get("answer", "")),
                sources=_normalize_sources(raw.get("sources") or []),
                mode="local",
                llm_model=_rag_llm_label(rag),
            )
        if mode == "openai":
            try:
                rag_o = get_rag_openai()
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            try:
                raw = rag_o.ask(prompt)
            except Exception as e:
                raise _map_openai_failure(e) from e
            return PolicyResponse(
                answer=str(raw.get("answer", "")),
                sources=_normalize_sources(raw.get("sources") or []),
                mode="openai",
                llm_model=_rag_llm_label(rag_o),
            )
        # compare
        rag_l = get_rag()
        local_raw = rag_l.ask(prompt)
        local_answer = str(local_raw.get("answer", ""))
        local_sources = _normalize_sources(local_raw.get("sources") or [])
        try:
            rag_o = get_rag_openai()
            openai_raw = rag_o.ask(prompt)
            openai_answer = str(openai_raw.get("answer", ""))
            openai_label = _rag_llm_label(rag_o)
        except Exception as e:
            openai_answer = f"(OpenAI 호출 실패: {e})"
            openai_label = None
        return PolicyResponse(
            answer="",
            sources=local_sources,
            mode="compare",
            local_answer=local_answer,
            openai_answer=openai_answer,
            local_llm_model=_rag_llm_label(rag_l),
            openai_llm_model=openai_label,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/rag-debug")
def rag_debug_status() -> dict[str, Any]:
    """``RAG_DEBUG_PRINT`` 해석 여부 확인 (터미널 없이 브라우저/HTTP로 점검)."""
    from rag_chain import _rag_debug_print_enabled

    return {
        "RAG_DEBUG_PRINT_env": os.getenv("RAG_DEBUG_PRINT", "(unset → 코드 기본 1=ON)"),
        "rag_debug_effective_on": _rag_debug_print_enabled(),
        "next": "POST /api/rag-debug-poke 로 콘솔·uvicorn WARNING 로그에 테스트 블록 출력",
    }


@app.post("/api/rag-debug-poke")
def rag_debug_poke() -> dict[str, Any]:
    """print/uvicorn 로그 경로 스모크 테스트 (RAG 미호출)."""
    from rag_chain import _print_llm_input

    _print_llm_input(
        "POST /api/rag-debug-poke",
        "이 메시지가 uvicorn 터미널 또는 로그에 [RAG DEBUG]로 보이면 출력은 정상입니다.",
    )
    return {"ok": True, "message": "백엔드 실행 터미널에서 WARNING [RAG DEBUG] 줄을 확인하세요."}


@app.get("/api/rules-update-log")
def rules_update_log() -> dict[str, Any]:
    """``data/rules/history/update_log.json`` 의 ``updateDate`` (없거나 오류 시 null)."""
    import json

    path = _RULES_UPDATE_LOG_PATH
    if not path.is_file():
        return {"updateDate": None}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"updateDate": None}
        ud = data.get("updateDate")
        if isinstance(ud, str) and ud.strip():
            return {"updateDate": ud.strip()}
        return {"updateDate": None}
    except Exception as e:
        logger.warning("rules update_log 읽기 실패: %s", e)
        return {"updateDate": None}


@app.post("/api/run-crawlers")
def run_crawlers_endpoint(
    skip_if_fresh: bool = Query(
        True,
        description="False면 항상 전체 크롤. True(기본)이면 merge/update_log가 오늘(KST)이면 크롤 생략",
    ),
) -> dict[str, Any]:
    """
    `data/crawler/run_crawler.py` 의 `run_all_crawlers` 실행.
    규제지역·DTI/DSR JSON 갱신 등(네트워크·대상 사이트 응답에 따라 수십 초~수분 소요 가능).

    ``skip_if_fresh`` 가 True이고 ``rules/merge`` 가 오늘 이미 반영된 상태면
    네트워크 크롤을 하지 않고 즉시 성공 응답을 반환한다(알아보기 UX).

    크롤러 import·실행 중 예상 밖 예외는 HTTP 500 대신 본문에 ``steps`` 로 내려
    프론트가 메시지를 표시한 뒤 요약 요청을 이어갈 수 있게 한다.
    """
    import json

    if skip_if_fresh:
        from app.rule_engine_loan import reset_loan_calculator
        from app.rules_merge_freshness import should_skip_heavy_refresh

        skip, detail = should_skip_heavy_refresh()
        if skip:
            reset_loan_calculator()
            logger.info("run_crawlers: 크롤 생략 (%s)", detail)
            payload: dict[str, Any] = {
                "steps": [
                    {
                        "name": "run_all_crawlers",
                        "ok": True,
                        "skipped": True,
                        "reason": detail,
                    }
                ],
                "all_ok": True,
                "crawl_all_ok": True,
                "merge": {
                    "all_ok": True,
                    "skipped": True,
                    "note": "merge 규칙 오늘(KST) 기준 — 크롤·병합 단계 생략",
                },
            }
            return payload

    try:
        from data.crawler.run_crawler import run_all_crawlers

        payload = run_all_crawlers()
        # Path·set 등 비JSON 타입이 섞이면 응답 직렬화 단계에서 500이 날 수 있음
        try:
            json.dumps(payload)
        except TypeError:
            payload = json.loads(json.dumps(payload, default=str))
        return payload
    except Exception as e:
        logger.exception("run_crawlers 실패")
        return {
            "steps": [
                {
                    "name": "_runner",
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                }
            ],
            "all_ok": False,
        }


@app.post("/api/refresh-knowledge")
def refresh_knowledge() -> dict[str, Any]:
    """
    상단 새로고침 버튼용 — **항상** 전체 실행:
    규제·DTI/DSR 크롤 및 merge(``update_log.json``) → AIHub·규칙 기반 Vector DB 재빌드.

    (오늘 이미 merge 반영 여부와 무관하게 크롤·벡터 단계를 생략하지 않음.)
    """
    global _rag_singleton, _rag_openai_singleton
    try:
        stats = _rebuild_vector_db_with_latest_crawled(force=True)
        # 전체 재빌드이므로 RAG 싱글톤은 항상 무효화
        _rag_singleton = None
        _rag_openai_singleton = None
        return {
            "ok": True,
            "message": "크롤링 및 벡터DB 업데이트 완료",
            "stats": stats,
        }
    except Exception as e:
        logger.exception("refresh_knowledge 실패")
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/calculate-loan", response_model=LoanCalculationResult)
def calculate_loan(profile: UserProfile) -> LoanCalculationResult:
    """엔진 기반 대출 한도 계산(결정론, RAG 비의존)."""
    try:
        return _loan_orchestrator().calculate_engine_only(profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/explain-loan-policy", response_model=PolicyExplainResponse)
def explain_loan_policy(profile: UserProfile) -> PolicyExplainResponse:
    """Rule 엔진과 분리: 동일 프로필로 엔진 재계산 후 정책 문서 RAG 설명·출처만 반환."""
    try:
        expl, sources, action_items = _loan_orchestrator().explain_policy_with_rag_only(profile)
        rag = get_rag()
        return PolicyExplainResponse(
            explanation=expl,
            sources=sources,
            action_items=action_items,
            llm_model=_rag_llm_label(rag),
        )
    except Exception as e:
        logger.exception("explain_loan_policy 실패")
        raise HTTPException(
            status_code=503,
            detail=f"정책 설명을 생성할 수 없습니다: {e}",
        ) from e
