#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
"""
PINCH Goal System — Belief-driven, hierarchical goals.

Goals flow from beliefs:
  Core Beliefs → Vision → Strategic → Tactical

Properties:
- alignment: How well does this serve core beliefs?
- timeframe: vision / strategic / tactical
- parent: Higher-level goal this serves
- status: active / completed / abandoned / blocked
- progress: 0-100
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
GOALS_FILE = MEMORY_DIR / "goals_system.json"
BELIEFS_FILE = MEMORY_DIR / "beliefs.json"

# Import local LLM for alignment scoring
import sys
sys.path.insert(0, str(Path(__file__).parent))
try:
    from local_llm import is_available, complete
    LLM_AVAILABLE = is_available()
except:
    LLM_AVAILABLE = False


def load_goals() -> dict:
    """Load goal system from disk."""
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text())
    return {
        "vision": [],      # Long-term direction (months-years)
        "strategic": [],   # Medium-term objectives (weeks-months)
        "tactical": [],    # Immediate actions (days-weeks)
        "completed": [],   # Archive of completed goals
        "abandoned": [],   # Archive of abandoned goals
        "updated_at": None
    }

def save_goals(goals: dict):
    """Save goal system to disk."""
    goals["updated_at"] = datetime.now().isoformat()
    GOALS_FILE.write_text(json.dumps(goals, indent=2))

def load_beliefs() -> dict:
    """Load beliefs for alignment checking."""
    if BELIEFS_FILE.exists():
        return json.loads(BELIEFS_FILE.read_text())
    return {"core_beliefs": [], "mental_models": [], "skills": [], "warnings": []}


def generate_goal_id() -> str:
    """Generate unique goal ID."""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def calculate_alignment(goal_text: str, beliefs: dict) -> float:
    """Calculate how well a goal aligns with core beliefs using LLM."""
    if not LLM_AVAILABLE:
        return 0.7  # Default if no LLM
    
    belief_list = []
    for category in ["core_beliefs", "mental_models"]:
        for b in beliefs.get(category, []):
            belief_list.append(b.get("belief", b) if isinstance(b, dict) else b)
    
    if not belief_list:
        return 0.8  # No beliefs to compare against
    
    prompt = f"""Rate how well this goal aligns with these core beliefs (0-10).

Goal: {goal_text}

Core Beliefs:
{chr(10).join(f"- {b}" for b in belief_list[:10])}

Consider:
- Does pursuing this goal honor these beliefs?
- Is this goal consistent with who I am?
- Would achieving this goal strengthen or contradict my values?

Reply with just a number 0-10:"""
    
    try:
        response = complete(prompt, max_tokens=10, temperature=0.2)
        score = float(response.strip().split()[0])
        return min(max(score / 10.0, 0), 1)
    except:
        return 0.7


def add_goal(
    text: str,
    timeframe: str = "tactical",  # vision / strategic / tactical
    parent_id: str = None,
    auto_align: bool = True
) -> dict:
    """Add a new goal."""
    goals = load_goals()
    beliefs = load_beliefs()
    
    goal = {
        "id": generate_goal_id(),
        "text": text,
        "timeframe": timeframe,
        "parent_id": parent_id,
        "status": "active",
        "progress": 0,
        "alignment": calculate_alignment(text, beliefs) if auto_align else 0.7,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "notes": []
    }
    
    if timeframe in goals:
        goals[timeframe].append(goal)
    else:
        goals["tactical"].append(goal)
    
    save_goals(goals)
    return goal


def update_goal(goal_id: str, **updates) -> Optional[dict]:
    """Update a goal's properties."""
    goals = load_goals()
    
    for timeframe in ["vision", "strategic", "tactical"]:
        for goal in goals.get(timeframe, []):
            if goal["id"] == goal_id:
                for key, value in updates.items():
                    if key in goal:
                        goal[key] = value
                goal["updated_at"] = datetime.now().isoformat()
                save_goals(goals)
                return goal
    
    return None


