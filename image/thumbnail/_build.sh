#!/bin/bash
# Build the README hero banner for VietVoice Studio from real app screenshots.
set -euo pipefail
cd "$(dirname "$0")"

AB="/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ABL="/System/Library/Fonts/Supplemental/Arial Black.ttf"
AR="/System/Library/Fonts/Supplemental/Arial.ttf"
ACCENT="#2dd4bf"      # teal — matches app brand
INK="#e6edf3"         # near-white text
MUTE="#9fb0bb"        # muted gray

W=1280; H=640

# --- helper: round corners + subtle border + drop shadow for a screenshot ---
make_card () {  # $1 in  $2 out  $3 width
  local in="$1" out="$2" cw="$3"
  magick "$in" -resize "${cw}x" /tmp/_sc.png
  local d cwh ch
  d=$(magick identify -format "%w %h" /tmp/_sc.png); cwh=($d); ch=${cwh[1]}
  magick -size "${cw}x${ch}" xc:none -draw "roundrectangle 0,0 $((cw-1)),$((ch-1)) 16,16" /tmp/_mask.png
  magick /tmp/_sc.png /tmp/_mask.png -alpha set -compose DstIn -composite /tmp/_round.png
  magick /tmp/_round.png -fill none -stroke "#27484b" -strokewidth 2 \
    -draw "roundrectangle 1,1 $((cw-2)),$((ch-2)) 16,16" /tmp/_stroked.png
  magick /tmp/_stroked.png \( +clone -background black -shadow 75x20+0+14 \) \
    +swap -background none -layers merge +repage "$out"
}

make_card _shot-studio.png card_studio.png 560
make_card _shot-video.png  card_video.png  560

# --- background: dark gradient + teal radial glow top-left ---
magick -size ${W}x${H} gradient:'#0c1218'-'#06090c' bg.png
magick -size ${W}x${H} radial-gradient:'#123a3a'-'#00000000' /tmp/_glow.png
magick bg.png /tmp/_glow.png -geometry +680-260 -compose screen -composite bg.png
# faint grid-free vignette accent line on left
magick bg.png -fill none -stroke "#16323200" -strokewidth 0 bg.png

# --- composite the two screenshot cards on the right (video on top) ---
magick bg.png card_studio.png -geometry +628+52 -composite \
       card_video.png  -geometry +688+292 -composite stage.png

# --- text block (left) ---
magick stage.png \
  -font "$AB"  -pointsize 21 -fill "$ACCENT" \
    -annotate +60+96 "SELF-HOSTED  ·  VIETNAMESE  AI  STUDIO" \
  -font "$ABL" -pointsize 56 -fill "$INK" \
    -annotate +58+168 "VietVoice Studio" \
  -font "$AR"  -pointsize 25 -fill "$MUTE" \
    -annotate +60+212 "Voice & talking-head video, from one prompt." \
  -font "$AB"  -pointsize 22 -fill "$ACCENT" -annotate +60+300 "▍" \
  -font "$AR"  -pointsize 22 -fill "$INK"    -annotate +84+300 "Multi-character Vietnamese TTS + LLM scripts" \
  -font "$AB"  -pointsize 22 -fill "$ACCENT" -annotate +60+346 "▍" \
  -font "$AR"  -pointsize 22 -fill "$INK"    -annotate +84+346 "Prompt → talking-head video with lip-sync" \
  -font "$AB"  -pointsize 22 -fill "$ACCENT" -annotate +60+392 "▍" \
  -font "$AR"  -pointsize 22 -fill "$INK"    -annotate +84+392 "Runs locally · built on VieNeu-TTS" \
  -font "$AB"  -pointsize 17 -fill "#7d8c97" \
    -annotate +60+470 "FastAPI   ·   Next.js   ·   SadTalker   ·   FFmpeg   ·   Apache-2.0" \
  thumbnail.png

# --- small caption pills over each card to label the job ---
magick thumbnail.png \
  -font "$AB" -pointsize 16 \
  -fill "#0b1218cc" -draw "roundrectangle 648,72 860,104 6,6" \
  -fill "$ACCENT"   -annotate +660+94 "STUDIO" \
  -fill "$INK"      -annotate +728+94 "— Multi-voice TTS" \
  -fill "#0b1218cc" -draw "roundrectangle 708,312 952,344 6,6" \
  -fill "$ACCENT"   -annotate +720+334 "VIDEO" \
  -fill "$INK"      -annotate +782+334 "— Talking-head pipeline" \
  thumbnail.png

# cleanup intermediates
rm -f bg.png stage.png card_studio.png card_video.png /tmp/_sc.png /tmp/_mask.png /tmp/_round.png /tmp/_stroked.png /tmp/_glow.png
magick identify -format "OUT: %wx%h  %b\n" thumbnail.png
