---
# try also 'default' to start simple
theme: seriph
# random image from a curated Unsplash collection by Anthony
# like them? see https://unsplash.com/collections/94734566/slidev
background: https://cover.sli.dev
# some information about your slides (markdown enabled)
title: Policy RAG — 발표 슬라이드
info: |
  **Policy RAG** 프로젝트용 Slidev 프레젠테이션입니다.
  규칙 엔진·RAG·LLM 구조 설명 등에 활용하세요.

  [Slidev 문서](https://sli.dev)
# apply UnoCSS classes to the current slide
class: text-center
# https://sli.dev/features/drawing
drawings:
  persist: false
# slide transition: https://sli.dev/guide/animations.html#slide-transitions
transition: slide-left
# enable Comark Syntax: https://comark.dev/syntax/markdown
comark: true
# duration of the presentation
duration: 35min
---

# Policy RAG

AI 부동산 대출 컨설턴트

<div @click="$slidev.nav.next" class="mt-12 py-1" hover:bg="white op-10">
  Prensentation <carbon:arrow-right />
</div>

<div class="abs-br m-6 text-xl">
  <button @click="$slidev.nav.openInEditor()" title="Open in Editor" class="slidev-icon-btn">
    <carbon:edit />
  </button>
  <a href="https://github.com/slidevjs/slidev" target="_blank" class="slidev-icon-btn">
    <carbon:logo-github />
  </a>
</div>

<!--
The last comment block of each slide will be treated as slide notes. It will be visible and editable in Presenter Mode along with the slide. [Read more in the docs](https://sli.dev/guide/syntax.html#notes)
-->

---
transition: fade-out
---

# AI 부동산 대출 컨설턴트

**규칙 JSON 기반 대출 한도 계산(Rule Engine)** 과 **정책 문서 검색·자연어 설명(RAG + LLM)** 을 분리해, 숫자는 결정론으로 맞추고 해설·근거는 검색 결과로 붙이는 웹 앱입니다.

- 📝 **Frontend** — React Vite
- 🎨 **Backend** — FastAPI
- 🧑‍💻 **데이터** — 국토부·금융위·주택기금공사·KB 등 
- 🤹 **LLM** — **Ollama**(Gemma4), **OpenAI** 
- 🔎 **RAG·임베딩** — **ChromaDB** 
<br>
<br>



<!--
You can have `style` tag in markdown to override the style for the current page.
Learn more: https://sli.dev/features/slide-scope-style
-->

<style>
h1 {
  background-color: #2B90B6;
  background-image: linear-gradient(45deg, #4EC5D4 10%, #146b8c 20%);
  background-size: 100%;
  -webkit-background-clip: text;
  -moz-background-clip: text;
  -webkit-text-fill-color: transparent;
  -moz-text-fill-color: transparent;
}
</style>

---
---
# 프로젝트 목표

- **금융계산 정확성** => RuleEngine으로 금융계산
<br>
<br>
- **최신정책 반영** => 데이터 수집통해 RAG검색
<br>
<br>
- **설명가능한 AI** => LLM이 계산결과 + 정책근거 조합 하여 최종설명 생성
<br>
<br>



<!--
You can have `style` tag in markdown to override the style for the current page.
Learn more: https://sli.dev/features/slide-scope-style
-->

<style>
h1 {
  background-color: #2B90B6;
  background-image: linear-gradient(45deg, #4EC5D4 10%, #146b8c 20%);
  background-size: 100%;
  -webkit-background-clip: text;
  -moz-background-clip: text;
  -webkit-text-fill-color: transparent;
  -moz-text-fill-color: transparent;
}
</style>



---
layout: two-cols
layoutClass: gap-16
---

# 구현 기능 설명






::right::

<Toc text-sm minDepth="1" maxDepth="2" />


---
level: 2
---

# 데이터 수집

AI Hub, PDF, 웹 크롤링, 수동 데이터 저장으로 데이터 수집

구성 보기:

````md magic-move {lines: true}
```python {*|2|9|*}
// aihub 데이터 이용 aihub_processor.py
def process_for_rag(self) -> List[Dict[str, Any]]:
        """RAG용 문서 생성."""
        documents: list[dict[str, Any]] = []

        finance_docs = self._process_finance_data()
        documents.extend(finance_docs)

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
```

```python {*|1-2|11,14}
// pdf 크롤링 dti_dsr_rules_crawler.py
def _extract_text_from_pdf(path: Path) -> str:
    """pypdf로 전 페이지 텍스트 추출. 미설치 시 RuntimeError."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "PDF 텍스트 추출에 pypdf 가 필요합니다. backend 에서: pip install pypdf"
        ) from e

    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        parts.append(raw)
    return _norm_whitespace("\n".join(parts))
```

```python
// 웹사이트 크롤링 molit_policy_crawler.py
REGULATION_SOURCE_PATHS = [
    "/policy/main.jsp",
    "/policy/stable/sta_b_03.jsp",
    "/policy/stable/sta_b_02.jsp",
    "/policy/stable/sta_a_01.jsp",
    "/policy/stable/sta_b_01.jsp",
]
def _crawl_from_search(self) -> None:
    ...
            search_url = f"{self.base_url}/search/search.jsp"
            r = self.session.get(
                search_url,
                params={"query": keyword},
                timeout=12,
            )
```

Non-code blocks are ignored.

```json
// 수동저장 , data/manual/policy_loans.json
{
  "last_updated": "2024-05-08",
  "source": "주택도시기금",
  "products": {
    "디딤돌대출": {
      "general": {
        "income_limit": 60000000,
        "house_price_limit": 900000000,
        "max_amount": 200000000,
        "ltv": 70,
        "dti": 60
      },
      "first_home": {
        "income_limit": 70000000,
        "house_price_limit": 900000000,
        "max_amount": 240000000,
        "ltv": 80,
        "ltv_regulation_area": 70,
        "dti": 60
      },
      "newlywed": {
        "income_limit": 85000000,
        "house_price_limit": 900000000,
        "max_amount": 320000000,
        "ltv": 70,
        "dti": 60,
        "marriage_period": 7
      },
      "conditions": {
        "age": 19,
        "house_count": 0,
        "move_in_period": 3
      }
    }
  }
}
```
````

---

# RAG 구성

<div grid="~ cols-2 gap-4">
<div>

-AI HUB 금융,법률 문서 기계독해 데이터<br>
-국토교통부 제공하는 정책풀이집 사이트 크롤링<br>
-금융위원회 보도한 PDF 자료 <br>
-주택도시기금 정책자금 수동 자료<br>
-KB Think 크롤링<br>
-마이홈 정책 대출 자료<br>
-국토교통부+금융위원회+주택도시기금 추가 웹크롤링<br>



</div>
<div>

<img src="/data_structure.png" alt="데이터 구조" class="mx-auto max-h-100 object-contain" />


</div>
</div>

<!--
Presenter note with **bold**, *italic*, and ~~striked~~ text.

Also, HTML elements are valid:
<div class="flex w-full">
  <span style="flex-grow: 1;">Left content</span>
  <span>Right content</span>
</div>
-->

---
class: px-20
---

# 결과화면1(계산)

사용자 입력값 토대로 계산하여 최대 대출 가능 금액 계산

<div grid="~ cols-2 gap-2" m="t-2">



<img border="rounded" src="/result1.png" alt="">

<img border="rounded" src="/result2.png" alt="">

</div>

Read more about [How to use a theme](https://sli.dev/guide/theme-addon#use-theme) and
check out the [Awesome Themes Gallery](https://sli.dev/resources/theme-gallery).

---


# 결과화면2(RAG)

RAG + LLM 통해 대출가능금액 설명과 대출을 더 많이 받을수있는 정보 검색 전달

<div grid="~ cols-2 gap-2" m="t-2">



<img border="rounded" src="/result3.png" alt="">

<img border="rounded" src="/result4.png" alt="">

</div>

Read more about [How to use a theme](https://sli.dev/guide/theme-addon#use-theme) and
check out the [Awesome Themes Gallery](https://sli.dev/resources/theme-gallery).

---

# 결과화면3(RAG)

RAG + LLM 통해 대출가능금액 설명과 대출을 더 많이 받을수있는 정보 검색 전달

<div grid="~ cols-2 gap-2" m="t-2">



<img border="rounded" src="/result5.png" alt="">

<img border="rounded" src="/result6.png" alt="">

</div>

Read more about [How to use a theme](https://sli.dev/guide/theme-addon#use-theme) and
check out the [Awesome Themes Gallery](https://sli.dev/resources/theme-gallery).

---
layout: center
class: text-center
---

<div class="text-4xl font-semibold">
  감사합니다
</div>