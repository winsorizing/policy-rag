import axios, { AxiosError } from "axios";
import {
  InsightMode,
  PolicyResponse,
  RagActionItem,
  Source,
  UserProfile,
} from "../types";

/**
 * 빈 문자열: Vite dev 서버가 `/api` → `vite.config.ts` proxy → 백엔드로 전달.
 * 프로덕션/직접 백엔드 접속 시: `VITE_API_BASE_URL=http://127.0.0.1:8000` 등 설정.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    "Content-Type": "application/json",
  },
});

function withCause(message: string, cause: unknown): Error {
  const err = new Error(message) as Error & { cause?: unknown };
  err.cause = cause;
  return err;
}

function axiosDetailPayload(data: unknown): string {
  if (data === null || data === undefined) return "";
  if (typeof data === "string") return data;
  if (typeof data === "object" && data !== null && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d))
      return d.map((x) => JSON.stringify(x)).join(" ");
    return String(d);
  }
  return "";
}

function axiosFailureMessage(error: AxiosError): string {
  if (!error.response) {
    const code = error.code;
    if (code === "ECONNREFUSED" || code === "ERR_NETWORK") {
      const hint =
        API_BASE_URL === ""
          ? "백엔드에 연결되지 않았습니다. backend에서 `uvicorn app.main:app --reload --port 8000` 실행 후, Vite 프록시(127.0.0.1:8000)가 동작하는지 확인하세요."
          : `백엔드(${API_BASE_URL})에 연결되지 않았습니다. 서버 실행 및 URL(VITE_API_BASE_URL)을 확인하세요.`;
      return hint;
    }
    if (error.message?.includes("timeout"))
      return "요청 시간이 초과되었습니다. 서버 부하 또는 LLM 응답 지연일 수 있습니다.";
    return `네트워크 오류: ${error.message || code || "알 수 없음"}`;
  }
  const detail = axiosDetailPayload(error.response.data);
  if (detail) return detail;
  return `HTTP ${error.response.status}`;
}

/** 프로필만으로 RAG 요약 (Local Ollama / OpenAI / 비교) */
export const profileInsight = async (
  userProfile: UserProfile,
  insightMode: InsightMode = "local"
): Promise<PolicyResponse> => {
  try {
    const response = await apiClient.post<PolicyResponse>(
      "/api/profile-insight",
      { ...userProfile, insight_mode: insightMode }
    );
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw withCause(axiosFailureMessage(error), error);
    }

    throw withCause("알 수 없는 오류가 발생했습니다.", error);
  }
};

export interface LoanCalculationResult {
  max_loan_amount: number;
  max_loan_by_ltv: number;
  max_loan_by_dti: number;
  max_loan_by_dsr: number;
  ltv_limit: number;
  dti_limit: number;
  dsr_limit: number;
  ltv_ratio: number;
  dti_ratio: number;
  dsr_ratio: number;
  regulation_type: string;
  restrictions: string[];
  limiting_factor: string;
  explanation: string;
}

export const calculateLoanEligibility = async (
  userProfile: UserProfile
): Promise<LoanCalculationResult> => {
  const response = await apiClient.post<LoanCalculationResult>(
    "/api/calculate-loan",
    userProfile
  );
  return response.data;
};

export interface PolicyExplainResponse {
  explanation: string;
  sources: Source[];
  action_items?: RagActionItem[];
  /** RAG에 사용된 Ollama 모델 태그 */
  llm_model?: string | null;
}

/** Rule 엔진과 분리: 정책 문서 RAG 설명·출처만 */
export const explainLoanPolicy = async (
  userProfile: UserProfile
): Promise<PolicyExplainResponse> => {
  const response = await apiClient.post<PolicyExplainResponse>(
    "/api/explain-loan-policy",
    userProfile
  );
  return response.data;
};

export const healthCheck = async (): Promise<{ status: string }> => {
  try {
    const response = await apiClient.get<{ status?: string; ok?: boolean }>(
      "/api/health"
    );
    const data = response.data;
    if (data.status === "healthy" || data.ok === true) {
      return { status: "healthy" };
    }
    return { status: "error" };
  } catch {
    return { status: "error" };
  }
};

/** 상단 새로고침 시 ``run_all_crawlers`` 요약(규제·DTI·merge, update_log 반영 여부) */
export interface RuleCrawlSummary {
  all_ok?: boolean;
  crawl_all_ok?: boolean;
  merge_all_ok?: boolean | null;
  steps?: Array<{ name?: string; ok?: boolean; skipped?: boolean }>;
}

export interface RefreshKnowledgeResponse {
  ok: boolean;
  message: string;
  stats: {
    skipped?: boolean;
    skip_reason?: string;
    doc_count: number;
    chunk_count: number;
    persist_directory: string | null;
    corpus_json: string | null;
    rule_crawl?: RuleCrawlSummary | { skipped?: boolean; note?: string };
  };
}

/** 크롤링 + 규칙 merge + 벡터DB 전체 재빌드(백엔드에서 항상 강제 실행). */
export const refreshKnowledge = async (): Promise<RefreshKnowledgeResponse> => {
  const adminKey = import.meta.env.VITE_ADMIN_SECRET_KEY ?? "";
  const response = await apiClient.post<RefreshKnowledgeResponse>(
    "/api/refresh-knowledge",
    null,
    adminKey ? { headers: { "X-Admin-Key": adminKey } } : undefined
  );
  return response.data;
};

export interface RunCrawlersStep {
  name: string;
  ok: boolean;
  skipped?: boolean;
  reason?: string;
  result?: unknown;
  error?: string;
}

export interface RunCrawlersResponse {
  steps: RunCrawlersStep[];
  all_ok: boolean;
  crawl_all_ok?: boolean;
  merge?: {
    all_ok?: boolean;
    skipped?: boolean;
    note?: string;
    result?: unknown;
    error?: string | null;
  };
}

export interface RulesUpdateLogResponse {
  updateDate: string | null;
}

/** ``history/update_log.json`` 의 ``updateDate`` (규칙 merge 기록) */
export const fetchRulesUpdateLog = async (): Promise<RulesUpdateLogResponse> => {
  const response = await apiClient.get<RulesUpdateLogResponse>(
    "/api/rules-update-log"
  );
  return response.data;
};

/**
 * `run_crawler.run_all_crawlers` — 규제지역·DTI/DSR 등 JSON 크롤(시간 소요 가능).
 * 기본은 백엔드 `skip_if_fresh=true`: merge가 오늘(KST)이면 네트워크 크롤 생략.
 */
export const runCrawlers = async (options?: {
  skipIfFresh?: boolean;
}): Promise<RunCrawlersResponse> => {
  const skipIfFresh = options?.skipIfFresh !== false;
  try {
    const response = await apiClient.post<RunCrawlersResponse>(
      "/api/run-crawlers",
      {},
      { timeout: 300_000, params: { skip_if_fresh: skipIfFresh } }
    );
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw withCause(axiosFailureMessage(error), error);
    }
    throw withCause("크롤 요청 중 알 수 없는 오류가 발생했습니다.", error);
  }
};
