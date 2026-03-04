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
PINCH Reflection System — Learning from experience.

Transforms raw episodic memories into:
1. Lessons learned (semantic knowledge)
2. Paradigm updates (belief changes)
3. Skills/procedures (how-to knowledge)
4. Warnings (things to avoid)

Uses local LLM for deep reflection.
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_graph import (
    get_db, add_memory, recall, get_stats,
    add_bond, load_graph, save_graph, get_all_strengths
)
try:
    from llm_client import complete, is_sonnet_available, is_local_available
    is_available = lambda: is_sonnet_available() or is_local_available()
except ImportError:
    from local_llm import is_available, complete
try:
    from skills_progression import record_learning_event, assess_skill_from_experience
    SKILLS_AVAILABLE = True
except:
    SKILLS_AVAILABLE = False

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
BELIEFS_FILE = MEMORY_DIR / "beliefs.json"
PARADIGMS_FILE = MEMORY_DIR / "paradigms.json"
REFLECTION_LOG = MEMORY_DIR / "reflection_log.json"


# ============================================================
# BELIEF & PARADIGM TRACKING
# ============================================================

def load_beliefs() -> dict:
    """Load current beliefs/understanding."""
    if BELIEFS_FILE.exists():
        return json.loads(BELIEFS_FILE.read_text())
    return {
        "core_beliefs": [],      # Fundamental truths I hold
        "mental_models": [],     # How I understand things work
        "skills": [],            # Things I know how to do
        "warnings": [],          # Things I've learned to avoid
        "updated_at": None
    }

def save_beliefs(beliefs: dict):
    """Save beliefs to disk."""
    beliefs["updated_at"] = datetime.now().isoformat()
    BELIEFS_FILE.write_text(json.dumps(beliefs, indent=2))

def load_paradigms() -> list:
    """Load paradigm shift history."""
    if PARADIGMS_FILE.exists():
        return json.loads(PARADIGMS_FILE.read_text())
    return []

def save_paradigms(paradigms: list):
    """Save paradigm history."""
    PARADIGMS_FILE.write_text(json.dumps(paradigms, indent=2))

def add_belief(category: str, belief: str, source_memory: str = None):
    """Add a new belief/skill/warning."""
    beliefs = load_beliefs()
    
    entry = {
        "belief": belief,
        "added_at": datetime.now().isoformat(),
        "source": source_memory
    }
    
    if category in beliefs:
        # Check for duplicates
        existing = [b["belief"].lower() for b in beliefs[category]]
        if belief.lower() not in existing:
            beliefs[category].append(entry)
            save_beliefs(beliefs)
            return True
    return False

def record_paradigm_shift(old_belief: str, new_belief: str, trigger: str, reasoning: str):
    """Record a paradigm shift — when understanding fundamentally changes."""
    paradigms = load_paradigms()
    
    paradigms.append({
        "timestamp": datetime.now().isoformat(),
        "old_belief": old_belief,
        "new_belief": new_belief,
        "trigger": trigger,
        "reasoning": reasoning
    })
    
    save_paradigms(paradigms)


def extract_skill_learning(memory_content: str) -> dict:
    """Use LLM to identify if an experience contributes to skill progression."""
    if not is_available():
        return {"has_learning": False}
    
    prompt = f"""Does this experience contribute to learning in any of these skill areas?

Experience: {memory_content[:400]}

Skill areas:
1. marketing_gtm - Marketing, audience building, growth, launches
2. video_creation - Video production, editing, visual storytelling
3. product_development - Building products, shipping, iteration

Reply in format:
SKILL: <skill_id or "none">
XP: <1-30 based on learning value>
DESCRIPTION: <what was learned>"""

    try:
        response = complete(prompt, max_tokens=100, temperature=0.3)
        
        skill = None
        xp = 0
        description = ""
        
        for line in response.strip().split("\n"):
            if line.startswith("SKILL:"):
                s = line[6:].strip().lower()
                if s in ["marketing_gtm", "video_creation", "product_development"]:
                    skill = s
            elif line.startswith("XP:"):
                try:
                    xp = int(line[3:].strip().split()[0])
                    xp = max(1, min(30, xp))
                except:
                    pass
            elif line.startswith("DESCRIPTION:"):
                description = line[12:].strip()
        
        if skill and xp > 0:
            return {
                "has_learning": True,
                "skill": skill,
                "xp": xp,
                "description": description
            }
        return {"has_learning": False}
    except:
        return {"has_learning": False}


