#!/usr/bin/env python3
"""CLI for transcribing or translating audio/video files with OpenAI Whisper."""
import argparse
import os
import sys

import whisper
from whisper.utils import get_writer


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
    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"Input file not found: {args.input}")

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Loading Whisper model '{args.model}'...")
    model = whisper.load_model(args.model)

    print(f"Running {args.task} on {args.input}...")
    result = model.transcribe(args.input, language=args.language, task=args.task, verbose=False)

    print("\n--- Detected text ---")
    print(result["text"].strip())

    writer = get_writer(args.format, args.output_dir)
    writer(result, args.input)
    print(f"\nSaved {args.format} output to {args.output_dir}/")


if __name__ == "__main__":
    main()
