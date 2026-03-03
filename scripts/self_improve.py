#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
#     "httpx>=0.25.0",
# ]
# ///
"""
PINCH Self-Improvement Engine — Points 2, 3, 4 of perpetual self-improvement.

2. CONSOLIDATE: Search PINCH memory for outcomes + patterns
3. APPLY: Generate proposed updates to SKILL.md, TOOLS.md, AGENTS.md, MEMORY.md
4. LOOP: Called by cron + heartbeat on a schedule

Usage:
  uv run self_improve.py run          # Full improvement cycle
  uv run self_improve.py pending      # Show pending doc updates
  uv run self_improve.py apply        # Apply all pending updates
  uv run self_improve.py apply --id X # Apply a specific update
  uv run self_improve.py dismiss --id X  # Dismiss without applying
  uv run self_improve.py status       # Show improvement stats
"""

import sys
import json
import re
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import get_db, get_all_strengths
from outcome import load_outcomes, export_for_improvement

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
WORKSPACE = Path.home() / ".openclaw" / "workspace"
PENDING_FILE = MEMORY_DIR / "pending_updates.json"
IMPROVE_LOG = MEMORY_DIR / "improvement_log.json"

# Map domains to files that might need updating
DOMAIN_TO_FILES = {
    "scraping":      [WORKSPACE / "skills" / "scrapling" / "SKILL.md"],
    "social":        [WORKSPACE / "TOOLS.md"],
    "coding":        [WORKSPACE / "AGENTS.md"],
    "communication": [WORKSPACE / "SOUL.md", WORKSPACE / "AGENTS.md"],
    "memory":        [WORKSPACE / "AGENTS.md", WORKSPACE / "HEARTBEAT.md"],
    "tools":         [WORKSPACE / "TOOLS.md"],
    "pipeline":      [WORKSPACE / "AGENTS.md"],
    "product":       [WORKSPACE / "MEMORY.md"],
    "general":       [WORKSPACE / "MEMORY.md"],
}


# ============================================================
# PENDING UPDATES STORE
# ============================================================

def load_pending() -> list:
    if PENDING_FILE.exists():
        return json.loads(PENDING_FILE.read_text())
    return []

def save_pending(updates: list):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(updates, indent=2))

def load_improve_log() -> list:
    if IMPROVE_LOG.exists():
        return json.loads(IMPROVE_LOG.read_text())
    return []

def save_improve_log(log: list):
    IMPROVE_LOG.write_text(json.dumps(log[-200:], indent=2))


# ============================================================
# POINT 2: CONSOLIDATE — extract patterns from outcomes
# ============================================================

def consolidate_outcomes(outcomes_by_domain: dict) -> list:
    """
    Analyze outcomes and extract patterns / lessons.
    Returns a list of proposed updates.
    """
    proposals = []

    for domain, data in outcomes_by_domain.items():
        successes = data.get("successes", [])
        failures = data.get("failures", [])
        partials = data.get("partials", [])

        if not successes and not failures:
            continue

        # Extract patterns from failures
        for fail in failures:
            # Turn each failure into a "warning" or "fix"
            proposal = {
                "id": f"{domain}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{abs(hash(fail)) % 10000}",
                "type": "warning",
                "domain": domain,
                "trigger": fail,
                "proposed_addition": _failure_to_warning(fail, domain),
                "target_files": [str(f) for f in DOMAIN_TO_FILES.get(domain, [WORKSPACE / "MEMORY.md"])],
                "created_at": datetime.now().isoformat(),
                "status": "pending",
                "source_outcome": "fail",
            }
            if proposal["proposed_addition"]:
                proposals.append(proposal)

        # Extract patterns from successes
        if len(successes) >= 2:
            # Multiple successes in a domain = there's a working pattern worth documenting
            combined = "; ".join(successes[-3:])
            proposal = {
                "id": f"{domain}_{datetime.now().strftime('%Y%m%d%H%M%S')}_pattern",
                "type": "pattern",
                "domain": domain,
                "trigger": combined,
                "proposed_addition": _successes_to_pattern(successes, domain),
                "target_files": [str(f) for f in DOMAIN_TO_FILES.get(domain, [WORKSPACE / "MEMORY.md"])],
                "created_at": datetime.now().isoformat(),
                "status": "pending",
                "source_outcome": "success",
            }
            if proposal["proposed_addition"]:
                proposals.append(proposal)

    return proposals


