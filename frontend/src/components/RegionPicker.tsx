import React, { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Box,
  Typography,
} from '@mui/material';
import { LOAN_UI_GREEN } from '../constants/loanUi';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import {
  SIDO_LIST,
  formatRegionString,
  splitRegionToParts,
  getSigunguList,
} from '../data/koreaRegions';
import regionSeed from '../data/regionSeed.json';

interface RegionPickerProps {
  value: string;
  onChange: (region: string) => void;
  /** 문자열 또는 라벨+안내 아이콘 등 */
  label?: ReactNode;
  accentColor?: string;
}

interface RegionApiItem {
  region_cd: string;
  locatadd_nm: string;
}

const REGION_API = 'https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList';
const REGION_SEED_MAP = regionSeed as Record<string, string[]>;

function extractRows(payload: unknown): RegionApiItem[] {
  if (!payload || typeof payload !== 'object') return [];
  const root = payload as { StanReginCd?: unknown };
  if (!Array.isArray(root.StanReginCd)) return [];
  const block = root.StanReginCd.find(
    (x) => x && typeof x === 'object' && Array.isArray((x as { row?: unknown[] }).row)
  ) as { row?: unknown[] } | undefined;
  if (!block?.row) return [];
  return block.row.filter(
    (x): x is RegionApiItem =>
      !!x &&
      typeof x === 'object' &&
      typeof (x as { region_cd?: unknown }).region_cd === 'string' &&
      typeof (x as { locatadd_nm?: unknown }).locatadd_nm === 'string'
  );
}

function stripSidoPrefix(name: string, sidoName: string): string {
  const p = `${sidoName} `;
  return name.startsWith(p) ? name.slice(p.length) : name;
}

/**
 * data.go.kr 키가 URL-encoded 형태로 입력되는 경우가 많아 1회 decode 후 사용.
 * (decode 실패 시 원본 사용)
 */
function normalizeServiceKey(raw: string): string {
  try {
    const decoded = decodeURIComponent(raw);
    return decoded || raw;
  } catch {
    return raw;
  }
}

