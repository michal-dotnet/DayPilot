"""
הרצת ניסוי ב-LangSmith על ה-Dataset של DayPilot.

הרצה מתיקיית הפרויקט:
    python evaluation/run_experiment.py --name baseline
    python evaluation/run_experiment.py --name baseline --limit 3     # בדיקת עשן קצרה
    python evaluation/run_experiment.py --name improved
    python evaluation/run_experiment.py --name baseline-rescored --rescore baseline-v1-c4b25821
        # מריץ שוב רק את הבודקים על ניסוי קיים (בלי להריץ את האגנט), אחרי תיקון בבודקים

כל ניסוי נשמר גם ב-LangSmith (Datasets & Experiments) וגם מקומית ב-evaluation/results/.
אין כאן תוצאות מומצאות: כל מספר מגיע מהרצה אמיתית.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from daypilot.config import get_settings  # noqa: E402
from daypilot.utils.tls import use_system_certificates  # noqa: E402

settings = get_settings()
use_system_certificates(settings.use_system_certificates)
settings.export_tracing_env()

from langchain_core.callbacks import get_usage_metadata_callback  # noqa: E402
from langsmith import Client, evaluate  # noqa: E402

from daypilot.agent.llm import build_llm  # noqa: E402
from daypilot.agent.prompts import PROMPT_VERSION  # noqa: E402
from evaluators import checks_evaluator, make_quality_evaluator  # noqa: E402
from harness import run_scenario  # noqa: E402
from scenarios import NOW, SCENARIOS  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATASET_NAME = "daypilot-scenarios-v1"
# מחיר ל-1M טוקנים (gpt-6-luna, לפי דף התמחור של OpenAI בנובמבר 2026). לעדכן אם המודל משתנה.
PRICE_PER_M = {"input": 0.10, "output": 0.50}

usage = {"input_tokens": 0, "output_tokens": 0}


def ensure_dataset(client: Client) -> None:
    if client.has_dataset(dataset_name=DATASET_NAME):
        existing = {ex.inputs.get("id") for ex in client.list_examples(dataset_name=DATASET_NAME)}
        missing = [s for s in SCENARIOS if s["id"] not in existing]
        if not missing:
            print(f"Dataset '{DATASET_NAME}' קיים ({len(existing)} תרחישים)")
            return
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    else:
        dataset = client.create_dataset(dataset_name=DATASET_NAME, description="DayPilot Hebrew agent scenarios")
        missing = SCENARIOS
    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": {
                    "id": s["id"], "category": s["category"], "messages": s["messages"], "setup": s.get("setup") or {},
                    "decision": s.get("decision", "approve"), "now": NOW,
                },
                "outputs": {"checks": s["checks"]},
                "metadata": {"category": s["category"]},
            }
            for s in missing
        ],
    )
    print(f"נוספו {len(missing)} תרחישים ל-Dataset '{DATASET_NAME}'")


def add_usage(callback) -> None:
    for data in callback.usage_metadata.values():
        usage["input_tokens"] += data.get("input_tokens", 0)
        usage["output_tokens"] += data.get("output_tokens", 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="baseline / improved / ...")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", nargs="*", default=None)
    parser.add_argument("--rescore", default=None, help="שם ניסוי קיים להערכה מחדש")
    args = parser.parse_args()

    client = Client()
    ensure_dataset(client)
    llm = build_llm(settings)
    judge = build_llm(settings)

    examples = list(client.list_examples(dataset_name=DATASET_NAME))
    examples.sort(key=lambda e: e.inputs["id"])
    if args.ids:
        examples = [e for e in examples if e.inputs["id"] in args.ids]
    if args.limit:
        examples = examples[: args.limit]

    def target(inputs: dict) -> dict:
        with get_usage_metadata_callback() as cb:
            out = run_scenario(inputs, llm)
        add_usage(cb)
        print(f"  • {inputs['id']}: {'שגיאה' if out['error'] else 'הסתיים'}")
        return out

    quality = make_quality_evaluator(judge)

    def judged(inputs, outputs):
        with get_usage_metadata_callback() as cb:
            result = quality(inputs, outputs)
        add_usage(cb)
        return result

    if args.rescore:
        from langsmith.evaluation import evaluate_existing

        print(f"מעריך מחדש את הניסוי {args.rescore} (האגנט לא רץ שוב)...")
        results = evaluate_existing(args.rescore, evaluators=[checks_evaluator, judged], max_concurrency=1)
        prompt_version = "as in " + args.rescore
    else:
        print(f"מריץ {len(examples)} תרחישים (prompt {PROMPT_VERSION}, model {settings.model_name})...")
        results = evaluate(
            target,
            data=examples,
            evaluators=[checks_evaluator, judged],
            experiment_prefix=f"{args.name}-{PROMPT_VERSION}",
            max_concurrency=1,
            metadata={"prompt_version": PROMPT_VERSION, "model": settings.model_name, "name": args.name},
        )
        prompt_version = PROMPT_VERSION

    per_check: dict[str, list[int]] = defaultdict(list)
    per_category: dict[str, list[int]] = defaultdict(list)
    quality_scores: list[float] = []
    rows = []
    for row in results:
        ex = row["example"]
        scores = {r.key: r.score for r in row["evaluation_results"]["results"]}
        judge_comment = next((r.comment for r in row["evaluation_results"]["results"] if r.key == "reply_quality"), None)
        for key, score in scores.items():
            if key == "reply_quality":
                quality_scores.append(score)
            elif key != "all_checks_passed" and score is not None:
                per_check[key].append(score)
        if not scores:
            continue
        per_category[ex.inputs["category"]].append(scores.get("all_checks_passed", 0))
        rows.append({"id": ex.inputs["id"], "category": ex.inputs["category"], "scores": scores,
                     "final_reply": row["run"].outputs.get("final_reply"), "error": row["run"].outputs.get("error"),
                     "judge_comment": judge_comment,
                     "sessions": [(x["start"][:16], x["end"][11:16]) for x in row["run"].outputs.get("after", {}).get("sessions", [])
                                  if x["status"] == "planned"],
                     "tools": [c["name"] for c in row["run"].outputs.get("tool_calls", [])]})

    cost = usage["input_tokens"] / 1e6 * PRICE_PER_M["input"] + usage["output_tokens"] / 1e6 * PRICE_PER_M["output"]
    passed = sum(1 for r in rows if r["scores"].get("all_checks_passed"))
    summary = {
        "name": args.name,
        "experiment": results.experiment_name,
        "prompt_version": prompt_version,
        "model": settings.model_name,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "scenarios": len(rows),
        "scenarios_all_passed": passed,
        "per_check_pass_rate": {k: round(sum(v) / len(v), 3) for k, v in sorted(per_check.items())},
        "per_category_pass_rate": {k: round(sum(v) / len(v), 3) for k, v in sorted(per_category.items())},
        "reply_quality_avg": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None,
        "tokens": usage,
        "estimated_cost_usd": round(cost, 4),
        "rows": rows,
    }
    out_dir = ROOT / "evaluation" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.name}-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nניסוי: {results.experiment_name}")
    print(f"תרחישים שעברו את כל הבדיקות: {passed}/{len(rows)}")
    print(f"איכות תשובה ממוצעת (שופט): {summary['reply_quality_avg']}")
    print("אחוז הצלחה לפי בדיקה:")
    for key, rate in summary["per_check_pass_rate"].items():
        print(f"  {key:32} {rate:.0%}  ({sum(per_check[key])}/{len(per_check[key])})")
    print(f"טוקנים: {usage['input_tokens']:,} קלט, {usage['output_tokens']:,} פלט. עלות משוערת: ${cost:.4f}")
    print(f"נשמר: {path}")


if __name__ == "__main__":
    main()
