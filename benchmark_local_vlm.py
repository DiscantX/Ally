"""Phase 0 benchmark: local VLM (via Ollama) vs. Scribe's structured-extraction job.

Tests a locally-served vision model (default: moondream, served through Ollama)
against a folder of real game screenshots, at both original resolution and a
downscaled variant, logging wall-clock latency and raw output to CSV for
side-by-side review.

IMPORTANT CAVEAT: Ollama serves moondream through its generic multimodal
chat/generate endpoint, not the model's native `detect()`/`point()` skill API
(only available via the `moondream` pip package or Roboflow Inference). This
means bounding boxes here come from prompting the model to emit JSON, not from
a purpose-built grounding head -- expect this to be weaker than the model's
best-case grounding accuracy. This is a deliberate, documented limitation of
testing through Ollama, not a bug in this script. If results here look poor,
that alone doesn't rule the model out -- it specifically rules out "prompted
JSON through Ollama" as the integration path.

Usage:
    python benchmark_local_vlm.py
    python benchmark_local_vlm.py --model moondream --images-dir images
    python benchmark_local_vlm.py --downscale-max-side 512
    python benchmark_local_vlm.py --skip-full-res
    python benchmark_local_vlm.py --skip-downscaled
    python benchmark_local_vlm.py --timeout 300

Requires: `ollama serve` running locally with the target model already pulled
(e.g. `ollama pull moondream`), plus the `requests` and `Pillow` packages
(`pip install requests pillow` if not already present).

Note on --downscale-max-side: 768 is a starting guess, not a confirmed
"correct" value -- Moondream's vision encoder has its own trained input
resolution, and feeding it something far off that either wastes compute
(too large) or throws away detail (too small). Sweep a few values
(e.g. 384, 512, 768, 1024) across a re-run and compare the timing/accuracy
columns before locking in a number. Once you have one, it maps directly onto
this project's existing `downscale_max_size` config key in
cabinet/configs/*/config.json -- no new mechanism needed, just a tuned value.
"""

import argparse
import base64
import csv
import io
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from PIL import Image

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "moondream"
DEFAULT_IMAGES_DIR = "images"
DEFAULT_OUTPUT_CSV = "vlm_benchmark_results.csv"
DEFAULT_DOWNSCALE_MAX_SIDE = 768  # starting guess -- see docstring note above
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Shaped to mirror Scribe's actual schema (brain/knowledge/schema/schema.py's
# ScreenElement), so results are a fair apples-to-apples comparison against
# what Scribe currently returns -- not a free-form caption like the earlier
# ad-hoc test.
EXTRACTION_PROMPT = """You are analyzing a single screenshot from a video game.
Identify every distinct visual element you can see: characters, UI elements,
vehicles, and notable objects. Do not use any prior knowledge of this specific
game -- describe only what is visible.

Respond with ONLY a JSON array, no other text, no markdown code fences. Each
element must have this exact shape:
{"label": "short 1-3 word label", "description": "one plain sentence describing it", "box_2d": [y_min, x_min, y_max, x_max]}

box_2d coordinates must be normalized 0-1000 relative to the full image
(y_min/x_min = top-left corner, y_max/x_max = bottom-right corner).
"""


@dataclass
class BenchmarkResult:
    image_name: str
    variant: str  # "full_res" or "downscaled"
    width: int
    height: int
    elapsed_seconds: float
    http_ok: bool
    json_parsed: bool
    element_count: int
    raw_response: str
    error: str = ""


