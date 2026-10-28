"""Score each NCO-2015 minor group for AI exposure through OpenRouter.

Reads data/nco/nco_descriptions.json and data/occupations_in.csv.
Writes data/scores_in.json, keyed by 3-digit nco_code, plus a "_meta"
key that records the model used.
"""

import argparse
import asyncio
import csv
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTIONS_PATH = ROOT / "data" / "nco" / "nco_descriptions.json"
OCCUPATIONS_IN_PATH = ROOT / "data" / "occupations_in.csv"
SCORES_IN_PATH = ROOT / "data" / "scores_in.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# The :batch variant routes to the provider batch queue. It costs half as
# much and may take noticeably longer to return.
DEFAULT_MODEL = "google/gemini-3.6-flash"
MAX_IN_FLIGHT = 8
MAX_ATTEMPTS = 5
MAX_OCCUPATION_TITLES = 40
META_KEY = "_meta"

RUBRIC = """You score a 3-digit NCO-2015 minor group of occupations for how much current
AI reshapes the work. Use a scale from 0 to 10.

0 means current AI changes almost nothing about the work.
10 means current AI reshapes most of the tasks.

Judge for India, not for another country. Apply these clauses:

- Weigh the cost of automation against the prevailing local wage. Indian wages
  for many occupations are low, so a technically automatable task may stay human
  for a long time because a machine costs more than the worker.
- Weigh informality. Work outside registered enterprises has little digital
  infrastructure to build on, which slows adoption regardless of the task content.
- Score the work, not the worker. Exposure means the tasks change, not that jobs
  disappear.
- Physical, in-person and manual work scores low. Desk work over text, numbers,
  code and images scores high.
- Judge the group as a whole, weighted by the occupations inside it that employ
  most people.

You receive the group title, every unit group title, up to 40 occupation titles,
and India labour context from the Periodic Labour Force Survey. Treat that
context as evidence about how the work is actually organized.

Return strict JSON only, with no prose around it:
{"exposure": <int 0-10>, "rationale": "<2-4 sentences>"}"""


def fail(message: str) -> None:
    sys.exit(f"05_score.py: {message}")


