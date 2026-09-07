import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import type { PolicyResponse, Source, LoanResultDisplay, LocalRagBundle } from '../types';
import { won } from '../utils/formatWon';
import { formatRagSourceText } from '../utils/formatRagSourceText';
import ActionItems from './ActionItems';
import FriendlyAiAnalysis from './FriendlyAiAnalysis';

function pctLabel(n: number): string {
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2).replace(/\.?0+$/, '');
}

export interface LoanResultProps {
  insight: PolicyResponse;
  loan: LoanResultDisplay;
  localRag: LocalRagBundle | null;
  engineFirstLayout: boolean;
}

function pickRagText(
  insight: PolicyResponse,
  localRag: LocalRagBundle | null,
  engineFirstLayout: boolean,
): string {
  const pr = localRag?.explanation?.trim();
  if (pr) return pr;
  if (!engineFirstLayout && insight.answer?.trim()) return insight.answer.trim();
  return '';
}

function pickPolicySources(insight: PolicyResponse, localRag: LocalRagBundle | null): Source[] {
  if (localRag?.sources?.length) return localRag.sources;
  return insight.sources ?? [];
}

function LoanAndPolicySourceBlock() {
  return (
    <Box
      sx={{
        mb: 1.5,
        py: 1.25,
        px: 1.5,
        borderRadius: 1,
        bgcolor: 'grey.50',
        border: 1,
        borderColor: 'divider',
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: 'block', mb: 1 }}>
        데이터 출처
      </Typography>
      <Table
        size="small"
        sx={{
          '& .MuiTableCell-root': {
            verticalAlign: 'top',
            textAlign: 'left',
            borderColor: 'divider',
            color: 'text.secondary',
            fontSize: '0.75rem',
            lineHeight: 1.5,
          },
          '& .MuiTableHead-root .MuiTableCell-root': {
            fontWeight: 700,
            color: 'text.secondary',
            bgcolor: 'action.hover',
          },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: '30%' }}>데이터</TableCell>
            <TableCell>출처</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            <TableCell>규제지역·LTV·정책대출</TableCell>
            <TableCell>
              국토교통부 정책·규제 공개 페이지
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell>DTI·DSR</TableCell>
            <TableCell>
              금융위 가계부채 보도자료(PDF), KB Think LTV·DTI·DSR 가이드
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Box>
  );
}