const RegionPicker: React.FC<RegionPickerProps> = ({
  value,
  onChange,
  label = '대상주택지역',
  accentColor = LOAN_UI_GREEN,
}) => {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const [sido, setSido] = useState(() => splitRegionToParts(value).sido);
  const [sigungu, setSigungu] = useState(() => splitRegionToParts(value).sigungu);
  const [apiSigunguBySido, setApiSigunguBySido] = useState<Record<string, string[]>>(REGION_SEED_MAP);
  const [apiEnabled, setApiEnabled] = useState(false);

  useEffect(() => {
    const p = splitRegionToParts(value);
    setSido(p.sido);
    setSigungu(p.sigungu);
  }, [value]);

  useEffect(() => {
    const rawKey = import.meta.env.VITE_DATA_GO_KR_SERVICE_KEY as string | undefined;
    setApiEnabled(Boolean(rawKey));
  }, []);

  const sidoOptions: string[] = [...SIDO_LIST].filter((x) => x !== '전체');
  
  useEffect(() => {
    if (!apiEnabled) return;
    const rawKey = import.meta.env.VITE_DATA_GO_KR_SERVICE_KEY as string | undefined;
    if (!rawKey) return;
    const serviceKey = normalizeServiceKey(rawKey);

    const targets = sidoOptions.filter((s) => s !== '기타');

    const fetchOne = async (sidoName: string): Promise<[string, string[]]> => {
      try {
        const params = new URLSearchParams({
          serviceKey,
          pageNo: '1',
          numOfRows: '500',
          type: 'json',
          _type: 'json',
          locatadd_nm: sidoName,
        });
        const res = await fetch(`${REGION_API}?${params.toString()}`);
        if (!res.ok) throw new Error(`region api status ${res.status}`);
        const rows = extractRows(await res.json()).filter((item) => {
          return (
            item.locatadd_nm.startsWith(`${sidoName} `) &&
            !item.region_cd.endsWith('00000000') &&
            item.region_cd.endsWith('00000')
          );
        });
        return [sidoName, rows.map((x) => stripSidoPrefix(x.locatadd_nm, sidoName))];
      } catch (e) {
        console.error(`[RegionPicker] preload sigungu failed (${sidoName}):`, e);
        return [sidoName, []];
      }
    };

    const preloadAll = async () => {
      const entries = await Promise.all(targets.map((s) => fetchOne(s)));
      setApiSigunguBySido((prev) => {
        const next = { ...prev };
        for (const [k, v] of entries) {
          const uniq = Array.from(new Set(v.filter((x) => x && x.trim())));
          if (uniq.length > 0) {
            next[k] = ['전체', ...uniq];
          }
        }
        return next;
      });
    };

    void preloadAll();
  }, [apiEnabled]);

  const sigunguOptions: string[] = (() => {
    const cached = apiSigunguBySido[sido];
    if (cached && cached.length) {
      return cached[0] === '전체' ? cached : ['전체', ...cached];
    }
    return [...getSigunguList(sido)];
  })();

  useEffect(() => {
    if (!sigunguOptions.includes(sigungu)) {
      setSigungu(sigunguOptions[0] ?? '전체');
    }
  }, [sigunguOptions, sigungu]);

  const displayText = value.trim();

  const emitChange = (nextSido: string, nextSigungu: string) => {
    const next = formatRegionString(nextSido, nextSigungu);
    onChange(next);
  };

  const handlePickSido = (next: string) => {
    setSido(next);
    const nextGu = '전체';
    setSigungu(nextGu);
    emitChange(next, nextGu);
  };

  const handlePickSigungu = (next: string) => {
    setSigungu(next);
    emitChange(sido, next);
  };

  return (
    <Box sx={{ width: '100%', mt: 0, mb: 0 }}>
      <Box
        component="label"
        id="region-picker-label"
        sx={{
          display: 'flex',
          alignItems: 'center',
          mb: 1,
          '& .MuiTypography-root': { fontWeight: 700, fontSize: '0.95rem', color: 'text.primary' },
        }}
      >
        {typeof label === 'string' ? (
          <Typography component="span">{label}</Typography>
        ) : (
          label
        )}
      </Box>

      <Box
        component="button"
        type="button"
        aria-labelledby="region-picker-label"
        aria-expanded={open}
        onClick={(e) => setAnchorEl(anchorEl ? null : e.currentTarget)}
        sx={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 0.5,
          py: 1.35,
          px: 0,
          border: 'none',
          borderBottom: `2px solid ${accentColor}`,
          bgcolor: 'transparent',
          cursor: 'pointer',
          font: 'inherit',
          textAlign: 'right',
        }}
      >
        <Typography
          sx={{
            color: displayText ? accentColor : 'text.disabled',
            fontSize: '0.95rem',
            fontWeight: displayText ? 600 : 400,
          }}
        >
          {displayText || '지역 선택'}
        </Typography>
        {open ? (
          <ExpandLessIcon sx={{ fontSize: 22, color: accentColor }} />
        ) : (
          <ExpandMoreIcon sx={{ fontSize: 22, color: 'text.secondary' }} />
        )}
      </Box>

      {open ? (
        <Box
          sx={{
            mt: 1.5,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            overflow: 'hidden',
            bgcolor: '#fff',
          }}
        >
          <Box sx={{ display: 'flex', maxHeight: 320 }}>
            <Box
              sx={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                borderRight: '1px solid',
                borderColor: 'divider',
                minWidth: 0,
              }}
            >
              <Box
                sx={{
                  py: 1.35,
                  px: 0.5,
                  textAlign: 'center',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  color: '#4b5563',
                  bgcolor: '#fff',
                  borderBottom: '1px solid',
                  borderColor: 'divider',
                }}
              >
                시/도
              </Box>
              <Box sx={{ overflowY: 'auto', maxHeight: 260 }}>
                {sidoOptions.map((name) => {
                  const sel = sido === name;
                  return (
                    <Box
                      key={name}
                      component="button"
                      type="button"
                      onClick={() => handlePickSido(name)}
                      sx={{
                        width: '100%',
                        py: 1.5,
                        px: 2.25,
                        border: 'none',
                        borderBottom: '1px solid',
                        borderColor: '#f1f1f1',
                        cursor: 'pointer',
                        font: 'inherit',
                        fontSize: '0.98rem',
                        textAlign: 'left',
                        bgcolor: sel ? 'grey.200' : 'background.paper',
                        color: sel ? 'text.primary' : 'primary.main',
                        fontWeight: sel ? 700 : 400,
                        '&:hover': { bgcolor: sel ? 'grey.200' : 'action.hover' },
                      }}
                    >
                      {name}
                    </Box>
                  );
                })}
              </Box>
            </Box>

            <Box
              sx={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                minWidth: 0,
              }}
            >
              <Box
                sx={{
                  py: 1.35,
                  px: 0.5,
                  textAlign: 'center',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  color: '#4b5563',
                  bgcolor: '#fff',
                  borderBottom: '1px solid',
                  borderColor: 'divider',
                }}
              >
                시/군/구
              </Box>
              <Box sx={{ overflowY: 'auto', maxHeight: 260 }}>
                {sigunguOptions.map((name) => {
                  const sel = sigungu === name;
                  return (
                    <Box
                      key={`${sido}-${name}`}
                      component="button"
                      type="button"
                      onClick={() => {
                        handlePickSigungu(name);
                        setAnchorEl(null);
                      }}
                      sx={{
                        width: '100%',
                        py: 1.5,
                        px: 2.25,
                        border: 'none',
                        borderBottom: '1px solid',
                        borderColor: '#f1f1f1',
                        cursor: 'pointer',
                        font: 'inherit',
                        fontSize: '0.98rem',
                        textAlign: 'left',
                        bgcolor: sel ? 'grey.200' : 'background.paper',
                        color: sel ? 'text.primary' : 'primary.main',
                        fontWeight: sel ? 700 : 400,
                        '&:hover': { bgcolor: sel ? 'grey.200' : 'action.hover' },
                      }}
                    >
                      {name}
                    </Box>
                  );
                })}
              </Box>
            </Box>
          </Box>
        </Box>
      ) : null}
    </Box>
  );
};

export default RegionPicker;