def load_descriptions() -> dict[str, dict[str, Any]]:
    if not DESCRIPTIONS_PATH.exists():
        fail("Missing data/nco/nco_descriptions.json. Run scripts/04_nco_descriptions.py first.")
    try:
        payload = json.loads(DESCRIPTIONS_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        fail(f"Cannot read data/nco/nco_descriptions.json: {exc}")
    if not isinstance(payload, dict):
        fail("data/nco/nco_descriptions.json must hold a JSON object keyed by nco_code.")
    descriptions: dict[str, dict[str, Any]] = {}
    for code, entry in payload.items():
        if not isinstance(entry, dict):
            print(f"WARNING: ignoring non-object entry for code {code}")
            continue
        descriptions[str(code)] = entry
    return descriptions


def load_context() -> dict[str, dict[str, str]]:
    if not OCCUPATIONS_IN_PATH.exists():
        fail("Missing data/occupations_in.csv. Run scripts/03_tabulate.py first.")
    context: dict[str, dict[str, str]] = {}
    with open(OCCUPATIONS_IN_PATH, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("nco_code") or "").strip()
            sector = str(row.get("cut_sector") or "").strip()
            sex = str(row.get("cut_sex") or "").strip()
            if not code or sector != "all" or sex != "all":
                continue
            context[code] = row
    return context


def load_cached_scores(force: bool) -> tuple[dict[str, dict[str, Any]], str | None]:
    if force or not SCORES_IN_PATH.exists():
        return {}, None
    try:
        payload = json.loads(SCORES_IN_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        print(f"WARNING: cannot read {SCORES_IN_PATH}; ignoring cache")
        return {}, None
    if not isinstance(payload, dict):
        return {}, None
    cached_model = None
    meta = payload.get(META_KEY)
    if isinstance(meta, dict):
        cached_model = meta.get("model")
    code_pattern = re.compile(r"^\d{3}$")
    scores: dict[str, dict[str, Any]] = {}
    for code, entry in payload.items():
        if not isinstance(entry, dict) or not code_pattern.fullmatch(str(code)):
            continue
        scores[str(code)] = entry
    return scores, cached_model


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(value) else float(value)
    text = str(value).strip()
    if not text or text.lower() in ("nan", "null", "none", "na"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_share(value: Any) -> str:
    number = to_number(value)
    if number is None:
        return "Not available"
    return f"{number * 100:.1f}%"


def format_earnings(value: Any) -> str:
    number = to_number(value)
    if number is None:
        return "Not available"
    return f"INR {round(number):,}"


def format_status_mix(value: Any) -> str:
    if value is None:
        return "Not available"
    try:
        mix = json.loads(str(value).strip())
    except json.JSONDecodeError:
        return "Not available"
    if not isinstance(mix, dict) or not mix:
        return "Not available"
    parts = []
    for key in ("self_employed", "regular", "casual"):
        share = to_number(mix.get(key))
        if share is not None:
            parts.append(f"{key.replace('_', '-')} {share * 100:.1f}%")
    return ", ".join(parts) or "Not available"


def build_user_prompt(code: str, entry: dict[str, Any], context_row: dict[str, str] | None) -> str:
    lines = []
    title = str(entry.get("title") or "").strip()
    if title:
        lines.append(f"Occupation group: {code} - {title}")
    else:
        lines.append(f"Occupation group: {code}")
    unit_groups = entry.get("unit_groups")
    if isinstance(unit_groups, list) and unit_groups:
        lines.append("Unit groups:")
        for unit_group in unit_groups:
            if not isinstance(unit_group, dict):
                continue
            parts = [str(p).strip() for p in (unit_group.get("code"), unit_group.get("title")) if p]
            if parts:
                lines.append(f"- {' '.join(parts)}")
    occupation_titles = entry.get("occupation_titles")
    if isinstance(occupation_titles, list) and occupation_titles:
        lines.append("Occupation titles:")
        for title in occupation_titles[:MAX_OCCUPATION_TITLES]:
            if title:
                lines.append(f"- {str(title).strip()}")
    lines.append("India labour context (PLFS, all India, all genders):")
    if context_row is None:
        lines.append("- Labour context: not available")
    else:
        lines.append(f"- Informality share: {format_share(context_row.get('informality_share'))}")
        lines.append(f"- Status mix: {format_status_mix(context_row.get('status_mix'))}")
        lines.append(
            f"- Median monthly earnings: "
            f"{format_earnings(context_row.get('median_monthly_earnings_inr'))}"
        )
    lines.append("Reply with strict JSON only, no prose:")
    lines.append('{"exposure": <int 0-10>, "rationale": "<2-4 sentences>"}')
    return "\n".join(lines)


def extract_json(reply: str) -> Any:
    text = reply.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def validate_reply(parsed: Any) -> tuple[int, str] | None:
    if not isinstance(parsed, dict):
        return None
    exposure = parsed.get("exposure")
    rationale = parsed.get("rationale")
    if isinstance(exposure, bool) or not isinstance(exposure, (int, float)):
        return None
    if exposure != int(exposure) or not (0 <= exposure <= 10):
        return None
    if not isinstance(rationale, str):
        return None
    rationale = rationale.strip()
    if len(rationale) < 30:
        return None
    return int(exposure), rationale


def delay_for(attempt: int) -> float:
    return min(30.0, 2.0 ** (attempt - 1)) + random.uniform(0.0, 0.5)


async def call_model(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    user_text: str,
    correction: bool,
) -> tuple[str | None, str]:
    messages = [
        {"role": "system", "content": RUBRIC},
        {"role": "user", "content": user_text},
    ]
    if correction:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous reply was invalid. Reply again with strict JSON only: "
                    '{"exposure": <int 0-10>, "rationale": "<2-4 sentences>"}.'
                ),
            }
        )
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_status = "no response"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        except httpx.TransportError as exc:
            last_status = exc.__class__.__name__
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(delay_for(attempt))
                continue
            return None, f"transport error {last_status}"
        status = response.status_code
        if status == 400:
            detail = " ".join(response.text[:200].split())
            return None, f"HTTP 400 not retried ({detail})"
        if status == 429 or status >= 500:
            last_status = f"HTTP {status}"
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(delay_for(attempt))
                continue
            return None, f"{last_status} after {MAX_ATTEMPTS} attempts"
        if status != 200:
            return None, f"HTTP {status} not retried"
        try:
            body = response.json()
        except json.JSONDecodeError:
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(delay_for(attempt))
                continue
            return None, "unreadable response body"
        if not isinstance(body, dict) or body.get("error"):
            last_status = "provider error in 200 response"
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(delay_for(attempt))
                continue
            return None, last_status
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return None, "no choices in response"
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            return None, "empty message content"
        return content, "ok"
    return None, last_status


