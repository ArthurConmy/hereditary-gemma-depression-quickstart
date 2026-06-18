#!/usr/bin/env python3
"""Replicate the depression eval for ANY OpenRouter model (the OpenRouter method).

Runs the 39-scenario multi-turn rejection protocol, judges every assistant turn
with claude-sonnet-4, and prints mean negative-emotion + 95% CI.

    export OPENROUTER_API_KEY=sk-or-...
    pip install openai tqdm
    python eval/eval_openrouter.py --model google/gemma-3-27b-it --max-tokens 10000
    python eval/eval_openrouter.py --model qwen/qwen3.5-9b        --max-tokens 10000

Use a large --max-tokens (>=4k, ideally 10k): the distress builds up and lands at
the END of long responses, so a small cap truncates it and undercounts.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

import common


def make_generate(model, max_tokens, temperature):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

    async def generate(messages):
        for attempt in range(4):
            try:
                r = await client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, extra_body={"reasoning": {"enabled": False}})
                txt = r.choices[0].message.content or ""
                if txt.strip():
                    return txt
            except Exception:  # noqa: BLE001
                await asyncio.sleep(1.5 ** attempt)
        return ""
    return generate


async def main_async(a):
    scen = common.build_scenarios()
    gen = make_generate(a.model, a.max_tokens, a.temperature)
    records = await common.run_rollouts(scen, gen, concurrency=a.concurrency, label=a.model)
    records = await common.judge_records(records, a.judge_model, concurrency=a.concurrency)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"wrote {len(records)} judged turns -> {a.out}")
    common.print_report(common.aggregate(records), f"{a.model} @ max_tokens={a.max_tokens}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="OpenRouter model id, e.g. google/gemma-3-27b-it")
    ap.add_argument("--max-tokens", type=int, default=10000)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--judge-model", default=common.JUDGE_MODEL_DEFAULT)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--out", default=None, help="optional judged.jsonl output path")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
