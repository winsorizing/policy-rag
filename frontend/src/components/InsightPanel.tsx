import React, { useEffect, useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Alert,
  Divider,
  List,
  ListItem,
  ListItemText,
  Chip,
} from '@mui/material';
import ArticleOutlinedIcon from '@mui/icons-material/ArticleOutlined';
import type { PolicyResponse, Source, LoanResultDisplay, LocalRagBundle } from '../types';
import LoanResult from './LoanResult';
import { LOAN_UI_BORDER, LOAN_UI_GREEN, LOAN_UI_MUTED } from '../constants/loanUi';
import { formatRagSourceText } from '../utils/formatRagSourceText';

const AI_LOADING_STEPS = [
  '데이터 조회 중…',
  '대출 한도 계산 중(Rule Engine)…',
  '정책 문서 검색·설명 생성 중(RAG+LLM)…',
] as const;

export interface InsightPanelProps {
  loading: boolean;
  insight: PolicyResponse | null;
  loanResult: LoanResultDisplay | null;
  localRag: LocalRagBundle | null;
  engineFirstLayout: boolean;
  error: string | null;
  onDismissError?: () => void;
}

function SourcesList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <>
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        참고 출처 ({sources.length}건)
      </Typography>
      <List dense disablePadding>
        {sources.map((s, i) => (
          <ListItem
            key={`${s.metadata.source}-${s.metadata.chunk_index}-${i}`}
            alignItems="flex-start"
            sx={{
              px: 0,
              py: 1,
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
            <ListItemText
              primary={formatRagSourceText(s.metadata.title) || '문서'}
              secondary={
                <Box component="span" sx={{ display: 'block' }}>
                  <Typography component="span" variant="caption" sx={{ display: 'block' }}>
                    {s.metadata.source} · {s.metadata.date}
                  </Typography>
                  <Typography
                    component="span"
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', mt: 0.5, whiteSpace: 'pre-line' }}
                  >
                    {formatRagSourceText(s.content)}
                  </Typography>
                </Box>
              }
            />
          </ListItem>
        ))}
      </List>
    </>
  );
}

