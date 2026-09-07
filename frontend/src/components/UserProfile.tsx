// src/components/UserProfile.tsx
import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  CircularProgress,
  Tooltip,
  IconButton,
  Snackbar,
  Alert,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import {
  UserProfile as UserProfileType,
  InsightMode,
  InsightUpdatePayload,
  LoanResultDisplay,
  Source,
  RagActionItem,
} from '../types';
import {
  profileInsight,
  calculateLoanEligibility,
  explainLoanPolicy,
  runCrawlers,
  type LoanCalculationResult,
} from '../services/api';
import RegionPicker from './RegionPicker';
import {
  LOAN_UI_GREEN,
  LOAN_UI_BORDER,
  LOAN_UI_MUTED,
  WON_STEP,
} from '../constants/loanUi';

interface UserProfileProps {
  onProfileSave: (profile: UserProfileType) => void;
  insightLoading: boolean;
  onInsightUpdate: (payload: InsightUpdatePayload) => void;
  /** 크롤·merge 완료 후 상단 ``update_log`` 라벨 갱신 */
  onRulesDataSynced?: () => void | Promise<void>;
}

/** 보유 주택 수 그리드 — 백엔드는 house_count·first_time_buyer로 매핑 */
export type OwnershipCategory =
  | 'lifetime_first'
  | 'working_class'
  | 'no_home'
  | 'one_home'
  | 'two_plus';

interface ProfileForm {
  ownershipCategory: OwnershipCategory;
  married: boolean;
  annualIncome: number;
  region: string;
  housePrice: number;
}

type OwnershipCell =
  | { kind: 'option'; id: OwnershipCategory; label: string }
  | { kind: 'empty' };

const OWNERSHIP_CELLS: OwnershipCell[] = [
  { kind: 'option', id: 'lifetime_first', label: '생애최초' },
  { kind: 'option', id: 'working_class', label: '서민실수요' },
  { kind: 'option', id: 'no_home', label: '무주택' },
  { kind: 'option', id: 'one_home', label: '1주택' },
  { kind: 'option', id: 'two_plus', label: '2주택이상' },
  { kind: 'empty' },
];

const QUICK_PRICE_ADD: ReadonlyArray<{ label: string; delta: number }> = [
  { label: '+1,000만', delta: 10_000_000 },
  { label: '+1억', delta: 100_000_000 },
  { label: '+10억', delta: 1_000_000_000 },
];

const QUICK_INCOME_ADD: ReadonlyArray<{ label: string; delta: number }> = [
  { label: '+1,000만', delta: 10_000_000 },
  { label: '+100만', delta: 1_000_000 },
  { label: '+10만', delta: 100_000 },
];

function ownershipToProfileFields(category: OwnershipCategory): {
  house_count: number;
  first_time_buyer: boolean;
} {
  switch (category) {
    case 'lifetime_first':
      return { house_count: 0, first_time_buyer: true };
    case 'working_class':
      return { house_count: 0, first_time_buyer: false };
    case 'no_home':
      return { house_count: 0, first_time_buyer: false };
    case 'one_home':
      return { house_count: 1, first_time_buyer: false };
    case 'two_plus':
      return { house_count: 2, first_time_buyer: false };
    default:
      return { house_count: 0, first_time_buyer: false };
  }
}

const DEFAULT_PROFILE: ProfileForm = {
  ownershipCategory: 'no_home',
  married: false,
  annualIncome: 0,
  region: '',
  housePrice: 0,
};

