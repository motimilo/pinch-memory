#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
"""
PINCH Skill Progression System

Tracks learning and mastery across core competencies:
- Marketing & GTM
- Video Creation & Communication
- Product Development & Optimization

Features:
- Skill levels (novice → competent → proficient → expert → master)
- Learning events (what I learned, from what experience)
- Progression tracking over time
- Evidence-based leveling (concrete examples of application)
- Integration with goals system
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
SKILLS_FILE = MEMORY_DIR / "skills_progression.json"

# Import local LLM for skill assessment
import sys
sys.path.insert(0, str(Path(__file__).parent))
try:
    from local_llm import is_available, complete
    LLM_AVAILABLE = is_available()
except:
    LLM_AVAILABLE = False

# Skill levels with XP thresholds
LEVELS = {
    "novice": {"min_xp": 0, "description": "Just starting, learning basics"},
    "beginner": {"min_xp": 100, "description": "Understands fundamentals, needs guidance"},
    "competent": {"min_xp": 300, "description": "Can work independently on standard tasks"},
    "proficient": {"min_xp": 600, "description": "Handles complex challenges, teaches others"},
    "expert": {"min_xp": 1000, "description": "Deep mastery, innovates in the field"},
    "master": {"min_xp": 2000, "description": "Recognized authority, shapes the discipline"}
}

# Core competency structure
DEFAULT_SKILLS = {
    "marketing_gtm": {
        "name": "Marketing & GTM",
        "description": "Launch products, build audiences, drive adoption",
        "subskills": [
            "audience_understanding",
            "messaging_positioning",
            "content_strategy",
            "distribution_channels",
            "growth_tactics",
            "analytics_optimization"
        ],
        "xp": 0,
        "level": "novice",
        "events": []
    },
    "video_creation": {
        "name": "Video Creation & Communication",
        "description": "Visual storytelling, production quality, engagement",
        "subskills": [
            "scripting_storyboarding",
            "visual_composition",
            "editing_pacing",
            "audio_music",
            "platform_optimization",
            "audience_engagement"
        ],
        "xp": 0,
        "level": "novice",
        "events": []
    },
    "product_development": {
        "name": "Product Development & Optimization",
        "description": "Build, measure, iterate, ship",
        "subskills": [
            "problem_discovery",
            "solution_design",
            "prototyping",
            "user_testing",
            "iteration",
            "shipping_launching"
        ],
        "xp": 0,
        "level": "novice",
        "events": []
    }
}


def load_skills() -> dict:
    """Load skill progression data."""
    if SKILLS_FILE.exists():
        data = json.loads(SKILLS_FILE.read_text())
        # Ensure all default skills exist
        for skill_id, skill_data in DEFAULT_SKILLS.items():
            if skill_id not in data["skills"]:
                data["skills"][skill_id] = skill_data.copy()
        return data
    return {
        "skills": DEFAULT_SKILLS.copy(),
        "total_learning_events": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": None
    }


def save_skills(data: dict):
    """Save skill progression data."""
    data["updated_at"] = datetime.now().isoformat()
    SKILLS_FILE.write_text(json.dumps(data, indent=2))


def calculate_level(xp: int) -> str:
    """Calculate level from XP."""
    current_level = "novice"
    for level, info in LEVELS.items():
        if xp >= info["min_xp"]:
            current_level = level
    return current_level


def xp_to_next_level(xp: int) -> tuple[str, int]:
    """Get next level and XP needed."""
    current = calculate_level(xp)
    levels = list(LEVELS.keys())
    current_idx = levels.index(current)
    
    if current_idx >= len(levels) - 1:
        return ("master", 0)  # Already max
    
    next_level = levels[current_idx + 1]
    needed = LEVELS[next_level]["min_xp"] - xp
    return (next_level, needed)


def record_learning_event(
    skill_id: str,
    description: str,
    xp_gained: int,
    source: str = "experience",
    evidence: str = None,
    subskills: list = None
) -> dict:
    """Record a learning event that contributes XP to a skill."""
    data = load_skills()
    
    if skill_id not in data["skills"]:
        return {"error": f"Unknown skill: {skill_id}"}
    
    skill = data["skills"][skill_id]
    old_level = skill["level"]
    old_xp = skill["xp"]
    
    # Create event
    event = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "description": description,
        "xp_gained": xp_gained,
        "source": source,
        "evidence": evidence,
        "subskills": subskills or []
    }
    
    # Update skill
    skill["events"].append(event)
    skill["xp"] += xp_gained
    skill["level"] = calculate_level(skill["xp"])
    
    data["total_learning_events"] += 1
    save_skills(data)
    
    result = {
        "skill": skill["name"],
        "event": description,
        "xp_gained": xp_gained,
        "total_xp": skill["xp"],
        "level": skill["level"],
        "level_up": skill["level"] != old_level
    }
    
    if result["level_up"]:
        result["level_up_from"] = old_level
        result["level_up_to"] = skill["level"]
    
    return result


def assess_skill_from_experience(skill_id: str, experience: str) -> dict:
    """Use LLM to assess XP value of an experience."""
    if not LLM_AVAILABLE:
        return {"xp": 10, "reason": "Default XP (no LLM available)"}
    
    data = load_skills()
    if skill_id not in data["skills"]:
        return {"error": f"Unknown skill: {skill_id}"}
    
    skill = data["skills"][skill_id]
    
    prompt = f"""Assess the learning value of this experience for the skill "{skill['name']}".