def _failure_to_warning(fail: str, domain: str) -> str:
    """Convert a failure description into a warning note."""
    fail = fail.strip().lower()

    # Common patterns → structured warnings
    if "cookie" in fail or "auth" in fail or "login" in fail:
        return f"⚠️ Auth issue encountered: {fail}. Double-check cookie format and token expiry."
    if "timeout" in fail or "hang" in fail:
        return f"⚠️ Timeout pattern in {domain}: {fail}. Add explicit timeouts."
    if "block" in fail or "403" in fail or "bot" in fail:
        return f"⚠️ Anti-bot block in {domain}: {fail}. Use StealthyFetcher or add delays."
    if "module" in fail or "import" in fail or "install" in fail:
        return f"⚠️ Dependency issue: {fail}. Verify venv and install with [all] extras."
    if "rate limit" in fail or "429" in fail:
        return f"⚠️ Rate limit hit: {fail}. Add backoff/retry logic."
    if "format" in fail or "schema" in fail or "type" in fail:
        return f"⚠️ Format mismatch: {fail}. Verify expected input/output schema."

    # Generic failure
    return f"⚠️ Known failure: {fail}"


def _successes_to_pattern(successes: list, domain: str) -> str:
    """Summarize a cluster of successes into a reusable pattern note."""
    if not successes:
        return ""

    # Look for common keywords
    all_text = " ".join(successes).lower()

    pattern_lines = [f"✅ Confirmed working patterns in [{domain.upper()}]:"]
    for s in successes[-5:]:
        pattern_lines.append(f"  - {s[:100]}")

    return "\n".join(pattern_lines)


# ============================================================
# POINT 3: APPLY — update docs with proposed changes
# ============================================================

def apply_update(update: dict, dry_run: bool = False) -> bool:
    """Apply a single pending update to its target files."""
    if not update.get("proposed_addition"):
        print(f"  ⚠️  No content to apply for {update['id']}")
        return False

    applied_to = []

    for file_path_str in update.get("target_files", []):
        file_path = Path(file_path_str)
        if not file_path.exists():
            print(f"  ⚠️  File not found: {file_path}")
            continue

        content = file_path.read_text()

        # Avoid duplicates — check if the core insight is already there
        addition = update["proposed_addition"]
        core = update["trigger"][:40].lower()
        if core in content.lower():
            print(f"  ↩️  Already in {file_path.name}, skipping duplicate")
            continue

        # Find appropriate section or append
        section_header = _find_section(file_path.name, update["domain"], update["type"])
        new_content = _insert_update(content, addition, section_header)

        if dry_run:
            print(f"\n  📄 Would update: {file_path}")
            print(f"  Section: {section_header}")
            print(f"  Addition:\n{addition}")
        else:
            file_path.write_text(new_content)
            print(f"  ✅ Updated: {file_path.name}")
            applied_to.append(str(file_path))

    if applied_to and not dry_run:
        # Git commit the changes
        try:
            subprocess.run(
                ["git", "add"] + applied_to,
                cwd=str(WORKSPACE),
                capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"self-improve: {update['type']} update for [{update['domain']}]"],
                cwd=str(WORKSPACE),
                capture_output=True
            )
            print(f"  📦 Committed to git")
        except Exception as e:
            print(f"  ⚠️  Git commit failed: {e}")

        return True

    return len(applied_to) > 0 or dry_run


