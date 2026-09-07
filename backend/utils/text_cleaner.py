"""RAG 답변 후처리·액션 블록 추출."""

from __future__ import annotations

import re
from typing import Any


def _action_block_title(block: str) -> str:
    """프롬프트는 ``[방법명]`` 형태를 권장하지만, 모델이 생략하면 첫 줄에서 제목을 추출한다."""
    b = str(block or "").strip()
    if not b:
        return ""
    m = re.search(r"\[([^\]]+)\]", b)
    if m:
        return m.group(1).strip()
    first = b.split("\n", 1)[0].strip()
    m2 = re.match(r"^(.+?)\s*\(\s*난이도\s*:", first)
    if m2:
        return re.sub(r"\s+", " ", m2.group(1).strip())
    if len(first) <= 120:
        return first
    return first[:80].rstrip() + "…"


class TextCleaner:
    """RAG 답변 후처리."""

    @staticmethod
    def clean_rag_response(text: str, max_len: int | None = 500) -> str:
        """RAG 응답 정제. ``max_len`` 이 ``None`` 이면 길이 제한 없음."""
        t = str(text or "")

        # 1. 영어 단어 제거 (단어 경계, 3글자 이상)
        t = re.sub(r"\b[a-zA-Z]{3,}\b", "", t)

        # 1b. 괄호 안 영문만 있던 경우 생기는 빈 병기 "(, )", "( , )", 빈 "()" 제거
        for _ in range(4):
            nt = re.sub(r"\(\s*(?:,\s*)+\)", "", t)
            nt = re.sub(r"\(\s*\)", "", nt)
            if nt == t:
                break
            t = nt

        # 2. 마크다운 강조·틸드 등 정리
        t = re.sub(r"[*_~`]", "", t)

        # 3. 과도한 공백·줄바꿈
        t = re.sub(r"[ \t]{2,}", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)

        # 4. 맨 앞 메타 접두어 한 번만
        t = re.sub(r"^(답변|응답|설명|Answer|Response):\s*", "", t, count=1, flags=re.IGNORECASE)

        t = t.strip()

        # 5. 최대 길이 (일반 질의는 짧게; 구조화된 대출 설명 등은 호출 쪽에서 ``max_len`` 조정)
        if max_len is not None and len(t) > max_len:
            t = t[:max_len] + "..."

        return t

    @staticmethod
    def extract_action_items(text: str) -> list[dict[str, Any]]:
        """실행 가능한 액션 블록 추출 (### 1️⃣ … 형식)."""
        actions: list[dict[str, Any]] = []
        # U+0031 U+FE0F U+20E3 = 1️⃣
        keycap = r"[1-3]\uFE0F\u20E3"
        pattern = re.compile(
            rf"^###\s*{keycap}\s*(.+?)(?=^###\s*{keycap}|\Z)",
            re.DOTALL | re.MULTILINE,
        )
        for m in pattern.finditer(str(text or "")):
            block = m.group(1).strip()
            title = _action_block_title(block)

            difficulty_m = re.search(r"난이도:\s*(쉬움|보통|어려움)", block)
            difficulty = difficulty_m.group(1) if difficulty_m else "보통"

            effect_m = re.search(r"\+([^+\n]+?)억", block)
            effect = f"+{effect_m.group(1).strip()}억" if effect_m else ""

            actions.append(
                {
                    "title": title,
                    "difficulty": difficulty,
                    "effect": effect,
                    "full_text": block[:800],
                }
            )
        return actions
