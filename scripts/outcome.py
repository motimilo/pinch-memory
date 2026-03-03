#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
# ]
# ///
"""
PINCH Outcome Tracker — Point 1 of perpetual self-improvement.

Tags memories with outcome signals so the improvement loop can learn
what works and what doesn't.

Usage:
  uv run outcome.py log "what happened" --outcome success --domain scraping
  uv run outcome.py log "what failed" --outcome fail --domain social
  uv run outcome.py log "partial win" --outcome partial --domain coding
  uv run outcome.py summary
  uv run outcome.py summary --domain scraping
  uv run outcome.py recent [n]
"""

import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import add_memory, get_db, get_all_strengths

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
OUTCOMES_FILE = MEMORY_DIR / "outcomes.json"

VALID_OUTCOMES = ["success", "fail", "partial"]
VALID_DOMAINS = [
    "scraping", "social", "coding", "communication", "memory",
    "tools", "pipeline", "product", "general"
]


# ============================================================
# STORAGE
# ============================================================

def load_outcomes() -> list:
    if OUTCOMES_FILE.exists():
        return json.loads(OUTCOMES_FILE.read_text())
    return []

def save_outcomes(outcomes: list):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    OUTCOMES_FILE.write_text(json.dumps(outcomes[-500:], indent=2))  # Keep last 500


# ============================================================
# LOG AN OUTCOME
# ============================================================

def log_outcome(description: str, outcome: str, domain: str = "general", context: str = "") -> dict:
    """
    Log an outcome and store it as a tagged memory in PINCH.
    
    Format: [OUTCOME:success|fail|partial] [DOMAIN:xxx] description
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of: {VALID_OUTCOMES}")
    if domain not in VALID_DOMAINS:
        domain = "general"

    # Format for memory system (tagged for easy search)
    tagged_content = f"[OUTCOME:{outcome}] [DOMAIN:{domain}] {description}"
    if context:
        tagged_content += f" | Context: {context}"

    # Store in PINCH memory
    memory_id = add_memory(
        content=tagged_content,
        category="episodic",
        tier="short",
        source="outcome_tracker",
        metadata={
            "outcome": outcome,
            "domain": domain,
            "description": description,
            "context": context,
        },
        initial_strength=0.8 if outcome == "fail" else 0.6  # failures remembered longer
    )

    # Also store in local outcomes file for fast querying
    entry = {
        "id": memory_id,
        "timestamp": datetime.now().isoformat(),
        "outcome": outcome,
        "domain": domain,
        "description": description,
        "context": context,
    }
    outcomes = load_outcomes()
    outcomes.append(entry)
    save_outcomes(outcomes)

    icon = {"success": "✅", "fail": "❌", "partial": "⚡"}.get(outcome, "·")
    print(f"{icon} Logged [{outcome}] in [{domain}]: {description[:80]}")
    print(f"   Memory ID: {memory_id}")
    return entry


# ============================================================
# SUMMARY / REPORTING
# ============================================================

def summary(domain: str = None, hours_back: int = 168):
    """Show outcome summary, optionally filtered by domain."""
    outcomes = load_outcomes()
    cutoff = datetime.now() - timedelta(hours=hours_back)

    # Filter by time
    recent = [o for o in outcomes if datetime.fromisoformat(o["timestamp"]) > cutoff]

    # Filter by domain
    if domain:
        recent = [o for o in recent if o["domain"] == domain]

    if not recent:
        print("No outcomes logged yet.")
        return

    # Group by domain
    by_domain: dict = {}
    for o in recent:
        d = o["domain"]
        if d not in by_domain:
            by_domain[d] = {"success": [], "fail": [], "partial": []}
        by_domain[d][o["outcome"]].append(o["description"])

    print(f"\n📊 Outcome Summary (last {hours_back}h)")
    if domain:
        print(f"   Domain: {domain}")
    print("=" * 60)

    for d, counts in sorted(by_domain.items()):
        s = len(counts["success"])
        f = len(counts["fail"])
        p = len(counts["partial"])
        total = s + f + p
        rate = round((s + 0.5 * p) / total * 100) if total > 0 else 0

        print(f"\n[{d.upper()}] — {total} events, {rate}% success rate")
        if counts["success"]:
            print("  ✅ Wins:")
            for desc in counts["success"][-3:]:
                print(f"     • {desc[:70]}")
        if counts["fail"]:
            print("  ❌ Failures:")
            for desc in counts["fail"][-3:]:
                print(f"     • {desc[:70]}")
        if counts["partial"]:
            print("  ⚡ Partial:")
            for desc in counts["partial"][-3:]:
                print(f"     • {desc[:70]}")

    # Totals
    total_s = sum(len(v["success"]) for v in by_domain.values())
    total_f = sum(len(v["fail"]) for v in by_domain.values())
    total_p = sum(len(v["partial"]) for v in by_domain.values())
    total = total_s + total_f + total_p
    overall = round((total_s + 0.5 * total_p) / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} events | ✅ {total_s} | ❌ {total_f} | ⚡ {total_p} | {overall}% success")


def recent_outcomes(n: int = 10):
    """Show n most recent outcomes."""
    outcomes = load_outcomes()
    for o in outcomes[-n:]:
        icon = {"success": "✅", "fail": "❌", "partial": "⚡"}.get(o["outcome"], "·")
        ts = o["timestamp"][:16]
        print(f"{icon} [{ts}] [{o['domain']}] {o['description'][:80]}")


def export_for_improvement() -> dict:
    """Export outcome data structured for self_improve.py."""
    outcomes = load_outcomes()
    cutoff = datetime.now() - timedelta(hours=168)  # Last 7 days
    recent = [o for o in outcomes if datetime.fromisoformat(o["timestamp"]) > cutoff]

    by_domain: dict = {}
    for o in recent:
        d = o["domain"]
        if d not in by_domain:
            by_domain[d] = {"successes": [], "failures": [], "partials": []}
        if o["outcome"] == "success":
            by_domain[d]["successes"].append(o["description"])
        elif o["outcome"] == "fail":
            by_domain[d]["failures"].append(o["description"])
        else:
            by_domain[d]["partials"].append(o["description"])

    return by_domain


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PINCH Outcome Tracker")
    subparsers = parser.add_subparsers(dest="command")

    # log
    log_p = subparsers.add_parser("log", help="Log an outcome")
    log_p.add_argument("description", help="What happened")
    log_p.add_argument("--outcome", "-o", required=True, choices=VALID_OUTCOMES)
    log_p.add_argument("--domain", "-d", default="general", choices=VALID_DOMAINS)
    log_p.add_argument("--context", "-c", default="", help="Optional context")

    # summary
    sum_p = subparsers.add_parser("summary", help="Show outcome summary")
    sum_p.add_argument("--domain", "-d", default=None)
    sum_p.add_argument("--hours", type=int, default=168)

    # recent
    rec_p = subparsers.add_parser("recent", help="Show recent outcomes")
    rec_p.add_argument("n", nargs="?", type=int, default=10)

    args = parser.parse_args()

    if args.command == "log":
        log_outcome(args.description, args.outcome, args.domain, args.context)
    elif args.command == "summary":
        summary(args.domain, args.hours)
    elif args.command == "recent":
        recent_outcomes(args.n)
    else:
        parser.print_help()
