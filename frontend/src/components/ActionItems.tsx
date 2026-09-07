import React, { useState } from 'react';
import { Box, Paper, Typography, Chip, Button } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import EmojiObjectsIcon from '@mui/icons-material/EmojiObjects';
import type { RagActionItem } from '../types';

export interface ActionItemsProps {
  items: RagActionItem[];
}

type DifficultyKey = '쉬움' | '보통' | '어려움';

function normalizeDifficulty(raw: string): DifficultyKey {
  const t = (raw || '').trim();
  if (t === '쉬움' || t === '보통' || t === '어려움') return t;
  return '보통';
}

const DIFFICULTY_COLOR: Record<DifficultyKey, 'success' | 'warning' | 'error'> = {
  쉬움: 'success',
  보통: 'warning',
  어려움: 'error',
};

const ActionItems: React.FC<ActionItemsProps> = ({ items }) => {
  const [expandedFirst, setExpandedFirst] = useState(false);

  if (!items.length) return null;

  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <EmojiObjectsIcon sx={{ mr: 1, color: '#ffa726' }} />
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            대출 한도 높이는 법
          </Typography>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', pl: 0.25, lineHeight: 1.55, textAlign: 'left' }}>
          AI가 제안한 참고 방법이에요.
        </Typography>
      </Box>

      {items.map((item, idx) => {
        const d = normalizeDifficulty(item.difficulty);
        const rawEffect = (item.effect || '').trim();
        const showEffectChip =
          Boolean(rawEffect) && rawEffect !== '미상';
        const body = item.full_text || '';
        const previewLen = 280;
        const displayBody =
          idx === 0 && !expandedFirst && body.length > previewLen ? `${body.slice(0, previewLen)}…` : body;

        return (
          <Paper
            key={`${item.title}-${idx}`}
            elevation={1}
            sx={{
              p: 2,
              mb: 2,
              border: 1,
              borderColor: 'divider',
              '&:hover': {
                boxShadow: 3,
                borderColor: 'primary.light',
              },
            }}
          >
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 1,
                mb: 1,
                flexWrap: 'wrap',
              }}
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 700, flex: '1 1 200px', textAlign: 'left' }}>
                {idx + 1}. {item.title || '(제목 없음)'}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexShrink: 0 }}>
                <Chip label={d} size="small" color={DIFFICULTY_COLOR[d]} />
                {showEffectChip ? (
                  <Chip
                    label={rawEffect}
                    size="small"
                    icon={<TrendingUpIcon sx={{ '&&': { fontSize: 18 } }} />}
                    color="primary"
                    variant="outlined"
                  />
                ) : null}
              </Box>
            </Box>

            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line', textAlign: 'left' }}>
              {displayBody}
            </Typography>

            {idx === 0 && body.length > previewLen ? (
              <Button
                variant="outlined"
                size="small"
                sx={{ mt: 1 }}
                onClick={() => setExpandedFirst((v) => !v)}
              >
                {expandedFirst ? '접기' : '자세히 보기'}
              </Button>
            ) : null}
          </Paper>
        );
      })}
    </Box>
  );
};

export default ActionItems;
