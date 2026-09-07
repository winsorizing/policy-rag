// src/App.tsx
import React, { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Box,
  Typography,
  AppBar,
  Toolbar,
  Alert,
  Snackbar,
  IconButton,
  CircularProgress,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import UserProfile from './components/UserProfile';
import InsightPanel from './components/InsightPanel';
import {
  UserProfile as UserProfileType,
  PolicyResponse,
  LoanResultDisplay,
  LocalRagBundle,
  InsightUpdatePayload,
} from './types';
import { healthCheck, refreshKnowledge, fetchRulesUpdateLog } from './services/api';

const REFRESH_STEPS = [
  '규제지역·DTI/DSR 데이터 크롤링 중...',
  '규칙 파일 병합 중...',
  '벡터 DB 재빌드 중...',
];

const App: React.FC = () => {
  const [insightLoading, setInsightLoading] = useState(false);
  const [insight, setInsight] = useState<PolicyResponse | null>(null);
  const [loanResult, setLoanResult] = useState<LoanResultDisplay | null>(null);
  const [localRag, setLocalRag] = useState<LocalRagBundle | null>(null);
  const [engineFirstLayout, setEngineFirstLayout] = useState(false);
  const [insightError, setInsightError] = useState<string | null>(null);
  const [showSaveAlert, setShowSaveAlert] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshStepIdx, setRefreshStepIdx] = useState(0);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [serverStatus, setServerStatus] = useState<'connected' | 'disconnected'>('disconnected');
  /** ``update_log.json`` 의 ``updateDate`` (없으면 null → UI 에 '-') */
  const [rulesMergeUpdateLabel, setRulesMergeUpdateLabel] = useState<string | null>(
    null
  );
  const syncRulesUpdateLabel = async () => {
    try {
      const { updateDate } = await fetchRulesUpdateLog();
      setRulesMergeUpdateLabel(
        updateDate && updateDate.trim() ? updateDate.trim() : null
      );
    } catch {
      setRulesMergeUpdateLabel(null);
    }
  };

  useEffect(() => {
    void syncRulesUpdateLabel();
  }, []);

  useEffect(() => {
    // 서버 상태 확인
    const checkServer = async () => {
      const status = await healthCheck();
      setServerStatus(status.status === 'healthy' ? 'connected' : 'disconnected');
    };

    checkServer();
    const interval = setInterval(checkServer, 30000); // 30초마다 체크

    return () => clearInterval(interval);
  }, []);

  const handleProfileSave = (_profile: UserProfileType) => {
    setShowSaveAlert(true);
  };

  const handleInsightUpdate = (payload: InsightUpdatePayload) => {
    if (payload.loading) {
      setInsightLoading(true);
      setInsightError(null);
      setInsight(null);
      setLoanResult(null);
      setLocalRag(null);
      setEngineFirstLayout(false);
      return;
    }
    setInsightLoading(false);
    setInsightError(payload.error);
    if (payload.result === null) {
      setInsight(null);
      setLoanResult(null);
      setLocalRag(null);
      setEngineFirstLayout(false);
    } else {
      setInsight(payload.result);
      setLoanResult(payload.loanResult ?? null);
      setLocalRag(payload.localRag ?? null);
      setEngineFirstLayout(payload.engineFirstLayout ?? false);
    }
  };

  const handleRefreshKnowledge = async () => {
    setRefreshStepIdx(0);
    const stepTimer = setInterval(() => {
      setRefreshStepIdx(prev => Math.min(prev + 1, REFRESH_STEPS.length - 1));
    }, 25000);
    try {
      setRefreshing(true);
      const result = await refreshKnowledge();
      const stats = result.stats;
      const rc = stats.rule_crawl;
      const ruleLine =
        rc == null || typeof rc !== 'object' || !('all_ok' in rc)
          ? ''
          : rc.all_ok === false
            ? ` · 규칙크롤/병합 일부 실패`
            : ` · 규칙크롤/병합 OK(update_log 반영)`;
      setRefreshMessage(
        `${result.message} (문서 ${stats.doc_count}개, 청크 ${stats.chunk_count}개${ruleLine})`
      );
      await syncRulesUpdateLabel();
      setInsightError(null);
      setInsight(null);
    } catch (e) {
      setRefreshMessage(e instanceof Error ? e.message : '업데이트 중 오류가 발생했습니다.');
    } finally {
      clearInterval(stepTimer);
      setRefreshing(false);
    }
  };

  return (
    <Box sx={{ flexGrow: 1, minHeight: '100vh', bgcolor: 'grey.50' }}>
      <AppBar position="static" elevation={2} sx={{ flexDirection: 'column', alignItems: 'stretch' }}>
        <Toolbar
          disableGutters
          sx={{
            px: { xs: 1.5, sm: 2 },
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            minHeight: { xs: 56, sm: 64 },
          }}
        >
          {/* 왼쪽: 새로고침 버튼 + 업데이트 날짜 */}
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              minWidth: 0,
            }}
          >
            <Tooltip title="규칙 크롤·merge·벡터 DB 전체 재빌드(매번 전체 실행)">
              <span style={{ display: 'inline-flex', flexShrink: 0 }}>
                <IconButton
                  color="inherit"
                  onClick={() => void handleRefreshKnowledge()}
                  disabled={refreshing}
                  size="small"
                  sx={{ p: 0.5 }}
                >
                  {refreshing ? (
                    <CircularProgress size={18} color="inherit" />
                  ) : (
                    <RefreshIcon />
                  )}
                </IconButton>
              </span>
            </Tooltip>
            <Typography
              variant="body2"
              component="div"
              sx={{
                fontWeight: 600,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              업데이트({rulesMergeUpdateLabel ?? '-'})
            </Typography>
          </Box>

          {/* 가운데: 타이틀 */}
          <Typography
            variant="h6"
            component="div"
            sx={{
              flex: '0 0 auto',
              fontWeight: 700,
              textAlign: 'center',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: { xs: 160, sm: 300 },
            }}
          >
            🏠 AI 부동산 대출 컨설턴트
          </Typography>

          {/* 오른쪽: 서버 상태 */}
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 1,
              minWidth: 0,
            }}
          >
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                flexShrink: 0,
                bgcolor: serverStatus === 'connected' ? 'success.main' : 'error.main',
              }}
            />
            <Typography variant="caption" sx={{ whiteSpace: 'nowrap' }}>
              {serverStatus === 'connected' ? '서버 연결됨' : '서버 연결 끊김'}
            </Typography>
          </Box>
        </Toolbar>
        {refreshing ? (
          <Box
            component="aside"
            aria-busy="true"
            aria-live="polite"
            sx={{
              px: { xs: 1.5, sm: 2 },
              py: 1.25,
              bgcolor: 'rgba(0,0,0,0.14)',
              borderTop: '1px solid rgba(255,255,255,0.12)',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1 }}>
              <CircularProgress size={20} thickness={4} sx={{ color: 'common.white' }} />
              <Box sx={{ flex: 1 }}>
                <Typography
                  variant="caption"
                  sx={{ color: 'rgba(255,255,255,0.7)', display: 'block' }}
                >
                  {refreshStepIdx + 1} / {REFRESH_STEPS.length} 단계
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600,
                    color: 'common.white',
                    letterSpacing: '0.01em',
                    animation: 'refreshBusyPulse 1.35s ease-in-out infinite',
                    '@keyframes refreshBusyPulse': {
                      '0%, 100%': { opacity: 0.75 },
                      '50%': { opacity: 1 },
                    },
                  }}
                >
                  {REFRESH_STEPS[refreshStepIdx]}
                </Typography>
              </Box>
            </Box>
            <LinearProgress
              variant="determinate"
              value={((refreshStepIdx + 1) / REFRESH_STEPS.length) * 100}
              color="inherit"
              sx={{
                height: 4,
                borderRadius: 1,
                bgcolor: 'rgba(255,255,255,0.25)',
                '& .MuiLinearProgress-bar': {
                  borderRadius: 1,
                  bgcolor: 'common.white',
                },
              }}
            />
          </Box>
        ) : null}
      </AppBar>

      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Grid container spacing={3} sx={{ alignItems: 'stretch' }}>
          <Grid size={{ xs: 12, md: 6 }}>
            <UserProfile
              insightLoading={insightLoading}
              onInsightUpdate={handleInsightUpdate}
              onProfileSave={handleProfileSave}
              onRulesDataSynced={syncRulesUpdateLabel}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <InsightPanel
              loading={insightLoading}
              insight={insight}
              loanResult={loanResult}
              localRag={localRag}
              engineFirstLayout={engineFirstLayout}
              error={insightError}
              onDismissError={() => setInsightError(null)}
            />
          </Grid>
        </Grid>

        {/* 푸터 */}
        <Box sx={{ mt: 6, py: 3, textAlign: "center", borderTop: 1, borderColor: "grey.300" }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            ⚠️ 본 서비스는 참고용이며, 최종 대출 조건은 금융기관에 문의하세요.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            데이터 출처: 국토교통부, 금융위원회 | 최종 업데이트: {rulesMergeUpdateLabel ?? '-'}
          </Typography>
        </Box>
      </Container>

      {/* 저장 완료 알림 */}
      <Snackbar
        open={showSaveAlert}
        autoHideDuration={3000}
        onClose={() => setShowSaveAlert(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert onClose={() => setShowSaveAlert(false)} severity="success" sx={{ width: '100%' }}>
          맞춤 정책 요약을 불러왔습니다.
        </Alert>
      </Snackbar>

      <Snackbar
        open={refreshMessage !== null}
        autoHideDuration={5000}
        onClose={() => setRefreshMessage(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => setRefreshMessage(null)}
          severity={refreshMessage?.includes('오류') ? 'error' : 'info'}
          sx={{ width: '100%' }}
        >
          {refreshMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default App;