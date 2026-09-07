"""
FastAPI ``get_rag`` / ``get_rag_openai`` 가 import 하는 RAG 엔트리.

- ``RealEstateRAG``: Ollama(ChatOllama) + Chroma(VectorStoreManager)
- ``RealEstateRAGOpenAI``: OpenAI 챗 + 동일 Chroma
- ``ask_loan_explanation`` 경로: 대출 계산 결과 dict + 검색 컨텍스트로 구조화된 설명 프롬프트 사용
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    from dotenv import load_dotenv

    _RAG_CHAIN_DIR = Path(__file__).resolve().parent
    load_dotenv(_RAG_CHAIN_DIR / ".env", override=False)
except ImportError:
    pass

from langchain_classic.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_classic.chains import RetrievalQA
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from utils.text_cleaner import TextCleaner
from vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


def _rag_source_content_max() -> int:
    raw = os.getenv("RAG_SOURCE_CONTENT_MAX", "4096")
    try:
        return max(500, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 4096


_RAG_SOURCE_CONTENT_MAX = _rag_source_content_max()

_RAG_PROMPT_TEMPLATE = """
당신은 부동산 정책 전문가입니다. 주어진 정책 문서를 바탕으로 정확하게 답변하세요.

규칙:
1. 제공된 문서에 있는 정보만 사용하세요
2. 확실하지 않으면 "제공된 정보로는 확인이 어렵습니다"라고 답하세요
3. 숫자와 날짜는 정확하게 인용하세요
4. 출처를 명시하세요
5. 한국어로 답변하세요

컨텍스트:
{context}

질문: {question}

답변:
"""

# 대출 정책 설명 전용 (loan_orchestrator → ask_loan_explanation)
# 컨텍스트는 검색 본문이므로 str.format 대신 치환용 플레이스홀더만 사용
_LOAN_EXPLAIN_TEMPLATE = """당신은 친절한 부동산 대출 상담사입니다.
사용자는 이미 계산 결과를 봤으니, 같은 금액·같은 퍼센트를 반복하지 말고 핵심만 간단히 설명해.

# 사용자 상황
- 지역: {region} ({regulation_type})
- 주택가격: {house_price}원
- 연소득: {annual_income}원
- 보유주택: {house_count}채
- 생애최초: {is_first_home}

# 계산 결과 (참고용, 숫자는 바꾸지 말 것)
- 최대 대출: {max_loan}원
- 걸림돌: {limiting_factor}
- LTV: 실제 {ltv_actual}% / 한도 {ltv_limit}%
- DTI: 실제 {dti_actual}% / 한도 {dti_limit}%
- DSR: 실제 {dsr_actual}% / 한도 {dsr_limit}%

# 관련 정책 (참고)
{context}

---

다음 형식으로만 답변해. 번호·제목 구조는 지키되, 말투는 친근한 반말로 통일해.

## 💡 왜 이 금액이야? (1-2문장)
{limiting_factor}가 걸림돌이 된 이유를 정책 근거와 함께 간단히

## 🎯 대출 한도 높이는 법 (3가지만)

### 1️⃣ [방법명] (난이도: 쉬움/보통/어려움)
- 변경: 무엇을 바꿀지
- 효과: 대략 얼마나 나아질 수 있는지 (구체 숫자는 문서·엔진 범위 안에서만)
- 한 줄 요약

### 2️⃣ [방법명] (난이도: 쉬움/보통/어려움)
- 변경: 무엇을 바꿀지
- 효과: …
- 한 줄 요약

### 3️⃣ [방법명] (난이도: 쉬움/보통/어려움)
- 변경: 무엇을 바꿀지
- 효과: …
- 한 줄 요약

## ⚠️ 주의 (1문장)
이 조건에서 특히 조심할 점

---

규칙:
1. 한국어 위주 (필요한 경우에만 LTV·DTI·DSR 같은 약어 사용 가능)
2. 위에 없는 숫자·한도는 새로 만들지 말 것
3. 정책 근거는 위 [관련 정책]에 있는 내용만 쓰고, 없으면 솔직히 한계를 밝혀
4. 답변은 카드에 넣기 좋게 과하지 않게
5. 괄호 안에 영어 설명을 넣지 말 것(한글만). 영어 병기 후 삭제되면 "(, )"처럼 깨져 보일 수 있음

