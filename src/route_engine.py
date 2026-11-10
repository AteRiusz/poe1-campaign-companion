"""
Campaign Route Engine & Labyrinth Trial Tracker for PoE1 Speedrun Companion.

Loads declarative per-Act route files from `data/acts/act1.json` .. `act10.json`
and Labyrinth Trial definitions from `data/labyrinth_trials.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.log_watcher import LogEvent


@dataclass
class RouteStep:
    """Represents a single step/zone in the campaign speedrun guide."""

    step_id: str
    act: int
    step_number: int
    zone_name: str
    area_level: int
    compass: str
    summary: str
    layout_tell: str
    next_exit: str
    portal_tip: str
    badges: List[Dict[str, str]] = field(default_factory=list)
    actions: List[Dict[str, str]] = field(default_factory=list)
    boss_info: str = ""
    gem_reward: str = ""
    variants: List[Dict[str, str]] = field(default_factory=list)
    topology: Dict[str, Any] = field(default_factory=dict)
    zone_aliases: List[str] = field(default_factory=list)

    def matches_zone(self, normalized_zone: str) -> bool:
        """Return True if `normalized_zone` matches `zone_name` or any entry in `zone_aliases`."""
        if self.zone_name.strip().lower() == normalized_zone:
            return True
        return any(a.strip().lower() == normalized_zone for a in self.zone_aliases)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteStep":
        return cls(
            step_id=str(data.get("step_id", "")),
            act=int(data.get("act", 1)),
            step_number=int(data.get("step_number", 1)),
            zone_name=str(data.get("zone_name", "Unknown Zone")),
            area_level=int(data.get("area_level", 1)),
            compass=str(data.get("compass", "→")),
            summary=str(data.get("summary", "")),
            layout_tell=str(data.get("layout_tell", "")),
            next_exit=str(data.get("next_exit", "")),
            portal_tip=str(data.get("portal_tip", "")),
            badges=list(data.get("badges", [])),
            actions=list(data.get("actions", [])),
            boss_info=str(data.get("boss_info", "")),
            gem_reward=str(data.get("gem_reward", "")),
            variants=list(data.get("variants", [])),
            topology=dict(data.get("topology", {"nodes": [], "edges": []})),
            zone_aliases=list(data.get("zone_aliases", [])),
        )


@dataclass
class LabyrinthTrial:
    """Represents one of the 12 Campaign Labyrinth Trials (6 Normal, 3 Cruel, 3 Merciless)."""

    trial_id: str
    labyrinth: str  # "Normal" | "Cruel" | "Merciless"
    act: int
    zone_name: str
    waypoint_hint: str
    trap_type: str
    unlock_zone: str
    layout_hint: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LabyrinthTrial":
        return cls(
            trial_id=str(data.get("trial_id", "")),
            labyrinth=str(data.get("labyrinth", "Normal")),
            act=int(data.get("act", 1)),
            zone_name=str(data.get("zone_name", "")),
            waypoint_hint=str(data.get("waypoint_hint", "")),
            trap_type=str(data.get("trap_type", "")),
            unlock_zone=str(data.get("unlock_zone", "")),
            layout_hint=str(data.get("layout_hint", "")),
        )


def build_fallback_step(zone_name: str, act: int = 1) -> RouteStep:
    """Create a clean fallback RouteStep when entering an unmapped or endgame zone."""
    return RouteStep(
        step_id=f"fallback_{zone_name.lower().replace(' ', '_')}",
        act=act,
        step_number=0,
        zone_name=zone_name,
        area_level=0,
        compass="LIVE ZONE",
        summary=f"Currently in {zone_name} (Custom / Unmapped Zone)",
        layout_tell="Use manual Prev/Next buttons or enter a campaign zone to resume guided routing.",
        next_exit="Continue along your current objective",
        portal_tip="Add this zone to data/acts/actN.json to customize its layout",
        badges=[{"label": "LIVE TRACKING", "color": "sky"}],
        actions=[
            {
                "tag": "MAIN",
                "color": "emerald",
                "text": f"Detected entry into '{zone_name}' via Client.txt",
            }
        ],
        topology={
            "nodes": [
                {"id": "start", "label": "Entrance", "x": 0.2, "y": 0.75, "type": "start"},
                {"id": "exit", "label": zone_name, "x": 0.8, "y": 0.25, "type": "exit"},
            ],
            "edges": [{"from": "start", "to": "exit", "style": "main"}],
        },
    )


class RouteEngine:
    """
    Stateful tracker for the player's current position in the PoE1 campaign route
    (Acts 1–10) and Labyrinth Trial unlock/completion states.
    """

    def __init__(
        self,
        acts_dir: Optional[Path] = None,
        trials_path: Optional[Path] = None,
    ) -> None:
        root_dir = Path(__file__).resolve().parent.parent
        self.acts_dir = Path(acts_dir) if acts_dir is not None else (root_dir / "data" / "acts")
        self.trials_path = (
            Path(trials_path) if trials_path is not None else (root_dir / "data" / "labyrinth_trials.json")
        )

        self.steps: List[RouteStep] = self._load_all_act_steps()
        self.trials: List[LabyrinthTrial] = self._load_trials()

        self.current_index: int = 0
        self.max_reached_index: int = 0
        self.active_fallback: Optional[RouteStep] = None
        self.character_name: Optional[str] = None
        self.character_level: Optional[int] = None
        self.poe_window_focused: bool = True
        self.last_log_timestamp: str = ""

    def _load_all_act_steps(self) -> List[RouteStep]:
        """Load all `act1.json` .. `act10.json` files from `data/acts/` in numerical order."""
        if not self.acts_dir.exists():
            return []

        def _act_sort_key(p: Path) -> int:
            m = re.search(r"(\d+)", p.stem)
            return int(m.group(1)) if m else 999

        loaded: List[RouteStep] = []
        for act_file in sorted(self.acts_dir.glob("act*.json"), key=_act_sort_key):
            raw = json.loads(act_file.read_text(encoding="utf-8"))
            for item in raw.get("steps", []):
                loaded.append(RouteStep.from_dict(item))
        return loaded

    def _load_trials(self) -> List[LabyrinthTrial]:
        """Load the 12 Campaign Labyrinth Trials from `data/labyrinth_trials.json`."""
        if not self.trials_path.exists():
            return []
        raw = json.loads(self.trials_path.read_text(encoding="utf-8"))
        return [LabyrinthTrial.from_dict(item) for item in raw.get("trials", [])]

    @property
    def current_step(self) -> RouteStep:
        """Return the active RouteStep (or fallback step if in an unmapped zone)."""
        if self.active_fallback is not None:
            return self.active_fallback
        if not self.steps:
            return build_fallback_step("Unknown")
        return self.steps[self.current_index]

    def get_act_steps(self, act: Optional[int] = None) -> List[RouteStep]:
        """Return all steps belonging to the specified Act (or current step's Act)."""
        target_act = act if act is not None else self.current_step.act
        return [s for s in self.steps if s.act == target_act]

    def get_trials_by_tier(self, tier: str) -> List[LabyrinthTrial]:
        """Return trials for 'Normal' (6), 'Cruel' (3), or 'Merciless' (3)."""
        norm_tier = tier.strip().lower()
        return [t for t in self.trials if t.labyrinth.strip().lower() == norm_tier]

    def get_trial_status(
        self,
        trial: LabyrinthTrial,
        unlocked_ids: Sequence[str] = (),
        completed_ids: Sequence[str] = (),
    ) -> str:
        """
        Determine a trial's current state: 'completed' | 'unlocked' | 'locked'.
        A trial is unlocked if explicitly in `unlocked_ids` OR if the player's
        highest reached campaign step has reached/passed the trial's `unlock_zone` or Act.
        """
        if trial.trial_id in completed_ids:
            return "completed"
        if trial.trial_id in unlocked_ids:
            return "unlocked"

        if not self.steps:
            return "locked"

        reached_step = self.steps[min(len(self.steps) - 1, max(self.current_index, self.max_reached_index))]
        if reached_step.act > trial.act:
            return "unlocked"

        if reached_step.act == trial.act:
            # Check if unlock_zone appears at or before max_reached_index in the same Act
            unlock_norm = trial.unlock_zone.strip().lower()
            zone_norm = trial.zone_name.strip().lower()
            for idx in range(0, max(self.current_index, self.max_reached_index) + 1):
                s = self.steps[idx]
                if s.act == trial.act and (s.matches_zone(unlock_norm) or s.matches_zone(zone_norm)):
                    return "unlocked"

        return "locked"

    def select_index(self, index: int) -> RouteStep:
        """Manually jump to a specific step index."""
        if not self.steps:
            return self.current_step
        self.active_fallback = None
        self.current_index = max(0, min(len(self.steps) - 1, int(index)))
        self.max_reached_index = max(self.max_reached_index, self.current_index)
        return self.current_step

    def next_step(self) -> RouteStep:
        """Advance one step forward in the route."""
        self.active_fallback = None
        if self.current_index < len(self.steps) - 1:
            self.current_index += 1
            self.max_reached_index = max(self.max_reached_index, self.current_index)
        return self.current_step

    def prev_step(self) -> RouteStep:
        """Move one step backward in the route."""
        self.active_fallback = None
        if self.current_index > 0:
            self.current_index -= 1
        return self.current_step

    def on_zone_entered(self, zone_name: str) -> RouteStep:
        """
        Match a newly entered zone name from Client.txt against the route:
        1. Look forward from `current_index` (up to 8 steps ahead) for an exact case-insensitive match.
        2. Otherwise search all steps for an exact case-insensitive match (preferring closest index).
        3. If the zone is not in `data/acts/`, set a non-destructive `active_fallback` step.
        """
        normalized = zone_name.strip().lower()
        if not normalized:
            return self.current_step

        # 1. Forward lookahead window (handles revisiting zones or skipping optional sub-steps)
        lookahead_limit = min(len(self.steps), self.current_index + 16)
        for idx in range(self.current_index, lookahead_limit):
            if self.steps[idx].matches_zone(normalized):
                self.current_index = idx
                self.max_reached_index = max(self.max_reached_index, self.current_index)
                self.active_fallback = None
                return self.current_step

        # 2. Global search across all steps (choose closest step to current_index)
        matching_indices = [
            idx
            for idx, s in enumerate(self.steps)
            if s.matches_zone(normalized)
        ]
        if matching_indices:
            best_idx = min(matching_indices, key=lambda i: abs(i - self.current_index))
            self.current_index = best_idx
            self.max_reached_index = max(self.max_reached_index, self.current_index)
            self.active_fallback = None
            return self.current_step

        # 3. Unmapped / Endgame Map zone fallback
        current_act = self.steps[self.current_index].act if self.steps else 1
        self.active_fallback = build_fallback_step(zone_name.strip(), act=current_act)
        return self.current_step

    def process_log_event(self, event: LogEvent) -> bool:
        """
        Process a parsed LogEvent from Client.txt.
        Returns True if the state changed in a way that requires a UI refresh.
        """
        self.last_log_timestamp = event.timestamp
        if event.event_type == "ZONE_ENTERED" and event.zone_name:
            self.on_zone_entered(event.zone_name)
            return True
        if event.event_type == "LEVEL_UP":
            self.character_name = event.character_name
            self.character_level = event.level
            return True
        if event.event_type == "WINDOW_FOCUS" and event.window_focused is not None:
            if self.poe_window_focused != event.window_focused:
                self.poe_window_focused = event.window_focused
                return True
        return False
