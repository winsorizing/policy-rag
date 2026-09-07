from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")

from data.aihub.aihub_processor import AIHubProcessor
from vector_store import VectorStoreManager


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _policy_json_to_text(title: str, data: dict[str, Any]) -> str:
    if title == "regulation_areas":
        regions = data.get("regions") if isinstance(data.get("regions"), dict) else {}
        hot = regions.get("투기과열지구") if isinstance(regions, dict) else []
        adj = regions.get("조정대상지역") if isinstance(regions, dict) else []
        return (
            f"규제지역 요약 ({data.get('last_updated', '')})\n"
            f"- 투기과열지구: {', '.join((hot or [])[:60])}\n"
            f"- 조정대상지역: {', '.join((adj or [])[:60])}\n"
            f"- 일반지역: 기타 모든 지역"
        )

    # 나머지는 JSON 본문을 보존해 문서화
    return f"{title} ({data.get('last_updated', '')})\n" + json.dumps(
        data, ensure_ascii=False, indent=2
    )


def _load_aihub_documents(aihub_dir: Path, processed_out: Path) -> list[dict[str, Any]]:
    processor = AIHubProcessor(aihub_dir=str(aihub_dir))
    docs = processor.save_processed_data(str(processed_out))
    normalized: list[dict[str, Any]] = []
    for d in docs:
        text = str(d.get("text") or d.get("page_content") or "").strip()
        md = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
        if text:
            normalized.append({"text": text, "metadata": {k: str(v) for k, v in md.items()}})
    return normalized


def _load_rule_documents(rules_dir: Path, source_type: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if not rules_dir.is_dir():
        return docs

    targets = (
        "regulation_areas.json",
        "dti_dsr_rules.json",
        "ltv_rules.json",
        "policy_loans.json",
    )
    for name in targets:
        p = rules_dir / name
        if not p.is_file():
            continue
        try:
            data = _load_json(p)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        title = p.stem
        text = _policy_json_to_text(title, data)
        docs.append(
            {
                "text": text,
                "metadata": {
                    "source": str(data.get("source", title)),
                    "type": source_type,
                    "title": title,
                    "date": str(data.get("last_updated", "")),
                    "path": str(p),
                },
            }
        )
    return docs


def _chunk_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunked: list[dict[str, Any]] = []
    for doc in docs:
        text = str(doc.get("text", "")).strip()
        md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        parts = _chunk_text(text, chunk_size=1000, overlap=200)
        for i, part in enumerate(parts):
            chunk_md = {**md, "chunk_index": str(i), "total_chunks": str(len(parts))}
            chunked.append({"text": part, "metadata": {k: str(v) for k, v in chunk_md.items()}})
    return chunked


def build_vectordb(
    *,
    aihub_dir: Path,
    processed_out: Path,
    persist_dir: Path,
    prepare_only: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    def _say(msg: str) -> None:
        if not quiet:
            print(msg)

    _say("\n🚀 Vector DB 구축 시작")
    _say("=" * 60)

    _say("\n[1/4] AI Hub 데이터 전처리...")
    aihub_docs = _load_aihub_documents(aihub_dir, processed_out)
    _say(f"   AI Hub: {len(aihub_docs)}개")

    _say("\n[2/4] 크롤링 규칙 데이터 로드...")
    crawled_docs = _load_rule_documents(_BACKEND_DIR / "data" / "rules" / "crawled", "crawled_rule")
    _say(f"   크롤링: {len(crawled_docs)}개")

    _say("\n[3/4] 병합(최종) 규칙 데이터 로드...")
    merged_docs = _load_rule_documents(_BACKEND_DIR / "data" / "rules" / "merge", "merged_rule")
    _say(f"   병합 규칙: {len(merged_docs)}개")

    _say("\n[4/4] 문서 통합 및 청킹...")
    all_docs = aihub_docs + crawled_docs + merged_docs
    chunked_docs = _chunk_documents(all_docs)
    _say(f"   원본 문서: {len(all_docs)}개")
    _say(f"   청킹 후: {len(chunked_docs)}개")

    corpus_json = str(processed_out.resolve()) if processed_out.is_file() else None
    persist_resolved = str(persist_dir.resolve())

    if prepare_only:
        _say("\nℹ️ --prepare-only: 벡터 DB 생성은 건너뜁니다.")
        return {
            "doc_count": len(all_docs),
            "chunk_count": len(chunked_docs),
            "persist_directory": persist_resolved,
            "corpus_json": corpus_json,
            "prepare_only": True,
        }

    vs_manager = VectorStoreManager(persist_directory=str(persist_dir))
    vs_manager.create_vector_store(chunked_docs)
    _say(f"\n✅ Vector DB 구축 완료! ({persist_dir})")

    if not quiet:
        print("\n🧪 테스트 검색...")
        test_query = "투기과열지구에서 생애최초 구입자 LTV는?"
        results = vs_manager.similarity_search(test_query, k=3)
        print(f"\n질문: {test_query}")
        for i, doc in enumerate(results, 1):
            print(f"\n[{i}] {doc.metadata.get('source', 'N/A')}")
            print(f"    {doc.page_content[:150]}...")

    return {
        "doc_count": len(all_docs),
        "chunk_count": len(chunked_docs),
        "persist_directory": persist_resolved,
        "corpus_json": corpus_json,
        "prepare_only": False,
    }


def build_database(*, prepare_only: bool = False) -> dict[str, Any]:
    """기본 경로로 Vector DB 빌드 (AIHub + crawled + merge 규칙)."""
    return build_vectordb(
        aihub_dir=_BACKEND_DIR / "data" / "aihub",
        processed_out=_BACKEND_DIR / "data" / "processed" / "aihub_rag_documents.json",
        persist_dir=_BACKEND_DIR / "chroma_db",
        prepare_only=prepare_only,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AIHub 포함 Vector DB 빌드")
    parser.add_argument(
        "--aihub-dir",
        type=Path,
        default=_BACKEND_DIR / "data" / "aihub",
        help="AI Hub 데이터 루트 디렉터리",
    )
    parser.add_argument(
        "--processed-out",
        type=Path,
        default=_BACKEND_DIR / "data" / "processed" / "aihub_rag_documents.json",
        help="AIHub 전처리 결과 저장 경로",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=_BACKEND_DIR / "chroma_db",
        help="Chroma 영속 저장 디렉터리",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="문서 통합/청킹까지만 실행 (임베딩/DB 생성 생략)",
    )
    args = parser.parse_args()

    build_vectordb(
        aihub_dir=args.aihub_dir,
        processed_out=args.processed_out,
        persist_dir=args.persist_dir,
        prepare_only=args.prepare_only,
    )


if __name__ == "__main__":
    main()
