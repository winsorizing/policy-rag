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

const App: React.FC = () => {
  const [insightLoading, setInsightLoading] = useState(false);
  const [insight, setInsight] = useState<PolicyResponse | null>(null);
  const [loanResult, setLoanResult] = useState<LoanResultDisplay | null>(null);
  const [localRag, setLocalRag] = useState<LocalRagBundle | null>(null);
  const [engineFirstLayout, setEngineFirstLayout] = useState(false);
  const [insightError, setInsightError] = useState<string | null>(null);
  const [showSaveAlert, setShowSaveAlert] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
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
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
            minHeight: { xs: 56, sm: 64 },
          }}
        >
          <Box
            sx={{
              flex: '0 1 auto',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-start',
              columnGap: 0,
              rowGap: 0.25,
              minWidth: 0,
              zIndex: 1,
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
                flex: '0 1 auto',
                minWidth: 0,
                maxWidth: { xs: 200, sm: 240, md: 280 },
                whiteSpace: 'normal',
                overflowWrap: 'anywhere',
                wordBreak: 'break-word',
                lineHeight: 1.35,
              }}
            >
              최근 업데이트({rulesMergeUpdateLabel ?? '-'})
            </Typography>
          </Box>
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 1,
              minWidth: 0,
              zIndex: 1,
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
          <Typography
            variant="h6"
            component="div"
            sx={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              transform: 'translate(-50%, -50%)',
              fontWeight: 700,
              px: 1,
              textAlign: 'center',
              whiteSpace: 'nowrap',
              maxWidth: { xs: 'min(92vw, 280px)', sm: '50vw' },
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              pointerEvents: 'none',
              zIndex: 2,
            }}
          >
            🏠 AI 부동산 대출 컨설턴트
          </Typography>
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
              <Typography
                variant="body2"
                sx={{
                  fontWeight: 600,
                  color: 'common.white',
                  flex: 1,
                  letterSpacing: '0.01em',
                  animation: 'refreshBusyPulse 1.35s ease-in-out infinite',
                  '@keyframes refreshBusyPulse': {
                    '0%, 100%': { opacity: 0.75 },
                    '50%': { opacity: 1 },
                  },
                }}
              >
                데이터 최신화 진행 중 — 규제 크롤·병합·벡터 DB
              </Typography>
            </Box>
            <LinearProgress
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
            데이터 출처: 국토교통부, 금융위원회 | 최종 업데이트: 2024.04
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