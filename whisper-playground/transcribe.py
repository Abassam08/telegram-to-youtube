#!/usr/bin/env python3
"""CLI for transcribing or translating audio/video files with OpenAI Whisper,
then suggesting SEO-optimized YouTube metadata from the transcript."""
import argparse
import os
import sys

import whisper
from whisper.utils import get_writer

from metadata import format_metadata, generate_seo_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe or translate audio/video with Whisper")
    parser.add_argument("input", help="Path to an audio or video file")
    parser.add_argument(
        "--model", default="base",
        choices=["tiny", "base", "small", "medium", "large", "turbo"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--language", default=None,
        help="Force source language, e.g. 'ar' or 'en'. Auto-detected if omitted",
    )
    parser.add_argument(
        "--task", default="transcribe", choices=["transcribe", "translate"],
        help="'transcribe' keeps the original language, 'translate' outputs English",
    )
    parser.add_argument(
        "--format", default="srt", choices=["txt", "srt", "vtt", "json", "tsv", "all"],
        help="Output format (default: srt)",
    )
    parser.add_argument(
        "--output-dir", default="output",
        help="Directory to write results to (default: output/)",
    )
    parser.add_argument(
        "--skip-metadata", action="store_true",
        help="Skip generating SEO metadata suggestions (transcript only)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"Input file not found: {args.input}")

    os.makedirs(args.output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.input))[0]

    print(f"Loading Whisper model '{args.model}'...")
    model = whisper.load_model(args.model)

    print(f"Running {args.task} on {args.input}...")
    result = model.transcribe(args.input, language=args.language, task=args.task, verbose=False)

    transcript = result["text"].strip()
    print("\n--- Detected text ---")
    print(transcript)

    # whisper's writers name output files after the input's basename, so each
    # source file gets its own <stem>.<format> instead of overwriting a shared name.
    writer = get_writer(args.format, args.output_dir)
    writer(result, args.input)
    print(f"\nSaved {args.format} output to {args.output_dir}/{stem}.{args.format}")

    if args.skip_metadata:
        return

    print("\nGenerating SEO metadata suggestions...")
    try:
        metadata = generate_seo_metadata(transcript)
    except Exception as exc:
        print(f"\nMetadata generation failed: {exc}")
        return

    metadata_text = format_metadata(metadata)
    print(f"\n{metadata_text}")

    metadata_path = os.path.join(args.output_dir, f"{stem}.metadata.txt")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(metadata_text + "\n")
    print(f"\nSaved metadata suggestions to {metadata_path}")


if __name__ == "__main__":
    main()
