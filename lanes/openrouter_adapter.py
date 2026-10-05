#!/usr/bin/env python3
"""OpenRouter lane adapter (shipped 2026-10-05).

File-based lane: Roman writes `lanes/outbox/openrouter/<name>-brief.md`;
this adapter sends the brief to OpenRouter (custom.openrouter credential,
never touches disk) and writes the model's response to
`lanes/inbox/openrouter/<name>-result.md`.

Why OpenRouter: Jeremy has an OpenRouter balance (2026-10-05). It gives us
ONE pipe for both ends of the ladder — dirt-cheap models for easy tasks and
frontier models for the hard calls — without another billing relationship.
The ChatGPT lane (OpenAI API) keeps its tiers; this lane adds the OpenRouter
menu. Roman dispatches; like the other lanes, results are reviewed before
anything is integrated. OpenRouter results never merge/push/deploy.

Usage:
    python3 lanes/openrouter_adapter.py dispatch lanes/outbox/openrouter/JEG-NNN-brief.md [--tier cheap|standard|strong|frontier] [--model slug]
    python3 lanes/openrouter_adapter.py self-test      # verifies key + shows balance
    python3 lanes/openrouter_adapter.py models         # lists live model prices

Cost/quality tiers (--tier; --model overrides the tier pick):
    cheap     deepseek/deepseek-v4.1-flash  ~$0.30/$1.20 per 1M in/out — easy tasks,
              summaries, first-pass sweeps. A typical 10K-in/5K-out brief ~$0.01.
    standard  z-ai/glm-5.2                  strong open-weight intelligence;
              mid reviews. Check live price via `models` (it moves).
    strong    openai/gpt-5.6-sol            ~$2.00/$10.00 — deep reviews, hard logic.
              Typical brief ~$0.07.
    frontier  anthropic/claude-opus-4.5     ~$5.00/$25.00 via the cheapest route —
              hardest calls only. Typical brief ~$0.18.
Prices from OpenRouter's live model catalog (refreshed 2026-10-05 via
`models`); they move — re-check before any cost-sensitive choice.

Named model overrides (verified working via --model):
    z-ai/glm-5.3-flash  $0.15/$1M in, $0.50/1M out (live catalog 2026-10-05),
              1M ctx. Reasoning capped via MODEL_OPTIONS (uncapped it burns
              the token budget on internal reasoning and returns empty).
              Tried 2026-10-05 on 6 parallel weekly-backend tickets: fast
              (~30-50s/brief) and caught real brief flaws (JEG-393 result).
              Cheapest capable option for implementation briefs.

Routing rule: use the CHEAPEST tier that can do the job. cheap for
mechanical/easy tasks; standard for competent reviews; strong for hard
reasoning; frontier only for the calls nothing else handles.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import dynamic_credential_entry, DynamicCredentialError

LANES_DIR = os.path.dirname(os.path.abspath(__file__))
OUTBOX = os.path.join(LANES_DIR, "outbox", "openrouter")
INBOX = os.path.join(LANES_DIR, "inbox", "openrouter")
API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_TIER = "cheap"
# Cost/quality ladder for the lane. Keys are the --tier names; values are
# OpenRouter model slugs. Re-verify via `python3 openrouter_adapter.py models`.
MODEL_TIERS = {
    "cheap": "stealth/space-bunny-alpha",     # $0.00 — free; best review artifact in the 2026-10-05 eval vs M3 (reasoning capped via MODEL_OPTIONS)
    "standard": "z-ai/glm-5.2",               # strong open-weight intelligence
    "strong": "openai/gpt-5.6-sol",           # ~$2.00/$10.00 — hard reasoning
    "frontier": "anthropic/claude-opus-4.5",  # ~$5.00/$25.00 — hardest calls only
}
ALLOWED = ("openrouter.ai",)
# Per-model request options. Space Bunny Alpha reasons without bound by
# default: on a meaty task it burned 4K then 16K tokens on internal reasoning
# and returned empty content twice (2026-10-05 eval). Capping its reasoning
# effort produces complete answers.
MODEL_OPTIONS = {
    "stealth/space-bunny-alpha": {"reasoning": {"effort": "low"}},
    # Same pathology as Bunny (2026-10-05): without a cap it burns the whole
    # token budget on internal reasoning and returns empty content.
    "z-ai/glm-5.3-flash": {"reasoning": {"effort": "low"}},
}


def _api_key() -> str:
    try:
        entry = dynamic_credential_entry("custom.openrouter", "access_token")
    except DynamicCredentialError as exc:
        raise RuntimeError(f"custom.openrouter credential unavailable: {exc}")
    surr = str(entry.get("surrogate", "")).strip()
    if not surr.startswith("hsurr:"):
        raise RuntimeError("authd did not return a usable surrogate")
    return surr


def _request(path: str, payload: dict | None = None) -> dict:
    from dynamic_credentials import add_surrogate_to_request
    url = API_BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
            # OpenRouter asks for app attribution; harmless metadata.
            "HTTP-Referer": "https://jb-barrel-droid.github.io/fantasy-tools/",
            "X-Title": "Data Driven Football lane dispatcher",
        },
    )
    add_surrogate_to_request(req, "custom.openrouter", allowed_hosts=ALLOWED)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter {e.code}: {e.read().decode()[:400]}")


def _post(prompt: str, model: str, max_tokens: int = 8000) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": ("You are a senior staff engineer reviewing a plan. Be direct, specific, "
                         "and adversarial where warranted. No vague praise. Every finding names "
                         "the exact section it touches and proposes a concrete fix.")},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }
    # Per-model options (e.g. reasoning caps) merge in here.
    payload.update(MODEL_OPTIONS.get(model, {}))
    body = _request("/chat/completions", payload)
    try:
        content = body["choices"][0]["message"].get("content")
    except (KeyError, IndexError, AttributeError):
        raise RuntimeError(f"unexpected API response shape: {str(body)[:300]}")
    if not content:
        # Reasoning models can burn a small token budget on thinking and
        # return empty content; surface the shape instead of None.
        raise RuntimeError(f"empty content in API response: {str(body)[:300]}")
    return content


def dispatch(brief_path: str, model: str) -> str:
    """Send a brief, write the result to the inbox, return the result path."""
    with open(brief_path) as f:
        brief_text = f.read()
    base = os.path.basename(brief_path)
    m = re.match(r"(.+)-brief\.md$", base)
    stem = m.group(1) if m else os.path.splitext(base)[0]
    print(f"dispatching {base} -> model {model} ...", flush=True)
    answer = _post(brief_text, model)
    os.makedirs(INBOX, exist_ok=True)
    out_path = os.path.join(INBOX, f"{stem}-result.md")
    header = (f"# OpenRouter lane result — {stem}\n\n"
              f"_Model: {model}. Review-only unless the brief says otherwise. "
              f"Roman integrates; OpenRouter results never merge/push/deploy._\n\n---\n\n")
    with open(out_path, "w") as f:
        f.write(header + answer)
    # usage ledger for the watcher
    ledger = os.path.join(LANES_DIR, "dispatch_ledger.jsonl")
    with open(ledger, "a") as f:
        f.write(json.dumps({"lane": "openrouter", "brief": base,
                            "result": os.path.basename(out_path),
                            "model": model}) + "\n")
    print(f"result written: {out_path} ({len(answer)} chars)")
    return out_path


def self_test() -> None:
    # 1) key check: auth endpoint returns the key's credit info.
    try:
        data = _request("/auth/key").get("data", {})
        print(f"auth OK. label={data.get('label')} usage=${data.get('usage')} "
              f"limit={data.get('limit')} limit_remaining={data.get('limit_remaining')}")
    except RuntimeError as e:
        print(f"self-test FAIL (auth): {e}")
        sys.exit(1)
    # 2) round-trip on the cheapest tier. Generous token budget: reasoning
    # models spend tokens thinking before answering, and a small budget can
    # come back with empty content.
    try:
        answer = _post("Reply with exactly: OPENROUTER_LANE_OK",
                       MODEL_TIERS["cheap"], max_tokens=500)
    except RuntimeError as e:
        print(f"self-test FAIL (dispatch): {e}")
        sys.exit(1)
    # The ping checks connectivity, not model perfection: the cheapest tier
    # can garble an exact echo, so match the marker loosely.
    ok = "LANE_OK" in answer
    print("self-test:", "PASS" if ok else f"FAIL (got: {answer[:100]})")
    sys.exit(0 if ok else 1)


def list_models(limit: int = 12) -> None:
    """Print the current price ladder for the models we care about."""
    body = _request("/models")
    wanted = list(dict.fromkeys(MODEL_TIERS.values()))
    by_id = {m["id"]: m for m in body.get("data", [])}
    for slug in wanted:
        m = by_id.get(slug)
        if not m:
            print(f"{slug}: NOT FOUND in catalog")
            continue
        p = m.get("pricing", {})
        print(f"{slug}: ${float(p.get('prompt', 0))*1e6:.2f}/${float(p.get('completion', 0))*1e6:.2f} per 1M in/out  ctx={m.get('context_length')}")
    if limit:
        print("\nUse `--model <slug>` to override the tier pick.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "self-test":
        self_test()
    elif cmd == "models":
        list_models()
    elif cmd == "dispatch":
        if len(sys.argv) < 3:
            print("usage: openrouter_adapter.py dispatch <brief-path> [--tier NAME] [--model SLUG]")
            sys.exit(2)
        tier = DEFAULT_TIER
        if "--tier" in sys.argv:
            tier = sys.argv[sys.argv.index("--tier") + 1]
            if tier not in MODEL_TIERS:
                print(f"unknown tier: {tier} (choose from: {', '.join(MODEL_TIERS)})")
                sys.exit(2)
        model = MODEL_TIERS[tier]
        if "--model" in sys.argv:
            model = sys.argv[sys.argv.index("--model") + 1]
        dispatch(sys.argv[2], model)
    else:
        print(f"unknown command: {cmd}")
        sys.exit(2)