def _find_section(filename: str, domain: str, update_type: str) -> str:
    """Determine which section header to insert under."""
    if "SKILL.md" in filename:
        if update_type == "warning":
            return "## Notes"
        return "## Common Patterns"
    if "TOOLS.md" in filename:
        return f"## {domain.title()}"
    if "AGENTS.md" in filename:
        if update_type == "warning":
            return "## Safety"
        return "## Make It Yours"
    if "MEMORY.md" in filename:
        return "## Lessons Learned"
    if "SOUL.md" in filename:
        return "## Vibe"
    return "## Notes"


def _insert_update(content: str, addition: str, section_header: str) -> str:
    """
    Insert addition under section_header. If section not found, append to end.
    """
    lines = content.split("\n")
    insert_idx = None

    for i, line in enumerate(lines):
        if line.strip().startswith(section_header.strip()):
            # Find the end of this section (next ## header or EOF)
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            # Insert before the next section (or at end)
            insert_idx = j
            break

    timestamp = datetime.now().strftime("%Y-%m-%d")
    tagged_addition = f"\n<!-- self-improve:{timestamp} -->\n{addition}\n"

    if insert_idx is not None:
        lines.insert(insert_idx, tagged_addition)
    else:
        lines.append(f"\n{section_header}\n{tagged_addition}")

    return "\n".join(lines)


# ============================================================
# POINT 4: LOOP — the full cycle
# ============================================================

def run_cycle(auto_apply: bool = False, dry_run: bool = False) -> dict:
    """
    Full self-improvement cycle:
    1. Load outcomes from the last 7 days
    2. Consolidate into patterns/warnings
    3. Generate pending updates
    4. Optionally auto-apply
    """
    print("🔄 PINCH Self-Improvement Cycle")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    # Step 1: Load outcomes
    outcomes = export_for_improvement()
    total_outcomes = sum(
        len(v["successes"]) + len(v["failures"]) + len(v["partials"])
        for v in outcomes.values()
    )
    print(f"📥 Loaded {total_outcomes} outcomes across {len(outcomes)} domains")

    if total_outcomes == 0:
        print("   No outcomes logged yet. Start logging with: uv run outcome.py log ...")
        return {"status": "no_outcomes"}

    for domain, data in outcomes.items():
        s = len(data["successes"])
        f = len(data["failures"])
        p = len(data["partials"])
        print(f"   [{domain}] ✅{s} ❌{f} ⚡{p}")

    # Step 2: Consolidate
    print(f"\n🧠 Consolidating patterns...")
    proposals = consolidate_outcomes(outcomes)
    print(f"   Generated {len(proposals)} update proposals")

    if not proposals:
        print("   Nothing new to propose.")
        return {"status": "nothing_new"}

    # Step 3: Merge with existing pending (avoid duplicates)
    existing_pending = load_pending()
    existing_ids = {p["id"] for p in existing_pending}

    new_proposals = [p for p in proposals if p["id"] not in existing_ids]
    all_pending = existing_pending + new_proposals
    save_pending(all_pending)
    print(f"   Added {len(new_proposals)} new proposals to queue ({len(all_pending)} total pending)")

    # Step 4: Apply
    results = {"proposed": len(new_proposals), "applied": 0, "skipped": 0}

    if auto_apply or dry_run:
        print(f"\n{'🔍 Dry run' if dry_run else '⚡ Auto-applying'} updates...")
        for update in new_proposals:
            print(f"\n  [{update['type'].upper()}] {update['domain']} — {update['trigger'][:60]}...")
            success = apply_update(update, dry_run=dry_run)
            if success:
                results["applied"] += 1
                if not dry_run:
                    update["status"] = "applied"
                    update["applied_at"] = datetime.now().isoformat()
            else:
                results["skipped"] += 1
    else:
        print(f"\n📋 {len(new_proposals)} updates queued for review.")
        print("   Run: uv run self_improve.py pending   — to review")
        print("   Run: uv run self_improve.py apply     — to apply all")

    # Save updated pending
    save_pending(all_pending)

    # Log the cycle
    log = load_improve_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "outcomes_processed": total_outcomes,
        "proposals_generated": len(proposals),
        "applied": results["applied"],
    })
    save_improve_log(log)

    print(f"\n{'='*60}")
    print(f"✅ Cycle complete — {results['proposed']} proposed, {results['applied']} applied")

    return results


