from __future__ import annotations

import os
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

_BACKEND_DIR = Path(__file__).resolve().parent
_DEFAULT_CHROMA_DIR = str(_BACKEND_DIR / "chroma_db")


def _ollama_base_url() -> str | None:
    return os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or None


def _probe_ollama_embeddings(embeddings: OllamaEmbeddings, model_name: str) -> None:
    """임베딩 모델 미설치(404) 시 원인 안내."""
    try:
        embeddings.embed_query("ping")
    except Exception as e:
        err = str(e).lower()
        if "404" in err or "not found" in err or "status code: 404" in err:
            raise RuntimeError(
                f'Ollama에 임베딩 모델 "{model_name}" 이 없습니다. '
                f"다음을 실행한 뒤 서버를 다시 시작하세요:\n"
                f"  ollama pull {model_name}\n"
                f"(다른 모델을 쓰려면 환경변수 OLLAMA_EMBED_MODEL 을 바꾸고, "
                f"같은 모델로 chroma_db 를 다시 빌드하세요.)"
            ) from e
        raise


class VectorStoreManager:
    """Chroma 영속 저장. 임베딩은 로컬 Ollama(예: joonoh/HyperCLOVAX-SEED-Text-Instruct-1.5B:latest)."""

    def __init__(self, persist_directory: str | None = None) -> None:
        self.persist_directory = persist_directory or _DEFAULT_CHROMA_DIR
        embed_model = os.getenv("OLLAMA_EMBED_MODEL", "joonoh/HyperCLOVAX-SEED-Text-Instruct-1.5B:latest")
        self.embeddings = OllamaEmbeddings(
            model=embed_model,
            base_url=_ollama_base_url(),
        )
        _probe_ollama_embeddings(self.embeddings, embed_model)
        self.vector_store = None

    def create_vector_store(self, documents: list[dict[str, object]]) -> Chroma:
        docs = [
            Document(
                page_content=str(doc["text"]),
                metadata={k: str(v) for k, v in (doc["metadata"] or {}).items()},
            )
            for doc in documents
        ]
        self.vector_store = Chroma.from_documents(
            documents=docs,
            embedding=self.embeddings,
            persist_directory=self.persist_directory,
        )
        return self.vector_store

    def load_vector_store(self) -> Chroma:
        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
        )
        return self.vector_store

    def similarity_search(self, query: str, k: int = 3):
        if not self.vector_store:
            self.load_vector_store()
        assert self.vector_store is not None
        return self.vector_store.similarity_search(query, k=k)