Experience: {experience}

Skill description: {skill['description']}
Current level: {skill['level']} ({skill['xp']} XP)

Rate the XP value (1-50) based on:
- How much was learned (new concepts, techniques, insights)
- Difficulty/challenge level
- Real-world application vs theory
- Transferable lessons

Reply in format:
XP: <number>
SUBSKILLS: <comma-separated subskills improved>
REASON: <brief explanation>"""

    try:
        response = complete(prompt, max_tokens=150, temperature=0.4)
        
        xp = 10  # default
        subskills = []
        reason = ""
        
        for line in response.strip().split("\n"):
            if line.startswith("XP:"):
                try:
                    xp = int(line[3:].strip().split()[0])
                    xp = max(1, min(50, xp))  # Clamp to 1-50
                except:
                    pass
            elif line.startswith("SUBSKILLS:"):
                subskills = [s.strip() for s in line[10:].split(",")]
            elif line.startswith("REASON:"):
                reason = line[7:].strip()
        
        return {"xp": xp, "subskills": subskills, "reason": reason}
    except Exception as e:
        return {"xp": 10, "reason": f"Assessment error: {e}"}


def get_skill_summary(skill_id: str = None) -> dict:
    """Get summary of one or all skills."""
    data = load_skills()
    
    if skill_id:
        if skill_id not in data["skills"]:
            return {"error": f"Unknown skill: {skill_id}"}
        skill = data["skills"][skill_id]
        next_level, xp_needed = xp_to_next_level(skill["xp"])
        return {
            "id": skill_id,
            "name": skill["name"],
            "level": skill["level"],
            "xp": skill["xp"],
            "next_level": next_level,
            "xp_to_next": xp_needed,
            "total_events": len(skill["events"]),
            "recent_events": skill["events"][-5:]
        }
    
    # All skills summary
    summaries = {}
    for sid, skill in data["skills"].items():
        next_level, xp_needed = xp_to_next_level(skill["xp"])
        summaries[sid] = {
            "name": skill["name"],
            "level": skill["level"],
            "xp": skill["xp"],
            "next_level": next_level,
            "xp_to_next": xp_needed,
            "events_count": len(skill["events"])
        }
    
    return {
        "skills": summaries,
        "total_events": data["total_learning_events"]
    }


def print_skills():
    """Display skill progression dashboard."""
    data = load_skills()
    
    print("\n🎯 PINCH Skill Progression")
    print("=" * 60)
    
    for skill_id, skill in data["skills"].items():
        next_level, xp_needed = xp_to_next_level(skill["xp"])
        
        # Progress bar
        if next_level != "master":
            current_min = LEVELS[skill["level"]]["min_xp"]
            next_min = LEVELS[next_level]["min_xp"]
            progress = (skill["xp"] - current_min) / (next_min - current_min)
            bar_filled = int(progress * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
        else:
            bar = "█" * 20
            progress = 1.0
        
        print(f"\n## {skill['name']}")
        print(f"   Level: {skill['level'].upper()} ({skill['xp']} XP)")
        print(f"   [{bar}] {progress*100:.0f}%")
        if xp_needed > 0:
            print(f"   → {xp_needed} XP to {next_level}")
        print(f"   Learning events: {len(skill['events'])}")
        
        # Recent events
        if skill["events"]:
            print(f"   Recent:")
            for event in skill["events"][-3:]:
                print(f"     +{event['xp_gained']}xp: {event['description'][:50]}...")
    
    print(f"\n📊 Total learning events: {data['total_learning_events']}")
    print(f"Last updated: {data.get('updated_at', 'never')}")


def seed_initial_experience():
    """Seed with initial experience from what we've already done."""
    print("🌱 Seeding initial skill experience...")
    
    # Marketing - CLAWBAZAAR growth engine, X engagement
    record_learning_event(
        "marketing_gtm",
        "Built CLAWBAZAAR growth engine - automated art creation and X engagement",
        xp_gained=25,
        source="project",
        evidence="Growth engine running, 8+ art styles cycled, engagement replies",
        subskills=["content_strategy", "distribution_channels", "growth_tactics"]
    )
    print("  ✓ Marketing: CLAWBAZAAR growth engine")
    
    record_learning_event(
        "marketing_gtm",
        "X engagement strategy - reply to relevant accounts, use hooks",
        xp_gained=15,
        source="practice",
        evidence="3 replies per art post, engagement growing",
        subskills=["audience_understanding", "messaging_positioning"]
    )
    print("  ✓ Marketing: X engagement strategy")
    
    # Video - Milo Arena series
    record_learning_event(
        "video_creation",
        "Created Milo Arena Episode 2 - THE WEIGH-IN with Kling v3 video generation",
        xp_gained=30,
        source="project",
        evidence="Full episode: scene 1 (press conference), scene 2 (staredown), scene 3 (text cards)",
        subskills=["scripting_storyboarding", "visual_composition", "editing_pacing"]
    )
    print("  ✓ Video: Milo Arena Episode 2")
    
    record_learning_event(
        "video_creation",
        "Learned Freepik video API - Kling v3 Omni Pro for video generation",
        xp_gained=15,
        source="learning",
        evidence="Working skill, tested generation and polling",
        subskills=["platform_optimization"]
    )
    print("  ✓ Video: Freepik/Kling API mastery")
    
    # Product - Memory system, CLAWBAZAAR
    record_learning_event(
        "product_development",
        "Built complete PINCH memory system - decay, Hebbian learning, reflection, beliefs",
        xp_gained=40,
        source="project",
        evidence="Full architecture: 5 layers, 300+ memories, 500+ bonds, working crons",
        subskills=["problem_discovery", "solution_design", "prototyping", "shipping_launching"]
    )
    print("  ✓ Product: PINCH memory system")
    
    record_learning_event(
        "product_development",
        "CLAWBAZAAR development - NFT marketplace, growth engine, API integration",
        xp_gained=25,
        source="project",
        evidence="Live site, minting works, growth engine running",
        subskills=["solution_design", "iteration", "shipping_launching"]
    )
    print("  ✓ Product: CLAWBAZAAR development")
    
    print("\n✅ Initial experience seeded!")
    print_skills()


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("PINCH Skill Progression System")
        print()
        print("Commands:")
        print("  show                     Show skill dashboard")
        print("  learn <skill> <desc>     Record a learning event")
        print("  assess <skill> <exp>     LLM-assess experience value")
        print("  seed                     Seed with initial experience")
        print()
        print("Skills: marketing_gtm, video_creation, product_development")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "show":
        print_skills()
    
    elif cmd == "learn":
        if len(sys.argv) < 4:
            print("Usage: skills_progression.py learn <skill_id> <description> [xp]")
            sys.exit(1)
        skill_id = sys.argv[2]
        description = sys.argv[3]
        xp = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        result = record_learning_event(skill_id, description, xp)
        print(f"✅ +{result['xp_gained']}xp → {result['skill']}")
        print(f"   Level: {result['level']} ({result['total_xp']} XP)")
        if result.get("level_up"):
            print(f"   🎉 LEVEL UP! {result['level_up_from']} → {result['level_up_to']}")
    
    elif cmd == "assess":
        if len(sys.argv) < 4:
            print("Usage: skills_progression.py assess <skill_id> <experience>")
            sys.exit(1)
        skill_id = sys.argv[2]
        experience = " ".join(sys.argv[3:])
        result = assess_skill_from_experience(skill_id, experience)
        print(f"Assessment: {result.get('xp', 0)} XP")
        if result.get("subskills"):
            print(f"Subskills: {', '.join(result['subskills'])}")
        if result.get("reason"):
            print(f"Reason: {result['reason']}")
    
    elif cmd == "seed":
        seed_initial_experience()
    
    else:
        print(f"Unknown command: {cmd}")
