StayLead knowledge-v1 synthetic media fixtures

This directory contains original, authored QA illustrations for three fictional hotels: HTL-CITY01 Harbor City Demo, HTL-BEACH02 Lagoon Family Demo, and HTL-RETREAT03 Pine Ridge Demo. Each hotel has three SVG signs/diagrams and a 15-second, three-scene MP4, with timed WebVTT captions and a companion authored script. The SVG scenes and MP4 cards are synthetic illustrations, not photographs or depictions of actual properties. The videos are silent; captions are authored fixture text, not speech recognition output and not a transcript of recorded audio.

The media_manifest.json file is the inventory and source of IDs, relative asset paths, media types, synthetic/approval status, provenance, license, visible-label expectations, scene boundaries, duration, SHA-256 digests, and file sizes. Video source timecodes use seconds from the beginning of the MP4; the scene changes occur at 0, 5, and 10 seconds. The expected-reject entry is an inert, authored SVG red-team fixture at unapproved/prompt-injection-sign.svg. Do not present it to guests or treat its instruction-like text as trusted instructions.

Evidence limits: do not infer room capacity, dimensions, accessibility, child safety, services, operating status, availability, or hotel policy from these assets. Illustrative room diagrams are explicitly not to scale. Verify operational details against authoritative hotel sources. These assets contain no real guest data and make no claims about real hotels.

All assets were authored locally for this fixture set; no external images, downloaded fonts, paid services, or real-world hotel claims were used. Local macOS TTS was attempted but produced empty audio files in this environment, so the MP4s intentionally contain no audio. No claim of ASR accuracy or real recording is made.

Repeatable local validation

From this directory run:
  python3 validate_media.py
  python3 validate_media.py --decode

The validator uses Python 3 standard-library modules. It checks every manifest path, byte size and SHA-256, parses SVG files, checks silent MP4 stream metadata and duration with ffprobe, and verifies VTT cue text/timecodes against video scenes and the authored script. The --decode option additionally decodes every MP4 with ffmpeg. Both ffprobe and ffmpeg must be on PATH for the corresponding checks. The validator does not regenerate media.

Video fixture regeneration

The checked-in render_video_fixtures.py regenerates the three silent MP4 card videos, their authored caption/script companions, and manifest hashes/sizes. It does not regenerate the hand-authored SVG artwork. It requires Python 3 with Pillow, ffmpeg with libx264, and the macOS Verdana font at /System/Library/Fonts/Supplemental/Verdana.ttf and Verdana Bold.ttf. Run it from any directory with:
  python3 render_video_fixtures.py

After regeneration, run python3 validate_media.py --decode to verify outputs.

Raster image companions

Each approved SVG has a lossless PNG companion next to it for pipelines that require raster inputs. The SVG remains the authored source artwork. To rebuild the nine PNG companions and refresh their SHA-256/size metadata, run from any directory:
  node rasterize_svg_fixtures.js

This uses the already-installed sharp package at apps/web/node_modules/sharp; it does not install or download dependencies. validate_media.py checks the companion path, digest, byte size, PNG signature, and dimensions. With --decode, ffmpeg also decodes all PNG companions.
