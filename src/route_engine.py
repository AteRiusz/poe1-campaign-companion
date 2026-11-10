"""
Campaign Route Engine for PoE1 Speedrun Companion.

Loads declarative route definitions from `data/campaign_route.json` and resolves
the active step when a player enters a zone in `Client.txt` or navigates manually.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        portal_tip="Add this zone to data/campaign_route.json to customize its layout",
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
    Stateful tracker for the player's current position in the PoE1 campaign route.
    """

    def __init__(self, route_json_path: Optional[Path] = None) -> None:
        if route_json_path is None:
            root_dir = Path(__file__).resolve().parent.parent
            route_json_path = root_dir / "data" / "campaign_route.json"
        self.route_json_path = Path(route_json_path)
        self.steps: List[RouteStep] = self._load_steps()
        self.current_index: int = 0
        self.active_fallback: Optional[RouteStep] = None
        self.character_name: Optional[str] = None
        self.character_level: Optional[int] = None
        self.poe_window_focused: bool = True
        self.last_log_timestamp: str = ""

    def _load_steps(self) -> List[RouteStep]:
        raw = json.loads(self.route_json_path.read_text(encoding="utf-8"))
        return [RouteStep.from_dict(item) for item in raw.get("steps", [])]

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

    def select_index(self, index: int) -> RouteStep:
        """Manually jump to a specific step index."""
        if not self.steps:
            return self.current_step
        self.active_fallback = None
        self.current_index = max(0, min(len(self.steps) - 1, int(index)))
        return self.current_step

    def next_step(self) -> RouteStep:
        """Advance one step forward in the route."""
        self.active_fallback = None
        if self.current_index < len(self.steps) - 1:
            self.current_index += 1
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
        3. If the zone is not in `campaign_route.json`, set a non-destructive `active_fallback` step.
        """
        normalized = zone_name.strip().lower()
        if not normalized:
            return self.current_step

        # 1. Forward lookahead window (handles revisiting zones or skipping optional sub-steps)
        lookahead_limit = min(len(self.steps), self.current_index + 9)
        for idx in range(self.current_index, lookahead_limit):
            if self.steps[idx].zone_name.strip().lower() == normalized:
                self.current_index = idx
                self.active_fallback = None
                return self.current_step

        # 2. Global search across all steps (choose closest step to current_index)
        matching_indices = [
            idx
            for idx, s in enumerate(self.steps)
            if s.zone_name.strip().lower() == normalized
        ]
        if matching_indices:
            best_idx = min(matching_indices, key=lambda i: abs(i - self.current_index))
            self.current_index = best_idx
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