const LoanResult: React.FC<LoanResultProps> = ({ insight, loan, localRag, engineFirstLayout }) => {
  const ragText = pickRagText(insight, localRag, engineFirstLayout);
  const policySources = pickPolicySources(insight, localRag);
  const actionItems = localRag?.action_items ?? [];

  return (
    <Box sx={{ mt: 0.5 }}>
      <Paper
        elevation={3}
        sx={{
          p: 2.5,
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'common.white',
          mb: 2,
          borderRadius: 2,
        }}
      >
        <Typography variant="subtitle1" sx={{ opacity: 0.95, fontWeight: 600 }} gutterBottom>
          최대 대출 가능 금액
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.02em', mb: 1 }}>
          {loan.max_loan_amount.toLocaleString('ko-KR')}원
        </Typography>
        <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip
            label={`지역: ${loan.region}`}
            size="small"
            sx={{ bgcolor: 'rgba(255,255,255,0.2)', color: 'common.white' }}
          />
          <Chip
            label={`규제: ${loan.regulation_type}`}
            size="small"
            sx={{ bgcolor: 'rgba(255,255,255,0.2)', color: 'common.white' }}
          />
          <Chip
            label={`제한 요인: ${loan.limiting_factor}`}
            size="small"
            sx={{ bgcolor: 'rgba(255,255,255,0.28)', color: 'common.white' }}
          />
        </Box>
      </Paper>

      <LoanAndPolicySourceBlock />

      <Accordion
        defaultExpanded={true}
        disableGutters
        elevation={0}
        sx={{ border: 1, borderColor: 'divider', borderRadius: 1.5, mb: 2, '&:before': { display: 'none' } }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            상세 계산 내역 (LTV·DTI·DSR)
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, textAlign: 'left' }}>
          <Table
            size="small"
            sx={{
              '& .MuiTableCell-root': { verticalAlign: 'top', textAlign: 'left' },
            }}
          >
            <TableHead>
              <TableRow>
                <TableCell align="left">구분</TableCell>
                <TableCell align="left">한도</TableCell>
                <TableCell align="left">실제</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell align="left" sx={{ maxWidth: { xs: 120, sm: 200 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    LTV
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                    담보인정비율
                  </Typography>
                </TableCell>
                <TableCell align="left">{pctLabel(loan.ltv_limit)}%</TableCell>
                <TableCell align="left">{pctLabel(loan.ltv_ratio)}%</TableCell>
              </TableRow>
              <TableRow>
                <TableCell align="left" sx={{ maxWidth: { xs: 120, sm: 200 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    DTI
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                    소득 대비 주택담보대출 원리금 상환비율
                  </Typography>
                </TableCell>
                <TableCell align="left">{pctLabel(loan.dti_limit)}%</TableCell>
                <TableCell align="left">{pctLabel(loan.dti_ratio)}%</TableCell>
              </TableRow>
              <TableRow>
                <TableCell align="left" sx={{ maxWidth: { xs: 120, sm: 200 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    DSR
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                    총부채 원리금상환비율
                  </Typography>
                </TableCell>
                <TableCell align="left">{pctLabel(loan.dsr_limit)}%</TableCell>
                <TableCell align="left">{pctLabel(loan.dsr_ratio)}%</TableCell>
              </TableRow>
            </TableBody>
          </Table>

          <Box
            sx={{
              mt: 2,
              bgcolor: 'grey.50',
              borderRadius: 1,
              border: 1,
              borderColor: 'divider',
              overflow: 'hidden',
            }}
          >
            <Typography
              variant="caption"
              sx={{ fontWeight: 700, display: 'block', px: 2, py: 1, borderBottom: 1, borderColor: 'divider' }}
            >
              금액 요약
            </Typography>
            <Box sx={{ textAlign: 'left' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="left">항목</TableCell>
                    <TableCell align="left">금액</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell align="left">주택 가격</TableCell>
                    <TableCell align="left">{won(loan.house_price)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell align="left">최종 대출가능 금액</TableCell>
                    <TableCell align="left">{won(loan.max_loan_amount)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={2}> 
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                      LTV·DTI·DSR 규정을 각각 적용해 구한 최대 대출 가능 금액(원) 중, 가장 작은 금액이 한도로 정해집니다.
                      </Typography> 
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            
            </Box>
          </Box>
        </AccordionDetails>
      </Accordion>

      {ragText ? (
        <Paper elevation={2} sx={{ p: 2.5, mb: 2, bgcolor: '#f8f9fa', borderRadius: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
            <LightbulbIcon sx={{ mr: 1, color: '#ffa726' }} />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              AI 분석 결과
            </Typography>
          </Box>
          <FriendlyAiAnalysis text={ragText} />
        </Paper>
      ) : null}

      {actionItems.length > 0 ? <ActionItems items={actionItems} /> : null}

      {loan.regulation_type !== '일반지역' && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          <Typography variant="body2">
            규제지역·투기과열 등 구분에 따라 전입 의무·거주 요건 등이 달라질 수 있습니다. 정확한 의무는 최신 고시·금융기관 안내를 확인하세요.
          </Typography>
        </Alert>
      )}

      {policySources.length > 0 ? (
        <Accordion
          sx={{ mt: 1, border: 1, borderColor: 'divider', borderRadius: 1.5, '&:before': { display: 'none' } }}
          disableGutters
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              참고 문서 ({policySources.length}건)
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={1.25}>
              {policySources.map((source, idx) => {
                const plain = formatRagSourceText(source.content);
                return (
                  <Paper key={`${source.metadata.source}-${source.metadata.chunk_index}-${idx}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {(formatRagSourceText(source.metadata.title) || '문서')} · {source.metadata.source}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        mt: 0.75,
                        textAlign: 'left',
                        whiteSpace: 'pre-line',
                        maxHeight: 360,
                        overflow: 'auto',
                      }}
                    >
                      {plain}
                    </Typography>
                  </Paper>
                );
              })}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ) : null}
    </Box>
  );
};

export default LoanResult;