답변:
"""


def _rag_debug_print_enabled() -> bool:
    """기본 ON. 끄려면 ``RAG_DEBUG_PRINT=0``."""
    v = os.getenv("RAG_DEBUG_PRINT", "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _print_llm_input(label: str, text: str) -> None:
    """LLM 직전 문자열 — 터미널 + uvicorn 로그(기본 WARNING)에 남김."""
    if not _rag_debug_print_enabled():
        return
    try:
        max_preview = max(500, int(os.getenv("RAG_DEBUG_PRINT_MAX", "20000")))
    except ValueError:
        max_preview = 20000
    n = len(text)
    preview = text if n <= max_preview else text[:max_preview] + f"\n... [이하 생략, 전체 {n}자]"
    block = f"\n{'=' * 16} [RAG DEBUG] {label} (총 {n}자) {'=' * 16}\n{preview}\n{'=' * 72}\n"
    print(block, file=sys.stderr, flush=True)
    print(block, flush=True)
    # uvicorn 기본 로그 레벨에서도 보이도록 WARNING 사용
    uv = logging.getLogger("uvicorn.error")
    uv.warning("[RAG DEBUG] %s (total %d chars, preview up to %d)", label, n, max_preview)
    for line in preview.splitlines()[:300]:
        uv.warning("[RAG DEBUG] | %s", line[:600])
    if preview.count("\n") > 300:
        uv.warning("[RAG DEBUG] | ... (%d more lines omitted)", preview.count("\n") - 300)


def _ollama_base_url() -> str | None:
    return os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or None


def _pct_label(n: float) -> str:
    x = float(n)
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    t = f"{x:.2f}".rstrip("0").rstrip(".")
    return t or "0"


def _won_label(n: int) -> str:
    return f"{max(0, int(n)):,}"


def _fill_placeholders(template: str, values: Mapping[str, str]) -> str:
    """문서 본문에 `{{` 등이 있어도 안전하게 고정 키만 치환."""
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def _retriever_docs(retriever: Any, query: str) -> list[Any]:
    try:
        out = retriever.invoke(query)
        if isinstance(out, list):
            return out
    except Exception:
        pass
    try:
        return list(retriever.get_relevant_documents(query))
    except Exception:
        return []


def _docs_to_context(docs: list[Any]) -> str:
    parts: list[str] = []
    for d in docs:
        pc = getattr(d, "page_content", None) or ""
        t = str(pc).strip()
        if t:
            parts.append(t)
    if not parts:
        return "제공된 정책 문서가 없거나 검색 결과가 비었습니다."
    return "\n\n---\n\n".join(parts)


def _sources_from_docs(docs: list[Any], content_max: int | None = None) -> list[dict[str, Any]]:
    cap = _RAG_SOURCE_CONTENT_MAX if content_max is None else content_max
    sources: list[dict[str, Any]] = []
    for doc in docs:
        meta = getattr(doc, "metadata", None)
        if not isinstance(meta, dict):
            meta = {}
        sources.append(
            {
                "content": str(getattr(doc, "page_content", "") or "")[:cap],
                "metadata": {str(k): v for k, v in meta.items()},
            }
        )
    return sources


def ask_loan_explanation_rag(
    llm: Any,
    vector_store: Any,
    calculation_result: Mapping[str, Any],
) -> dict[str, Any]:
    """
    계산 결과 dict + Chroma 검색으로 구조화 프롬프트를 만들어 LLM에 직접 질의.
    반환: ``answer``, ``sources``, ``action_items`` (``ask()`` 와 동일 키).
    """
    inp = calculation_result.get("input") or {}
    ltv = calculation_result.get("ltv") or {}
    dti = calculation_result.get("dti") or {}
    dsr = calculation_result.get("dsr") or {}

    region = str(inp.get("region") or "").strip() or "-"
    regulation_type = str(calculation_result.get("regulation_type") or "").strip() or "-"
    house_price = int(inp.get("house_price") or 0)
    annual_income = int(inp.get("annual_income") or 0)
    house_count = int(inp.get("house_count") or 0)
    is_first = bool(inp.get("is_first_home"))
    max_loan = int(calculation_result.get("max_loan_amount") or 0)
    limiting_factor = str(calculation_result.get("limiting_factor") or "").strip() or "-"

    retrieval_query = f"{regulation_type} {limiting_factor} 제한 이유와 해결 방법"
    _print_llm_input("ask_loan_explanation · Chroma 검색 쿼리", retrieval_query)
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    docs = _retriever_docs(retriever, retrieval_query)
    context = _docs_to_context(docs)

    values = {
        "region": region,
        "regulation_type": regulation_type,
        "house_price": _won_label(house_price),
        "annual_income": _won_label(annual_income),
        "house_count": str(house_count),
        "is_first_home": "예" if is_first else "아니오",
        "max_loan": _won_label(max_loan),
        "limiting_factor": limiting_factor,
        "ltv_actual": _pct_label(float(ltv.get("actual") or 0)),
        "ltv_limit": _pct_label(float(ltv.get("limit") or 0)),
        "dti_actual": _pct_label(float(dti.get("actual") or 0)),
        "dti_limit": _pct_label(float(dti.get("limit") or 0)),
        "dsr_actual": _pct_label(float(dsr.get("actual") or 0)),
        "dsr_limit": _pct_label(float(dsr.get("limit") or 0)),
        "context": context,
    }
    prompt = _fill_placeholders(_LOAN_EXPLAIN_TEMPLATE, values)
    _print_llm_input("ask_loan_explanation · LLM 최종 프롬프트 (HumanMessage)", prompt)

    try:
        msg = HumanMessage(content=prompt)
        out = llm.invoke([msg])
        explanation = str(getattr(out, "content", None) or out or "").strip()
    except Exception as e:
        return {
            "answer": (
                "RAG(대출 설명) 단계에서 오류가 발생했습니다.\n"
                f"({type(e).__name__}: {e})"
            ),
            "sources": _sources_from_docs(docs),
            "action_items": [],
        }

    # 구조화 프롬프트(여러 ##·### 블록)는 500자 제한이면 본문 대부분이 잘림
    cleaned = TextCleaner.clean_rag_response(explanation, max_len=12000)
    action_items = TextCleaner.extract_action_items(explanation)

    return {
        "answer": cleaned,
        "sources": _sources_from_docs(docs),
        "action_items": action_items,
    }


class RealEstateRAG:
    """로컬 Ollama 챗 + Chroma 검색."""

    def __init__(self) -> None:
        model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
        self.llm_model_label = model
        self.vs_manager = VectorStoreManager()
        self.vs_manager.load_vector_store()
        self.llm = ChatOllama(
            model=model,
            temperature=0,
            base_url=_ollama_base_url(),
            callbacks=[StreamingStdOutCallbackHandler()],
        )
        self.prompt = PromptTemplate(
            template=_RAG_PROMPT_TEMPLATE,
            input_variables=["context", "question"],
        )
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vs_manager.vector_store.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": self.prompt},
            return_source_documents=True,
        )

    def ask(self, question: str) -> dict[str, Any]:
        try:
            _print_llm_input(
                "RealEstateRAG.ask · RetrievalQA query → 템플릿 {question} 자리",
                question,
            )
            try:
                result = self.qa_chain.invoke({"query": question})
            except Exception:
                result = self.qa_chain({"query": question})
            docs = result.get("source_documents") or []
            sources = _sources_from_docs(docs)
            raw = str(result.get("result") or "")
            actions = TextCleaner.extract_action_items(raw)
            cleaned = TextCleaner.clean_rag_response(raw)
            return {
                "answer": cleaned,
                "sources": sources,
                "action_items": actions,
            }
        except Exception as e:
            return {
                "answer": (
                    "RAG(검색·생성) 단계에서 오류가 발생했습니다.\n"
                    f"({type(e).__name__}: {e})"
                ),
                "sources": [],
                "action_items": [],
            }

    def ask_loan_explanation(self, calculation_result: Mapping[str, Any]) -> dict[str, Any]:
        vs = self.vs_manager.vector_store
        if vs is None:
            return {
                "answer": "벡터 스토어가 로드되지 않아 대출 설명을 생성할 수 없습니다.",
                "sources": [],
                "action_items": [],
            }
        return ask_loan_explanation_rag(self.llm, vs, calculation_result)


class RealEstateRAGOpenAI:
    """OpenAI 챗 + 동일 Chroma — OPENAI_API_KEY 필요."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not str(api_key).strip():
            raise RuntimeError(
                "OpenAI 모드를 쓰려면 backend/.env 등에 OPENAI_API_KEY 를 설정하세요."
            )
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self.llm_model_label = model
        self.vs_manager = VectorStoreManager()
        self.vs_manager.load_vector_store()
        self.llm = ChatOpenAI(model=model, temperature=0, api_key=api_key)
        self.prompt = PromptTemplate(
            template=_RAG_PROMPT_TEMPLATE,
            input_variables=["context", "question"],
        )
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vs_manager.vector_store.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": self.prompt},
            return_source_documents=True,
        )

    def ask(self, question: str) -> dict[str, Any]:
        try:
            _print_llm_input(
                "RealEstateRAGOpenAI.ask · RetrievalQA query → 템플릿 {question} 자리",
                question,
            )
            try:
                result = self.qa_chain.invoke({"query": question})
            except Exception:
                result = self.qa_chain({"query": question})
            docs = result.get("source_documents") or []
            sources = _sources_from_docs(docs)
            raw = str(result.get("result") or "")
            actions = TextCleaner.extract_action_items(raw)
            cleaned = TextCleaner.clean_rag_response(raw)
            return {
                "answer": cleaned,
                "sources": sources,
                "action_items": actions,
            }
        except Exception as e:
            return {
                "answer": (
                    "RAG(검색·생성) 단계에서 오류가 발생했습니다.\n"
                    f"({type(e).__name__}: {e})"
                ),
                "sources": [],
                "action_items": [],
            }

    def ask_loan_explanation(self, calculation_result: Mapping[str, Any]) -> dict[str, Any]:
        vs = self.vs_manager.vector_store
        if vs is None:
            return {
                "answer": "벡터 스토어가 로드되지 않아 대출 설명을 생성할 수 없습니다.",
                "sources": [],
                "action_items": [],
            }
        return ask_loan_explanation_rag(self.llm, vs, calculation_result)