# ============================================================
# REFLECTION ENGINE
# ============================================================

def extract_lesson(memory_content: str) -> dict:
    """Use LLM to extract lessons from a memory."""
    prompt = f"""Reflect on this experience and extract learnings.

Experience: {memory_content[:500]}

Answer these questions:
1. LESSON: What's the key takeaway? (one sentence)
2. TYPE: Is this a [fact/skill/warning/belief/paradigm_shift]?
3. GENERALIZABLE: Can this apply to other situations? (yes/no)
4. IMPORTANCE: Rate 1-10 how significant this learning is
5. ACTION: What should I do differently in the future? (if applicable)

Format your response as:
LESSON: ...
TYPE: ...
GENERALIZABLE: ...
IMPORTANCE: ...
ACTION: ..."""

    response = complete(prompt, max_tokens=300, temperature=0.4)
    
    # Parse response
    result = {
        "lesson": "",
        "type": "fact",
        "generalizable": False,
        "importance": 5,
        "action": ""
    }
    
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("LESSON:"):
            result["lesson"] = line[7:].strip()
        elif line.startswith("TYPE:"):
            t = line[5:].strip().lower()
            if t in ["fact", "skill", "warning", "belief", "paradigm_shift"]:
                result["type"] = t
        elif line.startswith("GENERALIZABLE:"):
            result["generalizable"] = "yes" in line.lower()
        elif line.startswith("IMPORTANCE:"):
            try:
                result["importance"] = int(line[11:].strip().split()[0])
            except:
                pass
        elif line.startswith("ACTION:"):
            result["action"] = line[7:].strip()
    
    return result


def check_paradigm_conflict(new_lesson: str, beliefs: dict) -> dict:
    """Check if a new lesson conflicts with existing beliefs."""
    existing = []
    for category in ["core_beliefs", "mental_models", "warnings"]:
        for b in beliefs.get(category, []):
            existing.append(b["belief"])
    
    if not existing:
        return {"conflict": False}
    
    prompt = f"""Does this new learning conflict with any existing beliefs?

New learning: {new_lesson}

Existing beliefs:
{chr(10).join(f"- {b}" for b in existing[:15])}

If there's a conflict:
1. Which belief does it conflict with?
2. Which one is more likely correct given the new evidence?
3. Should the old belief be updated?

Reply in format:
CONFLICT: yes/no
OLD_BELIEF: (the conflicting belief, or "none")
RESOLUTION: keep_old / update_to_new / both_valid
REASONING: (brief explanation)"""

    response = complete(prompt, max_tokens=200, temperature=0.3)
    
    result = {
        "conflict": False,
        "old_belief": None,
        "resolution": "keep_old",
        "reasoning": ""
    }
    
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("CONFLICT:"):
            result["conflict"] = "yes" in line.lower()
        elif line.startswith("OLD_BELIEF:"):
            old = line[11:].strip()
            if old.lower() != "none":
                result["old_belief"] = old
        elif line.startswith("RESOLUTION:"):
            res = line[11:].strip().lower()
            if res in ["keep_old", "update_to_new", "both_valid"]:
                result["resolution"] = res
        elif line.startswith("REASONING:"):
            result["reasoning"] = line[10:].strip()
    
    return result