def complete_goal(goal_id: str, notes: str = None) -> Optional[dict]:
    """Mark a goal as completed."""
    goals = load_goals()
    
    for timeframe in ["vision", "strategic", "tactical"]:
        for i, goal in enumerate(goals.get(timeframe, [])):
            if goal["id"] == goal_id:
                goal["status"] = "completed"
                goal["progress"] = 100
                goal["completed_at"] = datetime.now().isoformat()
                if notes:
                    goal["notes"].append({"text": notes, "at": datetime.now().isoformat()})
                
                # Move to completed archive
                goals["completed"].append(goal)
                goals[timeframe].pop(i)
                
                save_goals(goals)
                return goal
    
    return None


def get_active_goals(timeframe: str = None) -> list:
    """Get active goals, optionally filtered by timeframe."""
    goals = load_goals()
    
    active = []
    timeframes = [timeframe] if timeframe else ["vision", "strategic", "tactical"]
    
    for tf in timeframes:
        for goal in goals.get(tf, []):
            if goal.get("status") == "active":
                active.append(goal)
    
    # Sort by alignment (highest first)
    active.sort(key=lambda g: g.get("alignment", 0), reverse=True)
    return active


def get_goal_tree() -> dict:
    """Get goals organized as a tree (vision → strategic → tactical)."""
    goals = load_goals()
    
    tree = {"vision": []}
    
    # Build vision-level goals
    for vision in goals.get("vision", []):
        if vision.get("status") != "active":
            continue
        
        node = {
            "goal": vision,
            "children": []
        }
        
        # Find strategic goals that serve this vision
        for strategic in goals.get("strategic", []):
            if strategic.get("status") != "active":
                continue
            if strategic.get("parent_id") == vision["id"]:
                strat_node = {
                    "goal": strategic,
                    "children": []
                }
                
                # Find tactical goals that serve this strategic goal
                for tactical in goals.get("tactical", []):
                    if tactical.get("status") != "active":
                        continue
                    if tactical.get("parent_id") == strategic["id"]:
                        strat_node["children"].append({"goal": tactical})
                
                node["children"].append(strat_node)
        
        tree["vision"].append(node)
    
    # Add orphan strategic goals (no parent)
    tree["orphan_strategic"] = []
    for strategic in goals.get("strategic", []):
        if strategic.get("status") != "active":
            continue
        if not strategic.get("parent_id"):
            tree["orphan_strategic"].append({"goal": strategic})
    
    # Add orphan tactical goals (no parent)
    tree["orphan_tactical"] = []
    for tactical in goals.get("tactical", []):
        if tactical.get("status") != "active":
            continue
        if not tactical.get("parent_id"):
            tree["orphan_tactical"].append({"goal": tactical})
    
    return tree


def derive_goals_from_beliefs() -> list:
    """Use LLM to suggest goals based on current beliefs."""
    if not LLM_AVAILABLE:
        print("LLM not available for goal derivation")
        return []
    
    beliefs = load_beliefs()
    goals = load_goals()
    
    # Collect current beliefs and existing goals
    belief_list = []
    for category in ["core_beliefs", "mental_models"]:
        for b in beliefs.get(category, []):
            belief_list.append(b.get("belief", b) if isinstance(b, dict) else b)
    
    existing = []
    for tf in ["vision", "strategic", "tactical"]:
        for g in goals.get(tf, []):
            if g.get("status") == "active":
                existing.append(f"[{tf}] {g['text']}")
    
    prompt = f"""Based on these core beliefs, suggest 3 goals that would be aligned.

Core Beliefs:
{chr(10).join(f"- {b}" for b in belief_list[:10])}

Existing Goals:
{chr(10).join(f"- {g}" for g in existing[:10]) if existing else "None yet"}

Suggest 3 new goals (one vision, one strategic, one tactical) that:
1. Honor these beliefs
2. Don't duplicate existing goals
3. Are specific and actionable

Format:
VISION: [long-term goal]
STRATEGIC: [medium-term objective]
TACTICAL: [immediate action]"""
    
    try:
        response = complete(prompt, max_tokens=300, temperature=0.7)
        
        suggestions = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("VISION:"):
                suggestions.append({"timeframe": "vision", "text": line[7:].strip()})
            elif line.startswith("STRATEGIC:"):
                suggestions.append({"timeframe": "strategic", "text": line[10:].strip()})
            elif line.startswith("TACTICAL:"):
                suggestions.append({"timeframe": "tactical", "text": line[9:].strip()})
        
        return suggestions
    except Exception as e:
        print(f"Error deriving goals: {e}")
        return []


