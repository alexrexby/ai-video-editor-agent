#!/usr/bin/env bash
# Downloads luxury fonts for offline Remotion rendering
set -e

FONTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$FONTS_DIR"

echo "📥 Downloading Cormorant Garamond and Montserrat fonts..."

curl -sL "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-BoldItalic.ttf" -o "$FONTS_DIR/CormorantGaramond-BoldItalic.ttf"
curl -sL "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-Italic.ttf" -o "$FONTS_DIR/CormorantGaramond-Italic.ttf"
curl -sL "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-SemiBoldItalic.ttf" -o "$FONTS_DIR/CormorantGaramond-SemiBoldItalic.ttf"
curl -sL "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Bold.ttf" -o "$FONTS_DIR/Montserrat-Bold.ttf"
curl -sL "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-ExtraBold.ttf" -o "$FONTS_DIR/Montserrat-ExtraBold.ttf"

echo "✅ All fonts downloaded successfully to $FONTS_DIR"
