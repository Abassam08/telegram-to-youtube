# whisper-playground

A minimal, self-contained sandbox for trying out [OpenAI Whisper](https://github.com/openai/whisper) — speech recognition that can transcribe or translate audio/video into text and subtitles.

This folder is independent of the rest of the `telegram-to-youtube` pipeline — it doesn't import or depend on anything else in this repo.

After transcribing, it also calls Gemini to suggest a ready-to-upload YouTube **title, description, tags,
and hashtags**, tuned for a da'wah channel introducing Islam in English to non-Muslim, non-Arabic-speaking
viewers (see `metadata.py`).

## Setup

Requires Python 3.9+ and [ffmpeg](https://ffmpeg.org/) installed on your system (Whisper uses it to decode audio).

```bash
# system dependency
sudo apt install ffmpeg   # macOS: brew install ffmpeg

cd whisper-playground
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Metadata generation needs a Gemini API key. Create a `.env` file in `whisper-playground/` (or the repo root):

```
GOOGLE_GEMINI_API_KEY=your-key-here
```

> The first run of any model size downloads weights from OpenAI to `~/.cache/whisper` (e.g. `base` is ~140MB, `large` is ~3GB).

## Usage

Drop an audio or video file into `samples/`, then run:

```bash
python transcribe.py samples/your_file.mp4
```

By default this transcribes with the `base` model, writes an `.srt` subtitle file to `output/<source-filename>.srt`,
then prints + saves suggested YouTube metadata to `output/<source-filename>.metadata.txt`.

Pass `--skip-metadata` to only transcribe (no Gemini call).

### Options

```bash
python transcribe.py samples/your_file.mp4 \
  --model small \
  --language ar \
  --task transcribe \
  --format srt \
  --output-dir output
```

| Flag | Values | Notes |
|------|--------|-------|
| `--model` | `tiny`, `base`, `small`, `medium`, `large`, `turbo` | Bigger = more accurate, slower, more RAM/VRAM |
| `--language` | e.g. `ar`, `en` | Omit to auto-detect |
| `--task` | `transcribe`, `translate` | `translate` always outputs English regardless of source language |
| `--format` | `txt`, `srt`, `vtt`, `json`, `tsv`, `all` | `srt`/`vtt` are subtitle formats, `json` includes per-segment timestamps |
| `--skip-metadata` | flag | Skip the Gemini SEO metadata step, transcript-only |

### Examples

Transcribe Arabic speech to Arabic subtitles:

```bash
python transcribe.py samples/clip.mp4 --model small --language ar --format srt
```

Translate any language to English text:

```bash
python transcribe.py samples/clip.mp4 --model small --task translate --format txt
```

## Model size guide

| Model | Params | Relative speed | Good for |
|-------|--------|-----------------|----------|
| `tiny` | 39M | ~32x | Quick smoke tests |
| `base` | 74M | ~16x | Default, decent accuracy |
| `small` | 244M | ~6x | Better accuracy, still fast on CPU |
| `medium` | 769M | ~2x | High accuracy, wants a GPU |
| `large` | 1550M | 1x | Best accuracy, needs a GPU for reasonable speed |
| `turbo` | 809M | ~8x | Near-`large` accuracy at much higher speed |

## What's next

Once you know what you want to build with Whisper (e.g. auto-generating subtitles for the videos this repo uploads to YouTube, or transcribing captions to improve the Gemini metadata step), this folder can be promoted into a proper `services/` module or split into its own repository.