def save_scores(scores: dict[str, Any]) -> None:
    ordered = {code: scores[code] for code in sorted(scores)}
    SCORES_IN_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")


async def score_group(
    code: str,
    entry: dict[str, Any],
    context_row: dict[str, str] | None,
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    semaphore: asyncio.Semaphore,
    scores: dict[str, Any],
) -> bool:
    async with semaphore:
        title = str(entry.get("title") or "")
        user_text = build_user_prompt(code, entry, context_row)
        for correction in (False, True):
            reply, status = await call_model(client, api_key, model, user_text, correction)
            if reply is None:
                print(f"  failed  {code}  {title}  ({status})")
                return False
            validated = validate_reply(extract_json(reply))
            if validated is not None:
                exposure, rationale = validated
                scores[code] = {"nco_code": code, "exposure": exposure, "rationale": rationale}
                save_scores(scores)
                print(f"  scored  {code}  {title}  exposure={exposure}")
                return True
        print(f"  failed  {code}  {title}  (invalid response twice)")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score NCO-2015 minor groups for AI exposure through OpenRouter. "
        "Writes data/scores_in.json."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenRouter model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Score at most N groups. 0 means all. Use it for a cheap smoke run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-score groups already present in data/scores_in.json",
    )
    return parser.parse_args()


async def run(arguments: argparse.Namespace) -> None:
    load_dotenv(ROOT / ".env", override=True)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        fail("Missing OPENROUTER_API_KEY in .env. Set it before scoring.")

    descriptions = load_descriptions()
    context = load_context()

    cached, cached_model = load_cached_scores(arguments.force)
    if cached_model and cached_model != arguments.model:
        print(
            f"WARNING: cached scores hold model '{cached_model}', requested '{arguments.model}'. "
            "Re-scoring all groups."
        )
        cached = {}
    scores: dict[str, Any] = dict(cached)
    scores[META_KEY] = {"model": arguments.model}

    codes = sorted(descriptions)
    to_score = [code for code in codes if arguments.force or code not in cached]
    cached_count = len(codes) - len(to_score)
    for code in to_score:
        if code not in context:
            print(
                f"  failed  {code}  {descriptions[code].get('title', '')}  "
                "(no all/all row in data/occupations_in.csv)"
            )

    missing_context = [code for code in to_score if code not in context]
    to_call = [code for code in to_score if code in context]
    if arguments.limit:
        to_call = to_call[: arguments.limit]

    for code in sorted(cached):
        title = descriptions.get(code, {}).get("title", "")
        exposure = cached[code].get("exposure") if isinstance(cached[code], dict) else None
        print(f"  cached  {code}  {title}  exposure={exposure}")

    print(
        f"scoring {len(to_call)} groups with model {arguments.model} "
        f"(at most {MAX_IN_FLIGHT} in flight)"
    )
    if not to_call:
        print("nothing new to score")

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        semaphore = asyncio.Semaphore(MAX_IN_FLIGHT)
        outcomes = await asyncio.gather(
            *(
                score_group(code, descriptions[code], context.get(code), client, api_key,
                            arguments.model, semaphore, scores)
                for code in to_call
            )
        )
    scored = sum(1 for outcome in outcomes if outcome)
    failed = len(to_call) - scored + len(missing_context)
    save_scores(scores)
    print(f"done: scored={scored} cached={cached_count} failed={failed} of groups={len(codes)}")


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()