def show_pending():
    """Display all pending updates."""
    pending = [p for p in load_pending() if p.get("status") == "pending"]

    if not pending:
        print("No pending updates.")
        return

    print(f"\n📋 Pending Doc Updates ({len(pending)})")
    print("=" * 60)

    for p in pending:
        icon = "⚠️" if p["type"] == "warning" else "✅"
        print(f"\n[{p['id']}]")
        print(f"  {icon} Type: {p['type']} | Domain: {p['domain']}")
        print(f"  Trigger: {p['trigger'][:80]}")
        print(f"  Files: {', '.join(Path(f).name for f in p['target_files'])}")
        print(f"  Addition:\n    {p['proposed_addition'][:200].replace(chr(10), chr(10)+'    ')}")
        print(f"  Created: {p['created_at'][:16]}")


def apply_all(target_id: str = None):
    """Apply pending updates (all or specific ID)."""
    pending = load_pending()
    to_apply = [p for p in pending if p.get("status") == "pending"]

    if target_id:
        to_apply = [p for p in to_apply if p["id"] == target_id]

    if not to_apply:
        print("Nothing to apply.")
        return

    print(f"Applying {len(to_apply)} update(s)...")
    applied = 0
    for update in to_apply:
        print(f"\n  Applying [{update['id']}]...")
        success = apply_update(update, dry_run=False)
        if success:
            update["status"] = "applied"
            update["applied_at"] = datetime.now().isoformat()
            applied += 1

    save_pending(pending)
    print(f"\n✅ Applied {applied}/{len(to_apply)} updates")


def dismiss_update(target_id: str):
    """Dismiss a pending update without applying."""
    pending = load_pending()
    for p in pending:
        if p["id"] == target_id:
            p["status"] = "dismissed"
            p["dismissed_at"] = datetime.now().isoformat()
            save_pending(pending)
            print(f"Dismissed: {target_id}")
            return
    print(f"ID not found: {target_id}")


def show_status():
    """Show overall improvement stats."""
    log = load_improve_log()
    pending = load_pending()
    pending_count = sum(1 for p in pending if p.get("status") == "pending")
    applied_count = sum(1 for p in pending if p.get("status") == "applied")
    dismissed_count = sum(1 for p in pending if p.get("status") == "dismissed")

    print("\n📊 Self-Improvement Status")
    print("=" * 50)
    print(f"  Pending updates:   {pending_count}")
    print(f"  Applied updates:   {applied_count}")
    print(f"  Dismissed:         {dismissed_count}")
    print(f"  Cycles run:        {len(log)}")

    if log:
        last = log[-1]
        print(f"\n  Last cycle: {last['timestamp'][:16]}")
        print(f"    Outcomes processed: {last.get('outcomes_processed', 0)}")
        print(f"    Proposals generated: {last.get('proposals_generated', 0)}")
        print(f"    Applied: {last.get('applied', 0)}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PINCH Self-Improvement Engine")
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="Run improvement cycle")
    run_p.add_argument("--auto-apply", action="store_true", help="Auto-apply all proposals")
    run_p.add_argument("--dry-run", action="store_true", help="Show what would be applied")

    subparsers.add_parser("pending", help="Show pending updates")

    apply_p = subparsers.add_parser("apply", help="Apply pending updates")
    apply_p.add_argument("--id", default=None, help="Apply specific update ID")

    dismiss_p = subparsers.add_parser("dismiss", help="Dismiss a pending update")
    dismiss_p.add_argument("--id", required=True)

    subparsers.add_parser("status", help="Show improvement stats")

    args = parser.parse_args()

    if args.command == "run":
        run_cycle(auto_apply=args.auto_apply, dry_run=args.dry_run)
    elif args.command == "pending":
        show_pending()
    elif args.command == "apply":
        apply_all(target_id=args.id)
    elif args.command == "dismiss":
        dismiss_update(args.id)
    elif args.command == "status":
        show_status()
    else:
        parser.print_help()
