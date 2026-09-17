import React from 'react';
import { Composition } from 'remotion';
import { CaptionsOverlay } from './CaptionsOverlay';
import { CaptionsVideo } from './CaptionsVideo';

export const Root = () => {
  return (
    <>
      <Composition
        id="CaptionsOverlay"
        component={CaptionsOverlay}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          captions: [],
          callouts: [],
          stylePreset: 'luxury',
          subtitlePlacement: { position: 'top', top: 210, bottom: 440 },
        }}
      />
      <Composition
        id="CaptionsVideo"
        component={CaptionsVideo}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          videoSrc: '',
          captions: [],
          callouts: [],
          stylePreset: 'luxury',
          subtitlePlacement: { position: 'top', top: 210, bottom: 440 },
        }}
      />
    </>
  );
};