function loanResultFromEngine(
  userProfile: UserProfileType,
  loan: LoanCalculationResult,
): LoanResultDisplay {
  return {
    house_price: userProfile.house_price,
    annual_income: userProfile.annual_income,
    region: userProfile.region,
    max_loan_amount: loan.max_loan_amount,
    max_loan_by_ltv: loan.max_loan_by_ltv,
    max_loan_by_dti: loan.max_loan_by_dti,
    max_loan_by_dsr: loan.max_loan_by_dsr,
    ltv_limit: loan.ltv_limit,
    dti_limit: loan.dti_limit,
    dsr_limit: loan.dsr_limit,
    ltv_ratio: loan.ltv_ratio,
    dti_ratio: loan.dti_ratio,
    dsr_ratio: loan.dsr_ratio,
    regulation_type: loan.regulation_type,
    restrictions: loan.restrictions,
    limiting_factor: loan.limiting_factor,
  };
}

/** 숫자만 추출 후 1만 원 단위로 맞춤 (0 허용 시 미입력·0원 유지, 양수는 1만 원 단위) */
function normalizeManWon(
  raw: number,
  opts: { allowZero: boolean; minNonZero: number }
): number {
  if (!Number.isFinite(raw) || raw < 0) {
    return opts.allowZero ? 0 : opts.minNonZero;
  }
  if (opts.allowZero && raw === 0) return 0;
  const rounded = Math.round(raw / WON_STEP) * WON_STEP;
  if (opts.allowZero && rounded === 0) {
    return raw === 0 ? 0 : opts.minNonZero;
  }
  return Math.max(opts.minNonZero, rounded);
}

function digitsOnlyToNumber(s: string): number {
  const d = s.replace(/\D/g, '');
  if (!d) return 0;
  const n = Number(d);
  return Number.isFinite(n) ? n : 0;
}

function formatKoMoney(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '';
  const eok = Math.floor(n / 100_000_000);
  const man = Math.floor((n % 100_000_000) / 10_000);
  if (eok <= 0) {
    return `${man.toLocaleString('ko-KR')}만원`;
  }
  if (man <= 0) {
    return `${eok.toLocaleString('ko-KR')}억`;
  }
  return `${eok.toLocaleString('ko-KR')}억 ${man.toLocaleString('ko-KR')}만원`;
}

/** 천 단위 콤마(예: 10,000), 1만 원 단위(최소 단위 1만) — 편집 중에는 숫자만, blur 시 정규화 */
function ManWonInput({
  value,
  onCommit,
  allowZero,
  placeholder = '0',
  fontSize = '1rem',
  fontWeight = 500,
  maxWidth = '75%',
}: {
  value: number;
  onCommit: (n: number) => void;
  allowZero: boolean;
  placeholder?: string;
  fontSize?: string;
  fontWeight?: number;
  maxWidth?: string;
}) {
  const [focused, setFocused] = useState(false);
  const [text, setText] = useState('');

  const minNonZero = WON_STEP;

  const handleFocus = () => {
    setFocused(true);
    if (allowZero && value === 0) {
      setText('');
      return;
    }
    setText(String(value));
  };

  const handleBlur = () => {
    setFocused(false);
    const parsed = digitsOnlyToNumber(text);
    const next = normalizeManWon(parsed, { allowZero, minNonZero });
    onCommit(next);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setText(e.target.value.replace(/\D/g, ''));
  };

  const display =
    focused
      ? text
      : value === 0
        ? ''
        : value.toLocaleString('en-US');

  return (
    <input
      type="text"
      inputMode="numeric"
      autoComplete="off"
      placeholder={placeholder}
      value={display}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onChange={handleChange}
      style={{
        border: 'none',
        outline: 'none',
        font: 'inherit',
        fontSize,
        fontWeight,
        textAlign: 'right',
        width: '100%',
        maxWidth,
        color: '#212121',
        background: 'transparent',
      }}
    />
  );
}

function SectionLabel({
  children,
  info,
}: {
  children: React.ReactNode;
  info?: string;
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1.25 }}>
      <Typography component="span" sx={{ fontWeight: 700, fontSize: '0.95rem', color: 'text.primary' }}>
        {children}
      </Typography>
      {info ? (
        <Tooltip title={info} arrow placement="top">
          <IconButton size="small" aria-label="안내" sx={{ p: 0.25 }}>
            <InfoOutlinedIcon sx={{ fontSize: 18, color: LOAN_UI_MUTED }} />
          </IconButton>
        </Tooltip>
      ) : null}
    </Box>
  );
}