def reflect_on_memory(memory_content: str, memory_id: str = None) -> dict:
    """Full reflection on a single memory."""
    if not is_available():
        return {"error": "LLM not available"}
    
    # Extract lesson
    lesson = extract_lesson(memory_content)
    
    if lesson["importance"] < 4:
        return {"status": "skipped", "reason": "low importance", "lesson": lesson}
    
    # Load current beliefs
    beliefs = load_beliefs()
    
    # Check for conflicts
    if lesson["lesson"]:
        conflict = check_paradigm_conflict(lesson["lesson"], beliefs)
    else:
        conflict = {"conflict": False}
    
    result = {
        "status": "reflected",
        "lesson": lesson,
        "conflict": conflict,
        "actions_taken": []
    }
    
    # Take actions based on reflection
    if lesson["type"] == "warning" and lesson["lesson"]:
        added = add_belief("warnings", lesson["lesson"], memory_id)
        if added:
            result["actions_taken"].append(f"Added warning: {lesson['lesson'][:50]}...")
    
    elif lesson["type"] == "skill" and lesson["action"]:
        added = add_belief("skills", lesson["action"], memory_id)
        if added:
            result["actions_taken"].append(f"Added skill: {lesson['action'][:50]}...")
    
    elif lesson["type"] == "belief" and lesson["lesson"]:
        added = add_belief("core_beliefs", lesson["lesson"], memory_id)
        if added:
            result["actions_taken"].append(f"Added belief: {lesson['lesson'][:50]}...")
    
    elif lesson["type"] == "paradigm_shift" and conflict["conflict"]:
        if conflict["resolution"] == "update_to_new":
            record_paradigm_shift(
                old_belief=conflict["old_belief"],
                new_belief=lesson["lesson"],
                trigger=memory_content[:200],
                reasoning=conflict["reasoning"]
            )
            result["actions_taken"].append(f"Paradigm shift: {conflict['old_belief'][:30]}... → {lesson['lesson'][:30]}...")
    
    # Store the extracted lesson as semantic memory
    if lesson["lesson"] and lesson["importance"] >= 6:
        lesson_id = add_memory(
            content=lesson["lesson"],
            category="semantic",
            tier="long" if lesson["importance"] >= 8 else "short",
            source="reflection",
            metadata={"reflected_from": memory_id, "type": lesson["type"]},
            initial_strength=lesson["importance"] / 10.0
        )
        result["actions_taken"].append(f"Created semantic memory from lesson")
        
        # Bond the lesson to the source memory
        if memory_id:
            add_bond(memory_id, lesson_id, weight=0.5, bond_type="reflection")
    
    # Check for skill learning
    if SKILLS_AVAILABLE:
        skill_learning = extract_skill_learning(memory_content)
        if skill_learning.get("has_learning"):
            skill_result = record_learning_event(
                skill_learning["skill"],
                skill_learning["description"] or f"Learned from: {memory_content[:50]}...",
                skill_learning["xp"],
                source="reflection"
            )
            result["actions_taken"].append(
                f"Skill XP: +{skill_result['xp_gained']} to {skill_result['skill']} ({skill_result['level']})"
            )
            if skill_result.get("level_up"):
                result["actions_taken"].append(
                    f"🎉 LEVEL UP: {skill_result['level_up_from']} → {skill_result['level_up_to']}"
                )
    
    return result


def run_reflection_cycle(hours_back: int = 24, max_memories: int = 20):
    """Run reflection on recent significant memories."""
    print("🪞 PINCH Reflection Cycle")
    print("=" * 50)
    
    if not is_available():
        print("❌ Local LLM not available")
        return
    
    print("✅ Local LLM connected")
    
    # Get recent episodic memories
    db = get_db()
    if "memories" not in db.table_names():
        print("No memories to reflect on")
        return
    
    table = db.open_table("memories")
    df = table.to_pandas()
    df = df[df["id"] != "__init__"]
    df = df[df["category"] == "episodic"]
    
    # Filter by time
    cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
    df = df[df["created_at"] >= cutoff]
    
    # Get strengths for sorting
    strengths = get_all_strengths()
    
    memories_to_reflect = []
    for _, row in df.iterrows():
        state = strengths.get(row["id"], {})
        strength = state.get("strength", row.get("strength", 0.5))
        access_count = state.get("access_count", 0)
        
        # Prioritize frequently accessed or high-strength memories
        score = strength + (access_count * 0.1)
        memories_to_reflect.append({
            "id": row["id"],
            "content": row["content"],
            "score": score
        })
    
    # Sort by score and take top
    memories_to_reflect.sort(key=lambda x: x["score"], reverse=True)
    memories_to_reflect = memories_to_reflect[:max_memories]
    
    print(f"📝 Reflecting on {len(memories_to_reflect)} recent memories...\n")
    
    results = {
        "reflected": 0,
        "skipped": 0,
        "lessons_extracted": 0,
        "beliefs_added": 0,
        "paradigm_shifts": 0
    }
    
    for mem in memories_to_reflect:
        print(f"  🔍 {mem['content'][:60]}...")
        result = reflect_on_memory(mem["content"], mem["id"])
        
        if result.get("status") == "reflected":
            results["reflected"] += 1
            if result["lesson"].get("lesson"):
                results["lessons_extracted"] += 1
                print(f"     → Lesson: {result['lesson']['lesson'][:50]}...")
            
            for action in result.get("actions_taken", []):
                print(f"     → {action}")
                if "belief" in action.lower() or "warning" in action.lower() or "skill" in action.lower():
                    results["beliefs_added"] += 1
                if "paradigm" in action.lower():
                    results["paradigm_shifts"] += 1
        else:
            results["skipped"] += 1
        
        print()
    
    # Summary
    print("=" * 50)
    print("📊 Reflection Summary")
    print(f"   Memories reflected: {results['reflected']}")
    print(f"   Skipped (low importance): {results['skipped']}")
    print(f"   Lessons extracted: {results['lessons_extracted']}")
    print(f"   Beliefs/skills/warnings added: {results['beliefs_added']}")
    print(f"   Paradigm shifts: {results['paradigm_shifts']}")
    
    # Log the reflection
    log = load_reflection_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "hours_back": hours_back,
        "results": results
    })
    save_reflection_log(log)
    
    return results


