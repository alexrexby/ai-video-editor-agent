import React from 'react';
import { AbsoluteFill, OffthreadVideo, staticFile } from 'remotion';
import { CaptionsOverlay } from './CaptionsOverlay';

export const CaptionsVideo = ({ videoSrc, captions = [], stylePreset = 'gold' }) => {
  const resolvedSrc = videoSrc ? (videoSrc.startsWith('http') ? videoSrc : staticFile(videoSrc)) : null;

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      {resolvedSrc ? (
        <OffthreadVideo
          src={resolvedSrc}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      ) : null}
      <CaptionsOverlay captions={captions} stylePreset={stylePreset} />
    </AbsoluteFill>
  );
};
