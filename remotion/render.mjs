import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { bundle } from '@remotion/bundler';
import { renderMedia, renderFrames, selectComposition } from '@remotion/renderer';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Parse CLI args: --props <path> (--frames <dir> | --output <path>)
const args = process.argv.slice(2);
let propsPath = null;
let outputPath = null;
let framesDir = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--props' && args[i + 1]) {
    propsPath = args[i + 1];
    i++;
  } else if (args[i] === '--output' && args[i + 1]) {
    outputPath = args[i + 1];
    i++;
  } else if (args[i] === '--frames' && args[i + 1]) {
    framesDir = args[i + 1];
    i++;
  }
}

if (!propsPath || (!outputPath && !framesDir)) {
  console.error('Usage: node render.mjs --props <props.json> (--frames <dir> | --output <output.webm|output.mp4>)');
  process.exit(1);
}

const rawProps = JSON.parse(fs.readFileSync(propsPath, 'utf8'));
const durationInFrames = rawProps.durationInFrames || 300;
const captions = rawProps.captions || [];
const callouts = rawProps.callouts || [];
const stylePreset = rawProps.stylePreset || 'luxury';
const subtitlePlacement = rawProps.subtitlePlacement || { position: 'top', top: 340, bottom: 440 };
let videoSrc = rawProps.videoSrc || '';
const isFrames = Boolean(framesDir);
const isWebmOverlay = outputPath ? outputPath.endsWith('.webm') : true;
const compositionId = (isFrames || isWebmOverlay) ? 'CaptionsOverlay' : 'CaptionsVideo';

console.log(`[Remotion] Bundling composition for ${compositionId}...`);
const entryPoint = path.join(__dirname, 'src', 'index.js');
const bundleLocation = await bundle({
  entryPoint,
  enableCaching: true,
});

if (!isFrames && !isWebmOverlay && videoSrc) {
  const bundlePublic = path.join(bundleLocation, 'public');
  if (!fs.existsSync(bundlePublic)) {
    fs.mkdirSync(bundlePublic, { recursive: true });
  }
  const targetPath = path.join(bundlePublic, 'current_input.mp4');
  try {
    if (fs.existsSync(targetPath)) fs.unlinkSync(targetPath);
  } catch (e) {}
  fs.copyFileSync(path.resolve(videoSrc), targetPath);
  videoSrc = 'current_input.mp4';
}

console.log(`[Remotion] Selecting composition ${compositionId}...`);
const inputProps = (isFrames || isWebmOverlay)
  ? { captions, callouts, stylePreset, subtitlePlacement }
  : { videoSrc, captions, callouts, stylePreset, subtitlePlacement };

const composition = await selectComposition({
  serveUrl: bundleLocation,
  id: compositionId,
  inputProps,
});

// Override duration if provided
composition.durationInFrames = durationInFrames;

if (isFrames) {
  fs.mkdirSync(framesDir, { recursive: true });
  console.log(`[Remotion] Rendering ${durationInFrames} PNG frames to ${framesDir}...`);
  let lastReportedPct = -1;
  await renderFrames({
    composition,
    serveUrl: bundleLocation,
    outputDir: framesDir,
    inputProps,
    imageFormat: 'png',
    concurrency: 3,
    onFrameUpdate: (renderedFrames) => {
      const pct = Math.round((renderedFrames / durationInFrames) * 100);
      if (pct % 5 === 0 && pct !== lastReportedPct) {
        lastReportedPct = pct;
        process.stdout.write(`[Remotion Progress] ${pct}%\n`);
      }
    },
  });
  console.log(`[Remotion] Successfully rendered ${durationInFrames} frames to ${framesDir}`);
  process.exit(0);
}

console.log(`[Remotion] Rendering ${durationInFrames} frames to ${outputPath}...`);

const renderOptions = {
  composition,
  serveUrl: bundleLocation,
  outputLocation: outputPath,
  inputProps,
  timeoutInMilliseconds: 300000,
  concurrency: 3,
  onProgress: ({ progress }) => {
    const percent = Math.round(progress * 100);
    if (percent % 10 === 0) {
      process.stdout.write(`[Remotion Progress] ${percent}%\n`);
    }
  },
};

if (isWebmOverlay) {
  renderOptions.codec = 'vp8';
  renderOptions.imageFormat = 'png';
  renderOptions.pixelFormat = 'yuva420p';
} else {
  renderOptions.codec = 'h264';
}

await renderMedia(renderOptions);

console.log(`[Remotion] Successfully rendered to ${outputPath}`);