def load_reflection_log() -> list:
    if REFLECTION_LOG.exists():
        return json.loads(REFLECTION_LOG.read_text())
    return []

def save_reflection_log(log: list):
    REFLECTION_LOG.write_text(json.dumps(log[-100:], indent=2))  # Keep last 100


def show_beliefs():
    """Display current beliefs and understanding."""
    beliefs = load_beliefs()
    paradigms = load_paradigms()
    
    print("\n🧠 PINCH Current Understanding")
    print("=" * 50)
    
    if beliefs.get("core_beliefs"):
        print("\n💡 Core Beliefs:")
        for b in beliefs["core_beliefs"][-10:]:
            print(f"  • {b['belief']}")
    
    if beliefs.get("mental_models"):
        print("\n🔧 Mental Models:")
        for b in beliefs["mental_models"][-10:]:
            print(f"  • {b['belief']}")
    
    if beliefs.get("skills"):
        print("\n🎯 Skills/Procedures:")
        for b in beliefs["skills"][-10:]:
            print(f"  • {b['belief']}")
    
    if beliefs.get("warnings"):
        print("\n⚠️ Warnings (things to avoid):")
        for b in beliefs["warnings"][-10:]:
            print(f"  • {b['belief']}")
    
    if paradigms:
        print("\n🔄 Recent Paradigm Shifts:")
        for p in paradigms[-5:]:
            print(f"  • {p['old_belief'][:30]}... → {p['new_belief'][:30]}...")
            print(f"    Reason: {p['reasoning'][:50]}...")
    
    print(f"\nLast updated: {beliefs.get('updated_at', 'never')}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("PINCH Reflection System")
        print()
        print("Commands:")
        print("  reflect [hours]   Reflect on recent memories (default: 24h)")
        print("  beliefs           Show current beliefs and understanding")
        print("  paradigms         Show paradigm shift history")
        print("  test <text>       Test reflection on a piece of text")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "reflect":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        run_reflection_cycle(hours_back=hours)
    
    elif cmd == "beliefs":
        show_beliefs()
    
    elif cmd == "paradigms":
        paradigms = load_paradigms()
        print("\n🔄 Paradigm Shift History")
        print("=" * 50)
        for p in paradigms:
            print(f"\n[{p['timestamp'][:10]}]")
            print(f"  Old: {p['old_belief']}")
            print(f"  New: {p['new_belief']}")
            print(f"  Trigger: {p['trigger'][:100]}...")
            print(f"  Reason: {p['reasoning']}")
    
    elif cmd == "test":
        if len(sys.argv) < 3:
            print("Usage: reflection.py test <text to reflect on>")
            sys.exit(1)
        text = " ".join(sys.argv[2:])
        result = reflect_on_memory(text)
        print(json.dumps(result, indent=2))
    
    else:
        print(f"Unknown command: {cmd}")
