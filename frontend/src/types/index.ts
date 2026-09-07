export type InsightMode = "local" | "openai" | "compare";

/** 백엔드 `UserProfile`과 동일 */
export interface UserProfile {
  first_time_buyer: boolean;
  married: boolean;
  house_count: number;
  annual_income: number;
  region: string;
  house_price: number;
  product_cap_amount?: number;
}

export interface SourceMetadata {
  title: string;
  source: string;
  date: string;
  category: string;
  chunk_index: number;
}

export interface Source {
  content: string;
  metadata: SourceMetadata;
}

export interface RagActionItem {
  title: string;
  difficulty: string;
  effect: string;
  full_text: string;
}

/** 백엔드 `PolicyResponse`와 동일 */
export interface PolicyResponse {
  answer: string;
  sources: Source[];
  mode?: InsightMode;
  local_answer?: string;
  openai_answer?: string;
  llm_model?: string;
  local_llm_model?: string;
  openai_llm_model?: string;
}

/** 대출 계산 UI(프론트 합성) */
export interface LoanResultDisplay {
  house_price: number;
  annual_income: number;
  region: string;
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
}

/** 로컬 알아보기에서 `/api/explain-loan-policy` 결과 */
export interface LocalRagBundle {
  explanation: string;
  sources: Source[];
  action_items: RagActionItem[];
}

/** 알아보기 콜백 — API 응답 + 화면용 오버레이 */
export interface InsightUpdatePayload {
  loading: boolean;
  result: PolicyResponse | null;
  error: string | null;
  /** true: Rule 엔진 카드 우선(로컬 합성 레이아웃) */
  engineFirstLayout?: boolean;
  loanResult?: LoanResultDisplay | null;
  localRag?: LocalRagBundle | null;
}
