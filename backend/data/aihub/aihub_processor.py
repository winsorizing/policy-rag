from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


FINANCE_KEYWORDS: tuple[str, ...] = (
    "LTV",
    "DTI",
    "DSR",
    "주택담보대출",
    "담보대출",
    "투기과열지구",
    "조정대상지역",
    "생애최초",
    "신혼부부",
    "디딤돌",
    "보금자리론",
)

LAW_KEYWORDS: tuple[str, ...] = ("주택법", "부동산", "담보대출", "금융")


class AIHubProcessor:
    """AI Hub 금융·법률 데이터 전처리 (RAG 문서 생성)."""

    def __init__(self, aihub_dir: str = "data/aihub") -> None:
        self.aihub_dir = Path(aihub_dir)
        self.filtered_file = self.aihub_dir / "filtered_policy_keywords.json"
        # 프로젝트 내 폴더 표기가 혼재될 수 있어 대소문자/구조 후보를 모두 지원
        self.finance_dirs: tuple[Path, ...] = (
            self.aihub_dir / "Training" / "금융",
            self.aihub_dir / "training" / "금융",
            self.aihub_dir / "training",
        )
        self.law_dirs: tuple[Path, ...] = (
            self.aihub_dir / "Training" / "법률",
            self.aihub_dir / "training" / "법률",
            self.aihub_dir / "validation",
        )

    @staticmethod
    def _load_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _to_items(data: Any) -> list[dict[str, Any]]:
        """
        AI Hub 원본/필터 결과 둘 다 대응:
        - {"data": [...]}
        - [{...}, {...}]
        - {"training": [{"data":[...]}, ...], "validation": ...}
        """
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                return [x for x in data["data"] if isinstance(x, dict)]

            out: list[dict[str, Any]] = []
            for split_key in ("training", "validation"):
                blocks = data.get(split_key)
                if not isinstance(blocks, list):
                    continue
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    rows = block.get("data")
                    if isinstance(rows, list):
                        out.extend(x for x in rows if isinstance(x, dict))
            if out:
                return out

            return [data]

        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        return []

    @staticmethod
    def _iter_json_files(dirs: Iterable[Path]) -> list[Path]:
        files: list[Path] = []
        for d in dirs:
            if d.is_dir():
                files.extend(sorted(d.glob("*.json")))
        # 중복 제거
        uniq = {p.resolve(): p for p in files}
        return list(uniq.values())

    @staticmethod
    def _iter_item_units(item: dict[str, Any]) -> Iterable[dict[str, str]]:
        """
        item에서 RAG 후보 단위를 평탄화:
        - top-level context/question/answer(s)
        - paragraphs[].context + paragraphs[].qas[].question/answer
        """
        doc_title = str(item.get("doc_title") or item.get("title") or "").strip()
        law_name = str(item.get("law_name") or "").strip()

        top_context = str(item.get("context", "") or "").strip()
        top_question = str(item.get("question", "") or "").strip()
        top_answer = AIHubProcessor._answer_text(item.get("answer") or item.get("answers"))
        if top_context or top_question or top_answer:
            yield {
                "context": top_context,
                "question": top_question,
                "answer": top_answer,
                "title": doc_title,
                "law_name": law_name,
            }

        paragraphs = item.get("paragraphs")
        if not isinstance(paragraphs, list):
            return
        for para in paragraphs:
            if not isinstance(para, dict):
                continue
            context = str(para.get("context", "") or "").strip()
            qas = para.get("qas")
            if isinstance(qas, list) and qas:
                for qa in qas:
                    if not isinstance(qa, dict):
                        continue
                    question = str(qa.get("question", "") or "").strip()
                    answer = AIHubProcessor._answer_text(qa.get("answer") or qa.get("answers"))
                    yield {
                        "context": context,
                        "question": question,
                        "answer": answer,
                        "title": doc_title,
                        "law_name": law_name,
                    }
            else:
                # 문단만 있는 경우도 근거 문서로 보존
                if context:
                    yield {
                        "context": context,
                        "question": "",
                        "answer": "",
                        "title": doc_title,
                        "law_name": law_name,
                    }

    @staticmethod
    def _answer_text(answer: Any) -> str:
        if isinstance(answer, dict):
            txt = answer.get("text")
            if isinstance(txt, list) and txt:
                return str(txt[0]).strip()
            if isinstance(txt, str):
                return txt.strip()
        if isinstance(answer, str):
            return answer.strip()
        return ""

    @staticmethod
    def _to_vector_doc(page_content: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        프로젝트 vector_store 포맷(text/metadata) + 호환용(page_content) 동시 저장.
        """
        clean_md = {k: str(v) for k, v in metadata.items() if v is not None}
        return {
            "text": page_content,
            "page_content": page_content,
            "metadata": clean_md,
        }

    def process_for_rag(self) -> List[Dict[str, Any]]:
        """RAG용 문서 생성."""
        documents: list[dict[str, Any]] = []

        print("🏦 금융 데이터 처리 중...")
        finance_docs = self._process_finance_data()
        documents.extend(finance_docs)

        print("⚖️ 법률 데이터 처리 중...")
        law_docs = self._process_law_data()
        documents.extend(law_docs)

        # 중복 제거: 동일 type + 동일 text는 1개만 유지
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for d in documents:
            md = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
            d_type = str(md.get("type", ""))
            text = str(d.get("text") or d.get("page_content") or "")
            key = (d_type, text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(d)

        print(f"✅ 총 {len(deduped)}개 문서 생성 (중복 제거 후)")
        return deduped

    def _process_finance_data(self) -> List[Dict[str, Any]]:
        """금융 데이터 처리."""
        documents: list[dict[str, Any]] = []
        json_files = self._iter_json_files(self.finance_dirs)
        if self.filtered_file.is_file():
            json_files = [self.filtered_file, *json_files]

        for json_file in json_files:
            try:
                data = self._load_json(json_file)
            except Exception:
                continue

            items = self._to_items(data)

            for item in items:
                for unit in self._iter_item_units(item):
                    context = unit["context"]
                    question = unit["question"]
                    answer_text = unit["answer"]

                    is_relevant = any(
                        keyword in context or keyword in question for keyword in FINANCE_KEYWORDS
                    )
                    if not is_relevant:
                        continue

                    # 1) 정책 설명용 문서
                    if context:
                        documents.append(
                            self._to_vector_doc(
                                page_content=context,
                                metadata={
                                    "source": "AI Hub 금융",
                                    "type": "policy_explanation",
                                    "original_question": question,
                                    "title": unit["title"],
                                    "file": json_file.name,
                                },
                            )
                        )

                    # 2) QA 사례 문서
                    if question and answer_text:
                        qa_text = (
                            f"질문: {question}\n\n"
                            f"답변: {answer_text}\n\n"
                            f"관련 정책: {context[:200]}..."
                        )
                        documents.append(
                            self._to_vector_doc(
                                page_content=qa_text,
                                metadata={
                                    "source": "AI Hub 금융",
                                    "type": "qa_case",
                                    "category": "대출 상담 사례",
                                    "title": unit["title"],
                                    "file": json_file.name,
                                },
                            )
                        )

        print(f"   금융: {len(documents)}개")
        return documents

    def _process_law_data(self) -> List[Dict[str, Any]]:
        """법률 데이터 처리."""
        documents: list[dict[str, Any]] = []
        json_files = self._iter_json_files(self.law_dirs)
        if self.filtered_file.is_file():
            json_files = [self.filtered_file, *json_files]

        for json_file in json_files:
            try:
                data = self._load_json(json_file)
            except Exception:
                continue

            items = self._to_items(data)

            for item in items:
                for unit in self._iter_item_units(item):
                    context = unit["context"]
                    question = unit["question"]
                    if not any(kw in context or kw in question for kw in LAW_KEYWORDS):
                        continue
                    if not context:
                        continue

                    documents.append(
                        self._to_vector_doc(
                            page_content=context,
                            metadata={
                                "source": "AI Hub 법률",
                                "type": "legal_basis",
                                "law_name": unit["law_name"],
                                "title": unit["title"],
                                "file": json_file.name,
                            },
                        )
                    )

        print(f"   법률: {len(documents)}개")
        return documents

    def save_processed_data(
        self, output_file: str = "data/processed/aihub_rag_documents.json"
    ) -> List[Dict[str, Any]]:
        """전처리 데이터 저장."""
        documents = self.process_for_rag()
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
        print(f"💾 {output_file} 저장 완료")
        return documents


def main() -> None:
    processor = AIHubProcessor()
    processor.save_processed_data()


if __name__ == "__main__":
    main()