const UserProfile: React.FC<UserProfileProps> = ({
  onProfileSave,
  insightLoading,
  onInsightUpdate,
  onRulesDataSynced,
}) => {
  const [profile, setProfile] = useState<ProfileForm>(DEFAULT_PROFILE);
  const [formAlert, setFormAlert] = useState<string | null>(null);

  const [insightMode, setInsightMode] = useState<InsightMode>('local');

  const buildUserProfile = (): UserProfileType => {
    const { house_count, first_time_buyer } = ownershipToProfileFields(
      profile.ownershipCategory
    );
    return {
      first_time_buyer,
      married: profile.married,
      house_count,
      annual_income: profile.annualIncome,
      region: profile.region || '기타 지역',
      house_price: profile.housePrice,
      product_cap_amount: 0,
    };
  };

  const handleInsight = async () => {
    const userProfile = buildUserProfile();
    onInsightUpdate({ loading: true, result: null, error: null });
    try {
      try {
        const crawl = await runCrawlers();
        await onRulesDataSynced?.();
        if (!crawl.all_ok) {
          const bad = crawl.steps.filter((s) => !s.ok && !s.skipped);
          const failedNames = bad.map((s) => s.name).join(', ');
          const firstErr = bad.find((s) => s.error)?.error;
          setFormAlert(
            firstErr
              ? `크롤 경고(${failedNames || '알 수 없음'}): ${firstErr}. 요약은 계속 진행합니다.`
              : failedNames
                ? `일부 크롤러 실패(${failedNames}). 요약은 계속 진행합니다.`
                : '크롤 결과를 확인해 주세요. 요약은 계속 진행합니다.'
          );
        }
      } catch (crawlErr) {
        onInsightUpdate({
          loading: false,
          result: null,
          error:
            crawlErr instanceof Error
              ? `크롤 실행 실패: ${crawlErr.message}`
              : '크롤 실행 중 오류가 발생했습니다.',
        });
        return;
      }

      // Local 모드: Rule 엔진 + 정책 RAG를 순차 호출(한 번의 알아보기에서 둘 다 표시)
      if (insightMode === 'local') {
        const loan = await calculateLoanEligibility(userProfile);
        let policyRagExplanation = '';
        let policyRagSources: Source[] = [];
        let policyRagActionItems: RagActionItem[] = [];
        let ollamaModelLabel: string | undefined;
        try {
          const rag = await explainLoanPolicy(userProfile);
          policyRagExplanation = rag.explanation;
          policyRagSources = rag.sources ?? [];
          policyRagActionItems = rag.action_items ?? [];
          ollamaModelLabel = rag.llm_model ?? undefined;
        } catch (ragErr) {
          policyRagExplanation =
            `정책 문서(RAG) 설명을 불러오지 못했습니다.\n` +
            (ragErr instanceof Error ? ragErr.message : '');
        }
        onInsightUpdate({
          loading: false,
          result: {
            answer: loan.explanation,
            sources: [],
            mode: 'local',
            llm_model: ollamaModelLabel,
          },
          engineFirstLayout: true,
          loanResult: loanResultFromEngine(userProfile, loan),
          localRag: {
            explanation: policyRagExplanation,
            sources: policyRagSources,
            action_items: policyRagActionItems,
          },
          error: null,
        });
        onProfileSave(userProfile);
        return;
      }

      // OpenAI/비교 모드: 기존 경로 유지 (계산 엔진 + 모드별 요약)
      const loan = await calculateLoanEligibility(userProfile);
      const result = await profileInsight(userProfile, insightMode);

      onInsightUpdate({
        loading: false,
        result,
        engineFirstLayout: false,
        loanResult: loanResultFromEngine(userProfile, loan),
        localRag: null,
        error: null,
      });
      onProfileSave(userProfile);
    } catch (e) {
      onInsightUpdate({
        loading: false,
        result: null,
        error: e instanceof Error ? e.message : '대출 계산/요약을 불러오지 못했습니다.',
      });
    }
  };

  const getMissingFieldLabel = (): string | null => {
    if (profile.annualIncome <= 0) return '연소득';
    if (!profile.region.trim()) return '대상 주택 지역';
    if (profile.housePrice <= 0) return '대상 주택 시세';
    return null;
  };

  const handleSubmit = async () => {
    const missing = getMissingFieldLabel();
    if (missing) {
      setFormAlert(`${missing} 값을 입력한 뒤 다시 시도해 주세요.`);
      return;
    }
    await handleInsight();
  };

  const handleReset = () => {
    setProfile({ ...DEFAULT_PROFILE });
  };

  return (
    <Card
      elevation={0}
      sx={{
        height: '100%',
        border: `1px solid ${LOAN_UI_BORDER}`,
        borderRadius: 2,
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        bgcolor: '#fff',
      }}
    >
      <CardContent sx={{ p: { xs: 2.5, sm: 3 } }}>
        {/* 보유 주택 수 */}
        <Box sx={{ mb: 3 }}>
          <SectionLabel info="주택 보유·실수요 구분에 따라 규제 한도(간이 계산)에 반영됩니다.">
            보유 주택 수
          </SectionLabel>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gridTemplateRows: 'repeat(2, minmax(48px, auto))',
              border: `1px solid ${LOAN_UI_BORDER}`,
              borderRadius: 2,
              overflow: 'hidden',
              bgcolor: '#fff',
            }}
          >
            {OWNERSHIP_CELLS.map((cell, index) => {
              const col = index % 3;
              const row = Math.floor(index / 3);
              const borderRight = col < 2 ? `1px solid ${LOAN_UI_BORDER}` : 'none';
              const borderBottom = row === 0 ? `1px solid ${LOAN_UI_BORDER}` : 'none';
              if (cell.kind === 'empty') {
                return (
                  <Box
                    key="ownership-empty"
                    sx={{
                      borderRight,
                      borderBottom,
                      borderColor: LOAN_UI_BORDER,
                      bgcolor: '#fafafa',
                      minHeight: 48,
                    }}
                  />
                );
              }
              const selected = profile.ownershipCategory === cell.id;
              return (
                <Box
                  key={cell.id}
                  component="button"
                  type="button"
                  onClick={() =>
                    setProfile((prev) => ({ ...prev, ownershipCategory: cell.id }))
                  }
                  sx={{
                    appearance: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    font: 'inherit',
                    minHeight: 48,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    px: 1,
                    py: 1,
                    fontSize: '0.8125rem',
                    bgcolor: '#fff',
                    color: selected ? LOAN_UI_GREEN : LOAN_UI_MUTED,
                    fontWeight: selected ? 600 : 400,
                    borderRight,
                    borderBottom,
                    borderColor: LOAN_UI_BORDER,
                    boxShadow: selected ? `inset 0 0 0 2px ${LOAN_UI_GREEN}` : 'none',
                    transition: 'color 0.15s, box-shadow 0.15s',
                    '&:hover': {
                      bgcolor: selected ? '#fff' : '#fafafa',
                    },
                  }}
                >
                  {cell.label}
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* 혼인 여부 */}
        <Box sx={{ mb: 3 }}>
          <SectionLabel>혼인 여부</SectionLabel>
          <Box sx={{ display: 'flex', width: '100%', borderBottom: `1px solid ${LOAN_UI_BORDER}` }}>
            {(
              [
                { id: true, label: '기혼' },
                { id: false, label: '미혼' },
              ] as const
            ).map(({ id, label }) => {
              const sel = profile.married === id;
              return (
                <Box
                  key={String(id)}
                  component="button"
                  type="button"
                  onClick={() => setProfile((p) => ({ ...p, married: id }))}
                  sx={{
                    flex: 1,
                    py: 1.5,
                    border: 'none',
                    cursor: 'pointer',
                    font: 'inherit',
                    fontSize: '0.9rem',
                    fontWeight: sel ? 600 : 400,
                    color: sel ? LOAN_UI_GREEN : LOAN_UI_MUTED,
                    bgcolor: '#fff',
                    borderBottom: sel ? `2px solid ${LOAN_UI_GREEN}` : '2px solid transparent',
                    mb: '-1px',
                  }}
                >
                  {label}
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* 연소득 */}
        <Box sx={{ mb: 3 }}>
          <SectionLabel>연소득</SectionLabel>
          <Box
            component="label"
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 0.5,
              borderBottom: `2px solid ${LOAN_UI_GREEN}`,
              py: 1,
              px: 0,
            }}
          >
            <ManWonInput
              value={profile.annualIncome}
              onCommit={(n) => setProfile((p) => ({ ...p, annualIncome: n }))}
              allowZero
              maxWidth="70%"
            />
            <Typography sx={{ color: LOAN_UI_MUTED, fontSize: '0.95rem', flexShrink: 0 }}>원</Typography>
          </Box>
          {profile.annualIncome > 0 ? (
            <Typography
              variant="caption"
              sx={{ display: 'block', mt: 0.75, textAlign: 'right', color: LOAN_UI_MUTED }}
            >
              {formatKoMoney(profile.annualIncome)}
            </Typography>
          ) : null}
          <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap' }}>
            {QUICK_INCOME_ADD.map(({ label, delta }) => (
              <Button
                key={`income-${label}`}
                size="small"
                variant="outlined"
                onClick={() =>
                  setProfile((p) => ({
                    ...p,
                    annualIncome: normalizeManWon(p.annualIncome + delta, {
                      allowZero: true,
                      minNonZero: WON_STEP,
                    }),
                  }))
                }
                sx={{
                  borderRadius: 10,
                  px: 1.5,
                  py: 0.5,
                  fontSize: '0.75rem',
                  textTransform: 'none',
                  borderColor: LOAN_UI_BORDER,
                  color: LOAN_UI_MUTED,
                  bgcolor: '#f5f5f5',
                  '&:hover': { borderColor: LOAN_UI_MUTED, bgcolor: '#eee' },
                }}
              >
                {label}
              </Button>
            ))}
          </Box>
        </Box>

        {/* 대상 주택 지역 */}
        <Box sx={{ mb: 3 }}>
          <RegionPicker
            accentColor={LOAN_UI_GREEN}
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography component="span" sx={{ fontWeight: 700, fontSize: '0.95rem' }}>
                  대상 주택 지역
                </Typography>
                <Tooltip title="규제 구역 판단에 사용되는 주택 소재지입니다." arrow>
                  <IconButton size="small" aria-label="지역 안내" sx={{ p: 0.25 }}>
                    <InfoOutlinedIcon sx={{ fontSize: 18, color: LOAN_UI_MUTED }} />
                  </IconButton>
                </Tooltip>
              </Box>
            }
            value={profile.region}
            onChange={(region) => setProfile((prev) => ({ ...prev, region }))}
          />
        </Box>

        {/* 대상 주택 시세 */}
        <Box sx={{ mb: 2 }}>
          <SectionLabel>대상 주택 시세</SectionLabel>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 0.5,
              borderBottom: `3px solid ${LOAN_UI_GREEN}`,
              py: 1.25,
              px: 0,
            }}
          >
            <ManWonInput
              value={profile.housePrice}
              onCommit={(n) => setProfile((p) => ({ ...p, housePrice: n }))}
              allowZero
              placeholder="0"
              fontSize="1.05rem"
              fontWeight={600}
            />
            <Typography sx={{ color: LOAN_UI_MUTED, fontSize: '0.95rem', flexShrink: 0 }}>원</Typography>
          </Box>
          {profile.housePrice > 0 ? (
            <Typography
              variant="caption"
              sx={{ display: 'block', mt: 0.75, textAlign: 'right', color: LOAN_UI_MUTED }}
            >
              {formatKoMoney(profile.housePrice)}
            </Typography>
          ) : null}
          <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap' }}>
            {QUICK_PRICE_ADD.map(({ label, delta }) => (
              <Button
                key={label}
                size="small"
                variant="outlined"
                onClick={() =>
                  setProfile((p) => ({
                    ...p,
                    housePrice: normalizeManWon(p.housePrice + delta, {
                      allowZero: true,
                      minNonZero: WON_STEP,
                    }),
                  }))
                }
                sx={{
                  borderRadius: 10,
                  px: 1.5,
                  py: 0.5,
                  fontSize: '0.75rem',
                  textTransform: 'none',
                  borderColor: LOAN_UI_BORDER,
                  color: LOAN_UI_MUTED,
                  bgcolor: '#f5f5f5',
                  '&:hover': { borderColor: LOAN_UI_MUTED, bgcolor: '#eee' },
                }}
              >
                {label}
              </Button>
            ))}
          </Box>
        </Box>

        {/* 요약 엔진 */}
        <Box
          sx={{
            mt: 2,
            p: 1.5,
            borderRadius: 2,
            bgcolor: '#fafafa',
            border: `1px solid ${LOAN_UI_BORDER}`,
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 700, color: LOAN_UI_MUTED, display: 'block', mb: 1 }}>
            요약 엔진
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.75 }}>
            {(['local', 'openai', 'compare'] as const).map((m) => {
              const sel = insightMode === m;
              const lab = m === 'local' ? 'Local' : m === 'openai' ? 'OpenAI' : '비교';
              return (
                <Button
                  key={m}
                  size="small"
                  variant={sel ? 'contained' : 'outlined'}
                  onClick={() => setInsightMode(m)}
                  sx={{
                    textTransform: 'none',
                    width: '100%',
                    bgcolor: sel ? LOAN_UI_GREEN : 'transparent',
                    borderColor: LOAN_UI_BORDER,
                    color: sel ? '#fff' : LOAN_UI_MUTED,
                    boxShadow: 'none',
                    '&:hover': {
                      bgcolor: sel ? LOAN_UI_GREEN : '#f0f0f0',
                      boxShadow: 'none',
                    },
                  }}
                >
                  {lab}
                </Button>
              );
            })}
          </Box>
        </Box>

        {/* 초기화 · 계산하기 */}
        <Box sx={{ display: 'flex', gap: 1.5, mt: 3, alignItems: 'stretch' }}>
          <Button
            type="button"
            variant="outlined"
            startIcon={<RestartAltIcon />}
            onClick={handleReset}
            disabled={insightLoading}
            sx={{
              flex: '0 0 38%',
              maxWidth: 160,
              py: 1.35,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 600,
              borderColor: LOAN_UI_BORDER,
              color: LOAN_UI_MUTED,
              bgcolor: '#fff',
            }}
          >
            초기화
          </Button>
          <Button
            type="button"
            variant="contained"
            disableElevation
            onClick={() => void handleSubmit()}
            disabled={insightLoading}
            sx={{
              flex: 1,
              py: 1.35,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 700,
              fontSize: '1rem',
              bgcolor: LOAN_UI_GREEN,
              '&:hover': { bgcolor: '#009653' },
            }}
          >
            {insightLoading ? (
              <CircularProgress size={22} sx={{ color: '#fff' }} />
            ) : (
              '알아보기'
            )}
          </Button>
        </Box>

        <Snackbar
          open={formAlert !== null}
          autoHideDuration={2500}
          onClose={() => setFormAlert(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={() => setFormAlert(null)} severity="warning" sx={{ width: '100%' }}>
            {formAlert}
          </Alert>
        </Snackbar>
      </CardContent>
    </Card>
  );
};

export default UserProfile;