def print_goals():
    """Display current goal hierarchy."""
    goals = load_goals()
    
    print("\n🎯 PINCH Goal System")
    print("=" * 50)
    
    # Vision
    print("\n## 🔭 Vision (Long-term)")
    vision_goals = [g for g in goals.get("vision", []) if g.get("status") == "active"]
    if vision_goals:
        for g in vision_goals:
            align = g.get("alignment", 0) * 100
            print(f"  [{align:.0f}%] {g['text']}")
    else:
        print("  (no vision goals set)")
    
    # Strategic
    print("\n## 🎯 Strategic (Medium-term)")
    strat_goals = [g for g in goals.get("strategic", []) if g.get("status") == "active"]
    if strat_goals:
        for g in strat_goals:
            align = g.get("alignment", 0) * 100
            parent = f" → serves {g['parent_id'][:8]}" if g.get("parent_id") else ""
            print(f"  [{align:.0f}%] {g['text']}{parent}")
    else:
        print("  (no strategic goals set)")
    
    # Tactical
    print("\n## ✅ Tactical (Immediate)")
    tact_goals = [g for g in goals.get("tactical", []) if g.get("status") == "active"]
    if tact_goals:
        for g in tact_goals:
            align = g.get("alignment", 0) * 100
            progress = g.get("progress", 0)
            print(f"  [{align:.0f}%|{progress}%] {g['text']}")
    else:
        print("  (no tactical goals set)")
    
    # Stats
    completed = len(goals.get("completed", []))
    total = len(vision_goals) + len(strat_goals) + len(tact_goals)
    print(f"\n📊 {total} active goals | {completed} completed")
    print(f"Last updated: {goals.get('updated_at', 'never')}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("PINCH Goal System")
        print()
        print("Commands:")
        print("  show                    Show goal hierarchy")
        print("  add <timeframe> <text>  Add a goal (vision/strategic/tactical)")
        print("  complete <goal_id>      Mark goal as complete")
        print("  derive                  Suggest goals from beliefs")
        print("  tree                    Show goal tree structure")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "show":
        print_goals()
    
    elif cmd == "add":
        if len(sys.argv) < 4:
            print("Usage: goals.py add <vision|strategic|tactical> <goal text>")
            sys.exit(1)
        timeframe = sys.argv[2]
        text = " ".join(sys.argv[3:])
        goal = add_goal(text, timeframe=timeframe)
        print(f"✅ Added {timeframe} goal: {goal['text'][:50]}...")
        print(f"   ID: {goal['id']}")
        print(f"   Alignment: {goal['alignment']*100:.0f}%")
    
    elif cmd == "complete":
        if len(sys.argv) < 3:
            print("Usage: goals.py complete <goal_id>")
            sys.exit(1)
        goal_id = sys.argv[2]
        goal = complete_goal(goal_id)
        if goal:
            print(f"✅ Completed: {goal['text'][:50]}...")
        else:
            print(f"Goal not found: {goal_id}")
    
    elif cmd == "derive":
        print("🤔 Deriving goals from beliefs...")
        suggestions = derive_goals_from_beliefs()
        if suggestions:
            print("\nSuggested goals:")
            for s in suggestions:
                print(f"  [{s['timeframe'].upper()}] {s['text']}")
            
            print("\nAdd these? (y/n): ", end="")
            # In CLI mode, just show them
        else:
            print("No suggestions generated")
    
    elif cmd == "tree":
        tree = get_goal_tree()
        print("\n🌳 Goal Tree")
        print("=" * 50)
        
        for vnode in tree.get("vision", []):
            vg = vnode["goal"]
            print(f"\n🔭 {vg['text']}")
            for snode in vnode.get("children", []):
                sg = snode["goal"]
                print(f"   🎯 {sg['text']}")
                for tnode in snode.get("children", []):
                    tg = tnode["goal"]
                    print(f"      ✅ {tg['text']}")
        
        if tree.get("orphan_strategic"):
            print("\n📌 Unlinked Strategic:")
            for node in tree["orphan_strategic"]:
                print(f"   🎯 {node['goal']['text']}")
        
        if tree.get("orphan_tactical"):
            print("\n📌 Unlinked Tactical:")
            for node in tree["orphan_tactical"]:
                print(f"   ✅ {node['goal']['text']}")
    
    else:
        print(f"Unknown command: {cmd}")