const InsightPanel: React.FC<InsightPanelProps> = ({
  loading,
  insight,
  loanResult,
  localRag,
  engineFirstLayout,
  error,
  onDismissError,
}) => {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!loading) {
      setStepIndex(0);
      return;
    }
    const t = window.setInterval(() => {
      setStepIndex((prev) => (prev + 1) % AI_LOADING_STEPS.length);
    }, 900);
    return () => window.clearInterval(t);
  }, [loading]);

  return (
    <Card
      sx={{
        height: '100%',
        minHeight: 420,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <CardContent sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 1,
            mb: 2,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <ArticleOutlinedIcon sx={{ mr: 1, color: 'secondary.main' }} />
            <Typography variant="h6" sx={{ color: 'secondary.main' }}>
              {engineFirstLayout ? '대출 계산 & 정책 설명' : '맞춤 정책 요약'}
            </Typography>
          </Box>
          {insight && insight.llm_model && insight.mode !== 'compare' && (
            <Chip
              size="small"
              label={
                engineFirstLayout && insight.mode === 'local'
                  ? `Ollama · ${insight.llm_model}`
                  : insight.mode === 'openai'
                    ? `OpenAI · ${insight.llm_model}`
                    : `Local · ${insight.llm_model}`
              }
              color={insight.mode === 'openai' ? 'secondary' : 'primary'}
              variant="outlined"
            />
          )}
        </Box>

        {loading && (
          <Box
            sx={{
              flex: 1,
              px: 1.5,
              py: 4,
              display: 'flex',
              flexDirection: 'column',
              gap: 0.25,
              borderRadius: 1.5,
              border: `1px solid ${LOAN_UI_BORDER}`,
              bgcolor: '#fbfffc',
            }}
          >
            {AI_LOADING_STEPS.map((txt, idx) => {
              const active = idx <= stepIndex;
              const isCurrent = idx === stepIndex;
              return (
                <Box
                  key={txt}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.75,
                    py: 0.35,
                    color: active ? LOAN_UI_GREEN : LOAN_UI_MUTED,
                    opacity: active ? 1 : 0.45,
                    fontWeight: isCurrent ? 700 : 500,
                    transform: isCurrent ? 'translateX(1px)' : 'none',
                    transition: 'all 0.2s ease',
                    animation: isCurrent ? 'pulseAiStep 1s ease-in-out infinite' : 'none',
                    '@keyframes pulseAiStep': {
                      '0%': { opacity: 0.7 },
                      '50%': { opacity: 1 },
                      '100%': { opacity: 0.7 },
                    },
                  }}
                >
                  <Typography sx={{ fontSize: '0.95rem', fontWeight: 'inherit' }}>
                    {`✔ ${txt}`}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        )}

        {!loading && error && (
          <Alert severity="error" onClose={onDismissError} sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}

        {!loading && !error && !insight && (
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 1,
              borderColor: 'grey.200',
              borderRadius: 1,
              bgcolor: 'grey.50',
              p: 3,
              textAlign: 'center',
            }}
          >
            <Typography variant="body2" color="text.secondary">
              왼쪽에서 조건을 입력한 뒤 <strong>알아보기</strong>를 누르면
              <br />
              <strong>Rule 엔진</strong> 계산과 <strong>정책 문서 RAG</strong> 설명이 함께 표시됩니다.
            </Typography>
          </Box>
        )}

        {!loading && !error && insight && (
          <Box sx={{ flex: 1, overflow: 'auto' }}>
            {engineFirstLayout ? (
              <>
                <Box
                  sx={{
                    borderRadius: 1.5,
                    border: `2px solid ${LOAN_UI_BORDER}`,
                    bgcolor: '#fbfffc',
                    overflow: 'hidden',
                  }}
                >
                  <Box
                    sx={{
                      px: 2,
                      py: 1.25,
                      borderBottom: `1px solid ${LOAN_UI_BORDER}`,
                      bgcolor: 'grey.50',
                    }}
                  >
                    <Typography sx={{ fontWeight: 900, letterSpacing: 0.02 }}>
                      계산기(Rule 엔진)
                    </Typography>
                  </Box>
                  <Box sx={{ px: 2, py: 1.5 }}>
                    {loanResult ? (
                      <>
                        <LoanResult
                          insight={insight}
                          loan={loanResult}
                          localRag={localRag}
                          engineFirstLayout={engineFirstLayout}
                        />
                        {insight.answer ? (
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              mt: 2,
                              pt: 2,
                              borderTop: 1,
                              borderColor: 'divider',
                              textAlign: 'left',
                              color: 'text.secondary',
                            }}
                          >
                            {insight.answer}
                          </Typography>
                        ) : null}
                      </>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        계산 결과가 없습니다. 조건을 입력한 뒤 다시 시도해 주세요.
                      </Typography>
                    )}
                  </Box>
                </Box>
              </>
            ) : insight.mode === 'compare' &&
              (insight.local_answer !== undefined || insight.openai_answer !== undefined) ? (
              <>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Typography variant="subtitle2" color="primary">
                    Local (Ollama)
                  </Typography>
                  {insight.local_llm_model && (
                    <Chip size="small" label={insight.local_llm_model} variant="outlined" color="primary" />
                  )}
                </Box>
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: 'pre-wrap', mb: 3, textAlign: 'left' }}
                >
                  {insight.local_answer ?? '(없음)'}
                </Typography>
                <Divider sx={{ my: 2 }} />
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                  <Typography variant="subtitle2" color="secondary">
                    OpenAI (ChatOpenAI)
                  </Typography>
                  {insight.openai_llm_model && (
                    <Chip size="small" label={insight.openai_llm_model} variant="outlined" color="secondary" />
                  )}
                </Box>
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: 'pre-wrap', mb: 2, textAlign: 'left' }}
                >
                  {insight.openai_answer ?? '(없음)'}
                </Typography>
                {loanResult ? (
                  <>
                    <Divider sx={{ my: 2 }} />
                    <LoanResult
                      insight={insight}
                      loan={loanResult}
                      localRag={localRag}
                      engineFirstLayout={engineFirstLayout}
                    />
                  </>
                ) : null}
                {!loanResult ? <SourcesList sources={insight.sources} /> : null}
              </>
            ) : (
              <>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mb: 2, textAlign: 'left' }}>
                  {insight.answer}
                </Typography>
                {loanResult ? (
                  <>
                    <Divider sx={{ my: 2 }} />
                    <LoanResult
                      insight={insight}
                      loan={loanResult}
                      localRag={localRag}
                      engineFirstLayout={engineFirstLayout}
                    />
                  </>
                ) : null}
                {!loanResult ? <SourcesList sources={insight.sources} /> : null}
              </>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default InsightPanel;
