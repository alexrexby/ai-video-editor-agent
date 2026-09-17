import React, { useMemo } from 'react';
import {
  AbsoluteFill,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

// Strip punctuation marks for subtitle display (editorial luxury style like reference)
// Strips dots, commas, exclamation/question marks, quotes, colons, semicolons, brackets, dashes.
// Preserves '%' in numbers (e.g. 100%) and intra-word hyphens (e.g. чек-лист).
const stripPunctuation = (str) => {
  if (!str) return '';
  return str
    .replace(/[.,!?:;«»"'`~()[\]{}]/g, '')
    .replace(/^-+|-+$/g, '')
    .replace(/^—+|—+$/g, '')
    .trim();
};

const HELPER_WORDS = new Set([
  'для', 'них', 'в', 'во', 'на', 'у', 'к', 'ко', 'с', 'со', 'из', 'изо', 'о', 'об', 'обо',
  'по', 'под', 'за', 'от', 'ото', 'до', 'без', 'при', 'про', 'через', 'над',
  'вас', 'нас', 'них', 'их', 'его', 'ее', 'её', 'им', 'вам', 'нам', 'меня', 'тебя',
  'всех', 'всем', 'все', 'всё', 'то', 'же', 'ли', 'бы'
]);

const HELPER_PREPOSITIONS = new Set([
  'до', 'в', 'во', 'на', 'у', 'к', 'ко', 'с', 'со', 'из', 'изо', 'о', 'об', 'обо',
  'по', 'под', 'за', 'от', 'ото', 'без', 'при', 'про', 'через', 'над'
]);

const isAccentWord = (word, token) => {
  if (token?.isAccent) return true;
  if (!word) return false;
  const w = word.toLowerCase().trim();
  // Numbers, %, multipliers, currencies
  if (/(\d+|%|\$|€|₽|руб|тыс|млн|млрд|х\d+|x\d+)/i.test(w)) return true;
  // High-impact emotional and business keywords in Russian
  const keywords = [
    'деньги', 'денег', 'деньгам', 'выручк', 'прибыл', 'результат', 'секрет', 'систем',
    'ошибк', 'клиент', 'мастер', 'продаж', 'масштаб', 'миллион', 'миллиард', 'гаранти', 'быстро',
    'сразу', 'точно', 'чек-лист', 'важно', 'внимани', 'правил', 'главн', 'никогда',
    'всегда', 'перв', 'топ', 'суть', 'баз', 'практикум', 'курс', 'интенсив',
    'подар', 'бонус', 'инсайт', 'мысл', 'смысл', 'рост', 'структур', 'стратеги',
    'хуже', 'лучше', 'вау', 'классно', 'шок', 'факт', 'правда', 'цел', 'успех', 'провал'
  ];
  return keywords.some((k) => w.startsWith(k) || w.includes(k));
};

export const isTokenAccent = (token) => {
  if (!token) return false;
  if (token.isAccent) return true;
  const rawText = (token.rawText || token.text || '').trim();
  if (
    rawText.includes('✨') ||
    rawText.includes('🔥') ||
    rawText.includes('💯') ||
    rawText.includes('%') ||
    rawText.includes('!')
  ) {
    return true;
  }
  return isAccentWord(rawText, token);
};

export const CaptionPage = ({
  page,
  stylePreset = 'luxury',
  subtitlePlacement = { position: 'top', top: 210, bottom: 440 }
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentTimeMs = (frame / fps) * 1000;
  const absoluteTimeMs = page.startMs + currentTimeMs;

  const placement = page.placement || subtitlePlacement;
  const isTop = (placement?.position || 'top') === 'top';
  const posStyle = isTop
    ? { top: placement?.top ?? 210 }
    : { bottom: placement?.bottom ?? 440 };

  const isLuxury = stylePreset === 'luxury' || stylePreset === 'old_money';

  // Compute lines ensuring accent phrase is strictly placed on a new line
  const lines = useMemo(() => {
    const tokens = page.tokens;
    if (!tokens || tokens.length === 0) return [];

    let firstAccentIdx = tokens.findIndex((t) => isTokenAccent(t));

    // Case 1: No accent in this card - balance length into 1 or 2 lines
    if (firstAccentIdx === -1) {
      const totalChars = tokens.reduce((acc, t) => acc + stripPunctuation(t.text || '').length, 0);
      if (totalChars <= 18 || tokens.length <= 3) {
        return [{ tokens, isAccentLine: false }];
      }
      let bestIdx = Math.ceil(tokens.length / 2);
      let minDiff = Infinity;
      let runningChars = 0;
      const halfChars = totalChars / 2;
      for (let i = 0; i < tokens.length - 1; i++) {
        runningChars += stripPunctuation(tokens[i].text || '').length;
        const diff = Math.abs(runningChars - halfChars);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i + 1;
        }
      }
      return [
        { tokens: tokens.slice(0, bestIdx), isAccentLine: false },
        { tokens: tokens.slice(bestIdx), isAccentLine: false },
      ];
    }

    // Case 2: Accent exists!
    // If preceded by a helper preposition (e.g. 'до 50%', 'в бизнесе'), attach preposition to accent phrase
    if (firstAccentIdx > 1) {
      const prevClean = stripPunctuation(tokens[firstAccentIdx - 1].text || '').toLowerCase();
      if (HELPER_PREPOSITIONS.has(prevClean)) {
        firstAccentIdx -= 1;
      }
    }

    // If accent phrase starts after index 0:
    // Pre-tokens go on preceding line(s), accent tokens go on the NEW line!
    if (firstAccentIdx > 0) {
      const preTokens = tokens.slice(0, firstAccentIdx);
      const postTokens = tokens.slice(firstAccentIdx);

      const preChars = preTokens.reduce((acc, t) => acc + stripPunctuation(t.text || '').length, 0);
      const resLines = [];
      if (preChars > 26 && preTokens.length >= 4) {
        const mid = Math.ceil(preTokens.length / 2);
        resLines.push({ tokens: preTokens.slice(0, mid), isAccentLine: false });
        resLines.push({ tokens: preTokens.slice(mid), isAccentLine: false });
      } else {
        resLines.push({ tokens: preTokens, isAccentLine: false });
      }

      // Accent phrase strictly on a new line!
      resLines.push({ tokens: postTokens, isAccentLine: true });
      return resLines;
    }

    // If accent starts at index 0 (starts with accent):
    // e.g. 'Завтра у вас' or 'главный секрет в простой системе'
    let accentEndIdx = 1;
    while (accentEndIdx < tokens.length) {
      const t = tokens[accentEndIdx];
      const clean = stripPunctuation(t.text || '').toLowerCase();
      if (isTokenAccent(t) || HELPER_WORDS.has(clean)) {
        accentEndIdx++;
      } else {
        break;
      }
    }

    // Entire card is accent:
    if (accentEndIdx === tokens.length) {
      const totalChars = tokens.reduce((acc, t) => acc + stripPunctuation(t.text || '').length, 0);
      if (totalChars <= 22 || tokens.length <= 3) {
        return [{ tokens, isAccentLine: true }];
      }
      const mid = Math.ceil(tokens.length / 2);
      return [
        { tokens: tokens.slice(0, mid), isAccentLine: true },
        { tokens: tokens.slice(mid), isAccentLine: true },
      ];
    }

    // Accent phrase at start, then regular words:
    return [
      { tokens: tokens.slice(0, accentEndIdx), isAccentLine: true },
      { tokens: tokens.slice(accentEndIdx), isAccentLine: false },
    ];
  }, [page.tokens]);

  const renderToken = (token, tokenIndex, lineKey, isAccentLine) => {
    const isSpoken = token.toMs <= absoluteTimeMs;
    const isActive = token.fromMs <= absoluteTimeMs && token.toMs > absoluteTimeMs;

    const rawText = (token.text || '').trim();
    const cleanText = stripPunctuation(rawText);
    const displayText = isLuxury ? cleanText.toLowerCase() : cleanText;

    const isAccent = isLuxury && (isAccentLine || isTokenAccent(token));

    let highlightColor = '#FFF066';
    if (stylePreset === 'neon') {
      highlightColor = '#39FF14';
    } else if (isLuxury) {
      highlightColor = '#FFF066'; // Soft luxury butter yellow matching reference
    }

    // Editorial Luxury Style:
    // Normal: Montserrat, white #FFFFFF, 44px
    // Accent: Cormorant Garamond, butter yellow #FFF066, italic 700, 54px
    const luxuryStyle = {
      fontFamily: isAccent
        ? "'Cormorant Garamond', 'Georgia', serif"
        : "'Montserrat', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      fontSize: isAccent ? 54 : 44,
      fontWeight: isAccent ? 700 : 500,
      fontStyle: isAccent ? 'italic' : 'normal',
      textTransform: 'none',
      letterSpacing: isAccent ? '0.8px' : '0.4px',
      lineHeight: 1.22,
      margin: isAccent ? '0 5px' : '0 4px',
      color: isAccent ? '#FFF066' : '#FFFFFF',
      opacity: isAccent ? 1.0 : (isSpoken || isActive ? 1.0 : 0.6),
      display: 'inline-block',
      WebkitTextStroke: 'none',
      transition: 'opacity 0.08s ease, color 0.08s ease',
      textShadow: isAccent
        ? '0 0 16px rgba(255, 240, 102, 0.45), 0 2px 8px rgba(0, 0, 0, 0.9)'
        : (isActive
          ? '0 2px 14px rgba(255, 255, 255, 0.45), 0 2px 8px rgba(0, 0, 0, 0.85)'
          : '0 2px 8px rgba(0, 0, 0, 0.8), 0 1px 3px rgba(0, 0, 0, 0.9)'),
    };

    const classicStyle = {
      fontFamily: "'Montserrat', sans-serif",
      fontSize: 50,
      fontWeight: 900,
      textTransform: 'uppercase',
      letterSpacing: '1.2px',
      margin: '0 6px',
      color: isActive ? highlightColor : '#FFFFFF',
      display: 'inline-block',
      WebkitTextStroke: '6px #000000',
      paintOrder: 'stroke fill',
      transition: 'color 0.04s ease',
      textShadow: isActive
        ? '0 0 24px rgba(255, 240, 102, 0.9), 0 4px 18px rgba(0, 0, 0, 0.95)'
        : '0 4px 18px rgba(0, 0, 0, 0.95)',
    };

    return (
      <span
        key={`${lineKey}-${token.fromMs}-${tokenIndex}`}
        style={isLuxury ? luxuryStyle : classicStyle}
      >
        {displayText}
      </span>
    );
  };

  return (
    <div
      style={{
        position: 'absolute',
        ...posStyle,
        left: 0,
        right: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 40px',
        pointerEvents: 'none',
      }}
    >
      {lines.map((lineObj, lineIndex) => (
        <div
          key={`line-${lineIndex}`}
          style={{
            display: 'flex',
            flexDirection: 'row',
            flexWrap: 'nowrap',
            justifyContent: 'center',
            alignItems: 'center',
            textAlign: 'center',
            lineHeight: 1.22,
            marginTop: lineIndex > 0 ? '6px' : 0,
          }}
        >
          {lineObj.tokens.map((token, tokenIndex) =>
            renderToken(token, tokenIndex, `l${lineIndex}`, lineObj.isAccentLine)
          )}
        </div>
      ))}
    </div>
  );
};

export const CalloutBadge = ({ callout }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({
    frame,
    fps,
    config: {
      damping: 11,
      stiffness: 220,
      mass: 0.5,
    },
  });

  const isAlert = callout.type === 'alert' || callout.style === 'alert';
  const bgGradient = isAlert
    ? 'linear-gradient(135deg, rgba(230, 40, 40, 0.94), rgba(20, 20, 20, 0.96))'
    : 'linear-gradient(135deg, rgba(26, 68, 255, 0.94), rgba(15, 23, 42, 0.96))';

  const borderColor = isAlert
    ? 'rgba(255, 120, 120, 0.85)'
    : 'rgba(255, 240, 102, 0.9)';

  const isTop = (callout.placement?.position || 'top') === 'top';
  const topPos = isTop ? (callout.placement?.top ?? 210) : undefined;
  const bottomPos = !isTop ? (callout.placement?.bottom ?? 440) : undefined;

  return (
    <div
      style={{
        position: 'absolute',
        ...(isTop ? { top: topPos } : { bottom: bottomPos }),
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 40px',
        transform: `scale(${pop})`,
        transformOrigin: 'center center',
      }}
    >
      <div
        style={{
          background: bgGradient,
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: `2px solid ${borderColor}`,
          borderRadius: 24,
          padding: '18px 42px',
          boxShadow: '0 16px 48px rgba(0, 0, 0, 0.7), 0 0 30px rgba(26, 68, 255, 0.4)',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 16,
          maxWidth: '880px',
        }}
      >
        {callout.icon && (
          <span style={{ fontSize: 46, lineHeight: 1 }}>{callout.icon}</span>
        )}
        <span
          style={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 40,
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '1.2px',
            color: '#FFFFFF',
            textShadow: '0 2px 10px rgba(0,0,0,0.8)',
          }}
        >
          {callout.text}
        </span>
      </div>
    </div>
  );
};

export const CaptionsOverlay = ({
  captions = [],
  callouts = [],
  stylePreset = 'luxury',
  subtitlePlacement = { position: 'top', top: 210, bottom: 440 }
}) => {
  const { fps } = useVideoConfig();

  const pages = useMemo(() => {
    if (!captions || captions.length === 0) {
      return [];
    }

    const chunkList = [];
    let cur = [];
    let curChars = 0;

    for (let i = 0; i < captions.length; i++) {
      const token = captions[i];
      cur.push(token);
      const raw = (token.rawText || token.text || '').trim();
      const text = stripPunctuation(raw);
      curChars += text.length + 1;
      const hasPunct = raw.endsWith('.') || raw.endsWith('!') || raw.endsWith('?') || raw.endsWith(',') || raw.endsWith(';') || raw.endsWith(':');
      const durMs = cur.length > 1 ? token.endMs - cur[0].startMs : 0;
      const nextToken = captions[i + 1];
      const gapToNext = nextToken ? (nextToken.startMs - token.endMs) : 0;

      // Split chunk if:
      // - natural speech pause (> 180ms)
      // - punctuation with at least 2 words
      // - max 6 words or >= 30 characters
      // - phrase duration exceeds 2.2s
      const shouldSplit =
        gapToNext >= 180 ||
        (hasPunct && cur.length >= 2) ||
        cur.length >= 6 ||
        (cur.length >= 5 && curChars >= 30) ||
        durMs >= 2200;

      if (shouldSplit) {
        chunkList.push(cur);
        cur = [];
        curChars = 0;
      }
    }
    if (cur.length > 0) {
      chunkList.push(cur);
    }

    return chunkList.map((tokens, idx) => {
      const startMs = tokens[0].startMs;
      const endMs = tokens[tokens.length - 1].endMs;
      const tokensWithRelative = tokens.map((t) => ({
        ...t,
        fromMs: t.startMs,
        toMs: t.endMs,
      }));
      return {
        id: idx,
        startMs,
        endMs,
        durationMs: Math.max(200, endMs - startMs),
        tokens: tokensWithRelative,
        placement: tokens[0]?.placement || null,
      };
    });
  }, [captions]);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@1,600;1,700&family=Montserrat:wght@500;600;700;800;900&display=swap');
      `}</style>
      {/* 1. Word Subtitles */}
      {pages && pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = Math.round((page.startMs / 1000) * fps);
        const rawEndFrame = Math.round((page.endMs / 1000) * fps);
        const nextStartFrame = nextPage ? Math.round((nextPage.startMs / 1000) * fps) : Infinity;
        const endFrame = Math.min(nextStartFrame, Math.max(rawEndFrame + 4, startFrame + 10));
        const durationInFrames = Math.max(1, endFrame - startFrame);

        return (
          <Sequence
            key={`${page.startMs}-${index}`}
            from={startFrame}
            durationInFrames={durationInFrames}
          >
            <CaptionPage
              page={page}
              stylePreset={stylePreset}
              subtitlePlacement={subtitlePlacement}
            />
          </Sequence>
        );
      })}

      {/* 2. Motion Callout Badges */}
      {callouts && callouts.map((callout, cIdx) => {
        const startFrame = Math.round((callout.startMs / 1000) * fps);
        const endFrame = Math.round((callout.endMs / 1000) * fps);
        const durationInFrames = Math.max(15, endFrame - startFrame);

        return (
          <Sequence
            key={`callout-${callout.startMs}-${cIdx}`}
            from={startFrame}
            durationInFrames={durationInFrames}
          >
            <CalloutBadge callout={callout} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
