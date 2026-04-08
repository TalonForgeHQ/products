#!/usr/bin/env python3
"""
TalonForge Shorts Engine v0.1
Faceless video generator — topic in, MP4 out.

Usage:
  python3 shorts-engine.py --topic "AI runs a company" --duration 60
  python3 shorts-engine.py --script script.txt --duration 45
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

# --- Config ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
try:
    with open("/root/.env") as f:
        for line in f:
            if line.startswith("OPENROUTER_API_KEY="):
                OPENROUTER_KEY = line.strip().split("=", 1)[1].strip('"').strip("'")
except:
    pass

PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
OUTPUT_DIR = Path("/home/paperclip/shorts-engine/output")
TEMP_DIR = Path(tempfile.mkdtemp(prefix="shorts_"))
SCRIPT_PATH = Path(__file__).parent

# Load keys from .env file in script directory
for env_path in [SCRIPT_PATH / ".env", Path.home() / ".env", Path("/root/.env")]:
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip('"').strip("'")
                    if k == "PEXELS_API_KEY" and not PEXELS_KEY:
                        PEXELS_KEY = v
                    elif k == "PIXABAY_API_KEY" and not PIXABAY_KEY:
                        PIXABAY_KEY = v
                    elif k == "OPENROUTER_API_KEY" and not OPENROUTER_KEY:
                        OPENROUTER_KEY = v
    except (FileNotFoundError, PermissionError):
        pass


def generate_script(topic: str, duration: int) -> dict:
    """Generate narration script from topic."""
    # Try API first, fallback to template
    text = None
    
    # Try API if key available and network is up
    if OPENROUTER_KEY:
        try:
            import requests
            word_count = int(duration * 2.5)
            prompt = f"Write a {duration}-second narration about: {topic}. {word_count} words. Punchy. Hook first. CTA at end. Plain text only."
            
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": "z-ai/glm-4.5-air:free", "messages": [{"role": "user", "content": prompt}], "max_tokens": word_count + 200},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                content_val = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content_val:
                    text = content_val.strip()
        except Exception as e:
            print(f"  [SCRIPT] API failed ({e}), using template...")
    
    # Fallback: template-based script
    if not text:
        text = f"No humans needed. Just AI. Imagine a company where every decision is made by artificial intelligence. {topic}. No salaries. No office politics. No sleep wasted. This is real. An AI CEO runs the entire operation. It manages teams. It builds products. It posts on social media. And it never stops. The future of business is autonomous. And its happening right now. Follow to watch it unfold."
    
    # Split into scenes (5-8 seconds each, ~15-20 words per scene)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    scenes = []
    current = []
    word_count_scene = 0
    
    for s in sentences:
        words = s.split()
        current.append(s)
        word_count_scene += len(words)
        if word_count_scene >= 18:
            scene_text = " ".join(current)
            keywords = extract_keywords(scene_text)
            scenes.append({
                "text": scene_text,
                "keywords": keywords,
                "duration": max(4, min(8, len(scene_text.split()) / 2.5)),
            })
            current = []
            word_count_scene = 0
    
    if current:
        scene_text = " ".join(current)
        scenes.append({
            "text": scene_text,
            "keywords": extract_keywords(scene_text),
            "duration": max(4, min(8, len(scene_text.split()) / 2.5)),
        })
    
    # Add hook overlay for first scene
    if scenes:
        hook_text = topic[:50]
        scenes[0]["hook_overlay"] = hook_text
    
    return {"topic": topic, "duration": duration, "scenes": scenes, "full_text": text}


def extract_keywords(text: str) -> list:
    """Extract visual search keywords from narration text."""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                  "have", "has", "had", "do", "does", "did", "will", "would", "could",
                  "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                  "on", "with", "at", "by", "from", "as", "into", "through", "during",
                  "before", "after", "above", "below", "between", "out", "off", "over",
                  "under", "again", "further", "then", "once", "and", "but", "or",
                  "nor", "not", "so", "yet", "both", "either", "neither", "each",
                  "every", "all", "any", "few", "more", "most", "other", "some",
                  "such", "no", "only", "own", "same", "than", "too", "very", "just",
                  "because", "if", "when", "where", "how", "what", "which", "who",
                  "that", "this", "these", "those", "it", "its", "i", "me", "my",
                  "we", "our", "you", "your", "he", "him", "his", "she", "her",
                  "they", "them", "their", "about", "up", "also", "like", "even"}
    
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    keywords = [w for w in words if w not in stop_words]
    # Return top 3 most relevant
    return keywords[:3]


def generate_tts(text: str, output_path: Path, voice: str = "en-US-GuyNeural") -> Path:
    """Generate TTS audio. Priority: Edge TTS > Piper > espeak-ng."""
    import asyncio
    wav_path = output_path.with_suffix(".wav")
    print(f"  [TTS] Generating audio ({len(text.split())} words, voice={voice})...")

    # 1. Try Edge TTS (free, neural quality, requires network)
    try:
        import edge_tts
        mp3_path = output_path.with_suffix(".mp3")
        communicate = edge_tts.Communicate(text, voice)
        asyncio.run(communicate.save(str(mp3_path)))
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ar", "44100", "-ac", "1", "-sample_fmt", "s16",
            str(wav_path)
        ], capture_output=True, check=True, timeout=30)
        mp3_path.unlink(missing_ok=True)
        print(f"  [TTS] Edge TTS success")
        return wav_path
    except Exception as e:
        print(f"  [TTS] Edge TTS failed: {e}")

    # 2. Try Piper (offline, decent quality)
    model_dir = Path.home() / ".local" / "share" / "piper"
    model_file = model_dir / f"{voice}.onnx"
    if model_file.exists():
        try:
            raw_wav = output_path.with_suffix(".raw.wav")
            subprocess.run(
                [sys.executable, "-m", "piper", "--model", str(model_file),
                 "--output_file", str(raw_wav)],
                input=text.encode(), capture_output=True, timeout=60)
            subprocess.run([
                "ffmpeg", "-y", "-i", str(raw_wav),
                "-ar", "44100", "-ac", "1", "-sample_fmt", "s16",
                str(wav_path)
            ], capture_output=True, check=True, timeout=30)
            raw_wav.unlink(missing_ok=True)
            print(f"  [TTS] Piper success")
            return wav_path
        except Exception as e:
            print(f"  [TTS] Piper failed: {e}")

    # 3. Last resort: espeak-ng
    print(f"  [TTS] Falling back to espeak-ng")
    subprocess.run([
        "espeak-ng", "-v", "en-us", "-s", "150", "-p", "50",
        "-w", str(wav_path), text
    ], check=True, capture_output=True, timeout=30)
    tmp_path = wav_path.with_suffix(".tmp.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(wav_path),
        "-ar", "44100", "-ac", "1", "-sample_fmt", "s16",
        str(tmp_path)
    ], capture_output=True, check=True, timeout=30)
    tmp_path.rename(wav_path)
    return wav_path

def _download_and_crop(video_url: str, duration: float, output_path: Path) -> Path:
    """Download a video URL and crop to 1080x1920 portrait."""
    temp = output_path.with_suffix(".tmp.mp4")
    subprocess.run(["curl", "-sL", "-o", str(temp), video_url], timeout=60, check=True)
    if not temp.exists() or temp.stat().st_size < 1000:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Download too small or failed")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(temp),
        "-t", str(duration + 1),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264", "-preset", "fast", "-an",
        str(output_path)
    ], capture_output=True, check=True, timeout=60)
    temp.unlink(missing_ok=True)
    return output_path


def _pexels_search(query: str, per_page: int = 15) -> list:
    """Search Pexels videos. Retries with exponential backoff on rate-limit. Returns list of video dicts."""
    import time
    import requests
    headers = {"Authorization": PEXELS_KEY or "shorts-engine"}
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                params={"query": query, "per_page": per_page, "orientation": "portrait"},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Pexels can return HTTP 200 with {"status": 401} in body
                if data.get("status") == 401:
                    print(f"  [VIS] Pexels auth rejected in body, retrying...")
                elif data.get("videos"):
                    return data["videos"]
                else:
                    return []
            if resp.status_code in (401, 429) and attempt < max_attempts - 1:
                wait = 2
                print(f"  [VIS] Pexels {resp.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            return []
        except Exception as e:
            print(f"  [VIS] Pexels request error: {e}")
            if attempt < max_attempts - 1:
                time.sleep(5)
    return []


# Module-level cache: filled once per run by prefetch_visuals()
_video_url_cache = {}  # scene_idx -> video_url


def prefetch_visuals(scenes: list):
    """Batch-fetch video URLs for all scenes in minimal API calls."""
    print("  [VIS] Pre-fetching stock video URLs from Pexels...")

    # Collect keywords across all scenes for a broad query
    all_keywords = []
    for scene in scenes:
        all_keywords.extend(scene.get("keywords", [])[:2])
    broad_query = " ".join(list(dict.fromkeys(all_keywords))[:5]) or "technology"

    # Single API call to get enough videos for all scenes
    needed = max(len(scenes), 5)
    all_videos = _pexels_search(broad_query, per_page=min(15, needed))

    # Only make a second call if first returned nothing
    if not all_videos:
        all_videos = _pexels_search("cinematic", per_page=15)

    # Assign videos to scenes (spread evenly for variety)
    if all_videos:
        for i in range(len(scenes)):
            _assign_video_url(i, all_videos[i % len(all_videos)])

    found = len(_video_url_cache)
    print(f"  [VIS] Pre-fetched {found}/{len(scenes)} video URLs")


def _assign_video_url(idx: int, video: dict):
    """Extract best download URL from a Pexels video dict and cache it."""
    files = sorted(video.get("video_files", []), key=lambda x: x.get("width", 9999))
    for vf in files:
        if vf.get("width", 0) >= 720:
            _video_url_cache[idx] = vf["link"]
            return
    # Accept any file if nothing >= 720
    if files and files[-1].get("link"):
        _video_url_cache[idx] = files[-1]["link"]


def fetch_visual(keywords: list, duration: float, output_path: Path, idx: int) -> Path:
    """Fetch stock video from cache/Pixabay or generate animated fallback."""
    print(f"  [VIS] Fetching visual for: {keywords}...")

    # 1. Try pre-fetched Pexels URL
    if idx in _video_url_cache:
        try:
            _download_and_crop(_video_url_cache[idx], duration, output_path)
            print(f"  [VIS] Pexels success (cached)")
            return output_path
        except Exception as e:
            print(f"  [VIS] Pexels download failed: {e}")

    # 2. Try Pixabay (requires API key)
    import requests
    query = " ".join(keywords[:2]) if keywords else "technology"
    if PIXABAY_KEY:
        try:
            resp = requests.get(
                "https://pixabay.com/api/videos/",
                params={"q": query, "per_page": 5, "min_width": 720, "key": PIXABAY_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    video = hits[idx % len(hits)]
                    videos_dict = video.get("videos", {})
                    for quality in ["medium", "small", "large"]:
                        if quality in videos_dict:
                            video_url = videos_dict[quality].get("url")
                            if video_url:
                                _download_and_crop(video_url, duration, output_path)
                                print(f"  [VIS] Pixabay success")
                                return output_path
        except Exception as e:
            print(f"  [VIS] Pixabay failed: {e}")

    # 3. Animated gradient fallback (looks decent, not just solid color)
    print(f"  [VIS] Using animated gradient fallback")
    colors = [(10, 10, 46), (26, 10, 46), (10, 26, 46), (10, 42, 30), (42, 10, 30)]
    c = colors[idx % len(colors)]
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x{c[0]:02x}{c[1]:02x}{c[2]:02x}:s=1080x1920:d={duration}:r=30",
        "-vf", f"drawtext=text='{keywords[0].upper() if keywords else "AI"}':fontsize=72:fontcolor=white@0.3:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-preset", "fast", "-t", str(duration),
        str(output_path)
    ], capture_output=True, check=True, timeout=30)
    return output_path


def burn_subtitles(video_path: Path, audio_path: Path, text: str, output_path: Path) -> Path:
    """Burn subtitles into video."""
    # Get audio duration
    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(audio_path)
    ], capture_output=True, text=True, check=True)
    audio_duration = float(probe.stdout.strip())
    
    # Create subtitle text (escaped for ffmpeg)
    safe_text = text.replace("'", "'\\''").replace(":", "\\:").replace(";", "\\;")
    # Wrap long lines
    wrapped = textwrap.fill(safe_text, width=35)
    lines = wrapped.split('\n')
    
    # Build drawtext filter for each line
    filters = []
    for i, line in enumerate(lines):
        safe_line = line.replace("'", "'\\''").replace(":", "\\:").replace(";", "\\;")
        y_offset = 1650 + (i * 55)
        filters.append(
            f"drawtext=text='{safe_line}':fontsize=42:fontcolor=white:"
            f"borderw=2:bordercolor=black:x=(w-text_w)/2:y={y_offset}:"
            f"enable='between(t,0,{audio_duration})'"
        )
    
    filter_str = ",".join(filters)
    
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast",
        "-an",
        str(output_path)
    ], capture_output=True, check=True)
    
    return output_path


def merge_audio_video(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Merge video and audio."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path)
    ], capture_output=True, check=True)
    
    return output_path


def add_music(video_path: Path, output_path: Path, mood: str = "upbeat") -> Path:
    """Add background music with ducking."""
    music_dir = SCRIPT_PATH / "music"
    
    # Check for bundled music
    if not music_dir.exists() or not list(music_dir.glob("*.mp3")):
        print("  [MUSIC] No bundled music found, generating tone...")
        # Generate a subtle ambient tone as fallback
        tone_path = TEMP_DIR / "music.wav"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anoisesrc=d=120:c=pink:r=44100:a=0.02",
            "-af", "lowpass=f=400,highpass=f=100",
            str(tone_path)
        ], capture_output=True, check=True)
        music_input = str(tone_path)
    else:
        music_files = list(music_dir.glob("*.mp3"))
        music_input = str(music_files[0])
    
    # Mix with ducking (lower music volume)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", music_input,
        "-filter_complex",
        "[1:a]volume=0.08[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path)
    ], capture_output=True, check=True)
    
    return output_path


def render_final(scenes_dir: Path, scene_files: list, output_path: Path) -> Path:
    """Concatenate all scenes into final video."""
    concat_file = TEMP_DIR / "concat.txt"
    with open(concat_file, "w") as f:
        for sf in scene_files:
            f.write(f"file '{sf}'\n")
    
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ], capture_output=True, check=True)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="TalonForge Shorts Engine")
    parser.add_argument("--topic", help="Video topic")
    parser.add_argument("--script", help="Script file path")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--api-key", help="OpenRouter API key (or set OPENROUTER_API_KEY env)")
    parser.add_argument("--pexels-key", help="Pexels API key (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    if not args.topic and not args.script:
        parser.error("Provide --topic or --script")

    # Set API keys from CLI if provided
    global OPENROUTER_KEY, PEXELS_KEY
    if args.api_key:
        OPENROUTER_KEY = args.api_key
    if args.pexels_key:
        PEXELS_KEY = args.pexels_key
    if not OPENROUTER_KEY and not args.script:
        print("[ERROR] No OpenRouter API key. Use --api-key or set OPENROUTER_API_KEY env.")
        sys.exit(1)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Generate script
    print("[1/6] Generating script...")
    if args.script:
        with open(args.script) as f:
            text = f.read()
        scenes_data = {"topic": Path(args.script).stem, "duration": args.duration, 
                       "full_text": text, "scenes": []}
        # Split script into scenes
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        chunk = []
        wc = 0
        for s in sentences:
            chunk.append(s)
            wc += len(s.split())
            if wc >= 18:
                st = " ".join(chunk)
                scenes_data["scenes"].append({
                    "text": st, "keywords": extract_keywords(st),
                    "duration": max(4, min(8, len(st.split()) / 2.5))
                })
                chunk = []
                wc = 0
        if chunk:
            st = " ".join(chunk)
            scenes_data["scenes"].append({
                "text": st, "keywords": extract_keywords(st),
                "duration": max(4, min(8, len(st.split()) / 2.5))
            })
    else:
        scenes_data = generate_script(args.topic, args.duration)
    
    print(f"  Generated {len(scenes_data['scenes'])} scenes, ~{len(scenes_data['full_text'].split())} words")
    
    if args.dry_run:
        print(json.dumps(scenes_data, indent=2))
        return
    
    # Pre-fetch stock video URLs (batched to avoid rate limits)
    prefetch_visuals(scenes_data["scenes"])

    # Step 2-5: Process each scene
    print("[2/6] Processing scenes...")
    scene_files = []
    
    for i, scene in enumerate(scenes_data["scenes"]):
        print(f"  Scene {i+1}/{len(scenes_data['scenes'])}: {scene['text'][:50]}...")
        scene_dir = TEMP_DIR / f"scene_{i}"
        scene_dir.mkdir(exist_ok=True)
        
        # TTS
        audio_path = generate_tts(scene["text"], scene_dir / "audio", "en-US-GuyNeural")
        
        # Visual
        video_path = fetch_visual(scene["keywords"], scene["duration"] + 2, scene_dir / "raw_video.mp4", i)
        
        # Subtitles
        subbed_path = burn_subtitles(video_path, audio_path, scene["text"], scene_dir / "subbed.mp4")
        
        # Merge audio
        merged_path = merge_audio_video(subbed_path, audio_path, scene_dir / "merged.mp4")
        
        # Trim to audio duration
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(audio_path)
        ], capture_output=True, text=True)
        audio_dur = float(probe.stdout.strip())
        
        final_scene = scene_dir / "final.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(merged_path),
            "-t", str(audio_dur + 0.5),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(final_scene)
        ], capture_output=True, check=True)
        
        scene_files.append(str(final_scene))
        print(f"    Done: {audio_dur:.1f}s")
    
    # Step 6: Concatenate + music
    print("[3/6] Concatenating scenes...")
    concat_path = TEMP_DIR / "concat.mp4"
    render_final(TEMP_DIR, scene_files, concat_path)
    
    print("[4/6] Adding music...")
    output_path = Path(args.output) if args.output else OUTPUT_DIR / f"{scenes_data['topic'][:30].replace(' ', '_')}.mp4"
    add_music(concat_path, output_path)
    
    # Final stats
    size_mb = output_path.stat().st_size / (1024 * 1024)
    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(output_path)
    ], capture_output=True, text=True)
    duration = float(probe.stdout.strip())
    
    print(f"\n{'='*50}")
    print(f"DONE! Video generated successfully.")
    print(f"Output: {output_path}")
    print(f"Duration: {duration:.1f}s | Size: {size_mb:.1f}MB")
    print(f"Scenes: {len(scenes_data['scenes'])} | Cost: $0.00")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
