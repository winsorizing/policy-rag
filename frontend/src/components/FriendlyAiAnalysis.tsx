import React from 'react';
import { Box, Divider, Stack, Typography } from '@mui/material';

type Block =
  | { kind: 'h2'; text: string }
  | { kind: 'h3'; text: string }
  | { kind: 'p'; text: string };

/** ``##` / `###` 와 구분선 `---` 를 파싱해 블록으로 나눔 */
function parseBlocks(raw: string): Block[] {
  const lines = raw.split('\n');
  const out: Block[] = [];
  let para: string[] = [];

  const flush = () => {
    const t = para.join('\n').trim();
    if (t) out.push({ kind: 'p', text: t });
    para = [];
  };

  for (const line of lines) {
    const s = line.trimEnd();
    if (s.trim() === '---') {
      flush();
      continue;
    }
    const h2 = s.match(/^##\s+(.+)$/);
    const h3 = s.match(/^###\s+(.+)$/);
    if (h2) {
      flush();
      out.push({ kind: 'h2', text: h2[1].trim() });
    } else if (h3) {
      flush();
      out.push({ kind: 'h3', text: h3[1].trim() });
    } else {
      para.push(line);
    }
  }
  flush();
  return out;
}

export interface FriendlyAiAnalysisProps {
  text: string;
}

/**
 * RAG 답변의 마크다운 소제목을 숨기고, 섹션 제목·소제목·본문으로 나눠 표시합니다.
 */
const FriendlyAiAnalysis: React.FC<FriendlyAiAnalysisProps> = ({ text }) => {
  const blocks = parseBlocks(text || '');
  if (!blocks.length) return null;

  let h2Index = 0;

  return (
    <Stack spacing={0}>
      {blocks.map((b, i) => {
        const key = `${b.kind}-${i}-${b.kind === 'p' ? b.text.slice(0, 32) : b.text}`;
        if (b.kind === 'h2') {
          const first = h2Index === 0;
          h2Index += 1;
          return (
            <Box key={key} sx={{ mt: first ? 0 : 2.5, mb: 1 }}>
              {!first ? <Divider sx={{ mb: 1.5 }} /> : null}
              <Typography
                variant="subtitle1"
                component="h3"
                sx={{
                  fontWeight: 700,
                  fontSize: '1.05rem',
                  letterSpacing: '-0.02em',
                  color: 'primary.dark',
                  textAlign: 'left',
                }}
              >
                {b.text}
              </Typography>
            </Box>
          );
        }
        if (b.kind === 'h3') {
          return (
            <Typography
              key={key}
              variant="body2"
              component="h4"
              sx={{
                mt: 2,
                mb: 0.75,
                fontWeight: 700,
                color: 'text.primary',
                textAlign: 'left',
                pl: 0.75,
                borderLeft: 3,
                borderColor: 'primary.light',
              }}
            >
              {b.text}
            </Typography>
          );
        }
        return (
          <Typography
            key={key}
            variant="body2"
            sx={{ whiteSpace: 'pre-line', lineHeight: 1.75, textAlign: 'left', color: 'text.secondary' }}
          >
            {b.text}
          </Typography>
        );
      })}
    </Stack>
  );
};

export default FriendlyAiAnalysis;