def find_images(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")
    files = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(
            f"No supported images ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found in {images_dir}"
        )
    return files


def load_and_maybe_downscale(path: Path, max_side: int | None) -> tuple[Image.Image, int, int]:
    """Loads an image, optionally downscaling so its longest side is at most
    `max_side`, preserving aspect ratio. Returns (image, width, height) of
    whatever was actually produced (original if max_side is None or the
    image is already smaller than max_side)."""
    img = Image.open(path).convert("RGB")
    if max_side is not None:
        w, h = img.size
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            new_w, new_h = round(w * scale), round(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img, img.width, img.height


def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def call_ollama(
    base_url: str, model: str, prompt: str, image_b64: str, timeout: float
) -> tuple[bool, str, float]:
    """Calls Ollama's /api/generate with a single image + prompt (non-streaming,
    so the full response is captured in one shot rather than assembled from
    chunks). Returns (http_ok, response_text, elapsed_seconds)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    start = time.perf_counter()
    try:
        resp = requests.post(base_url, json=payload, timeout=timeout)
        elapsed = time.perf_counter() - start
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text[:500]}", elapsed
        data = resp.json()
        return True, data.get("response", ""), elapsed
    except requests.exceptions.RequestException as e:
        elapsed = time.perf_counter() - start
        return False, f"Request failed: {e}", elapsed


def try_parse_elements(raw_text: str) -> tuple[bool, int]:
    """Best-effort JSON extraction -- models routinely wrap JSON in markdown
    fences or add stray preamble/trailing text despite instructions not to,
    so this strips common wrapping before giving up. Returns
    (parsed_ok, element_count)."""
    text = raw_text.strip()
    if "```" in text:
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start_idx = text.find("[")
    end_idx = text.rfind("]")
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return False, 0
    candidate = text[start_idx:end_idx + 1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return True, len(parsed)
        return False, 0
    except json.JSONDecodeError:
        return False, 0


def run_benchmark(
    images_dir: Path,
    model: str,
    base_url: str,
    output_csv: Path,
    downscale_max_side: int | None,
    test_full_res: bool,
    test_downscaled: bool,
    timeout: float,
) -> None:
    images = find_images(images_dir)
    print(f"Found {len(images)} image(s) in {images_dir}")
    print(f"Model: {model} | Endpoint: {base_url}")
    if test_downscaled:
        print(f"Downscale target (longest side): {downscale_max_side}px")
    print()

    results: list[BenchmarkResult] = []

    for path in images:
        variants: list[tuple[str, int | None]] = []
        if test_full_res:
            variants.append(("full_res", None))
        if test_downscaled:
            variants.append(("downscaled", downscale_max_side))

        for variant_name, max_side in variants:
            print(f"[{path.name}] variant={variant_name} ... ", end="", flush=True)
            img, w, h = load_and_maybe_downscale(path, max_side)
            image_b64 = image_to_base64(img)

            http_ok, raw_response, elapsed = call_ollama(
                base_url, model, EXTRACTION_PROMPT, image_b64, timeout
            )
            json_parsed, element_count = (
                try_parse_elements(raw_response) if http_ok else (False, 0)
            )

            result = BenchmarkResult(
                image_name=path.name,
                variant=variant_name,
                width=w,
                height=h,
                elapsed_seconds=round(elapsed, 3),
                http_ok=http_ok,
                json_parsed=json_parsed,
                element_count=element_count,
                raw_response=raw_response,
            )
            results.append(result)

            status = "OK" if http_ok else "FAILED"
            parse_note = f"{element_count} elements" if json_parsed else "unparseable JSON"
            print(f"{status} in {elapsed:.2f}s ({w}x{h}) -- {parse_note}")

    write_csv(results, output_csv)
    print(f"\nWrote {len(results)} rows to {output_csv}")
    print_summary(results)


def write_csv(results: list[BenchmarkResult], output_csv: Path) -> None:
    if not results:
        return
    fieldnames = list(asdict(results[0]).keys())
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def print_summary(results: list[BenchmarkResult]) -> None:
    print("\n--- Summary (per variant) ---")
    by_variant: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        by_variant.setdefault(r.variant, []).append(r)

    for variant, rows in by_variant.items():
        avg_time = sum(r.elapsed_seconds for r in rows) / len(rows)
        parse_rate = sum(1 for r in rows if r.json_parsed) / len(rows) * 100
        parsed_rows = [r for r in rows if r.json_parsed]
        avg_elements = (
            sum(r.element_count for r in parsed_rows) / len(parsed_rows) if parsed_rows else 0.0
        )
        print(
            f"  {variant:12s}  avg={avg_time:6.2f}s  "
            f"parse_ok={parse_rate:5.1f}%  avg_elements={avg_elements:.1f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark a local VLM (served via Ollama) against real game screenshots."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_OLLAMA_URL, help="Ollama /api/generate endpoint")
    parser.add_argument("--images-dir", default=DEFAULT_IMAGES_DIR, help="Directory of test images")
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV, help="Output CSV path")
    parser.add_argument(
        "--downscale-max-side", type=int, default=DEFAULT_DOWNSCALE_MAX_SIDE,
        help="Longest-side target in pixels for the downscaled variant (see docstring note)",
    )
    parser.add_argument("--skip-full-res", action="store_true", help="Skip the full-resolution variant")
    parser.add_argument("--skip-downscaled", action="store_true", help="Skip the downscaled variant")
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-request timeout in seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_benchmark(
        images_dir=Path(args.images_dir),
        model=args.model,
        base_url=args.base_url,
        output_csv=Path(args.output_csv),
        downscale_max_side=args.downscale_max_side,
        test_full_res=not args.skip_full_res,
        test_downscaled=not args.skip_downscaled,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
