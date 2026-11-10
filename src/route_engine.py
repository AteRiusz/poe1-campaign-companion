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
from typing import Any, Dict, List, Optional, Sequence, Set

from src.log_watcher import LogEvent


# Multi-zone steps where a boss or quest objective resides in a specific sub-zone logged in Client.txt.
# Leaving the parent step only auto-completes if at least one of these sub-zones was entered (or boss dialogue seen).
REQUIRED_SUBZONES_BY_STEP_ID: Dict[str, Set[str]] = {
    "a1_s11_upper_prison": {"the warden's quarters"},
    "a1_s16_cavern_of_anger": {"merveil's caverns"},
    "a2_s10_crypt_level_1": {"the crypt level 1"},
    "a2_s14_caverns_and_pyramid": {"the ancient pyramid"},
    "a3_s08_solaris_temple": {"the solaris temple level 2"},
    "a3_s10_lunaris_temple": {"the lunaris temple level 2"},
    "a3_s12_sceptre_of_god": {"the upper sceptre of god"},
    "a4_s10_belly_of_the_beast": {"the belly of the beast level 2", "the bowels of the beast"},
    "a5_s09_cathedral_rooftop": {"the cathedral apex"},
    "a6_s07_shavronnes_tower": {"prison rooftop"},
    "a6_s10_wetlands_act6": {"the spawning ground"},
    "a6_s11_beacon_and_brine_king": {"the brine king's reef"},
    "a7_s02_crossroads_and_crypt": {"the crypt", "the crypt level 2"},
    "a7_s03_chamber_of_sins_1": {"maligaro's sanctum", "maligaro's workshop"},
    "a7_s06_northern_forest_dread_thicket": {"the dread thicket", "the den of despair"},
    "a7_s09_temple_of_decay": {"the temple of decay level 2", "arakaali's web"},
    "a8_s02_toxic_conduits_doedre": {"doedre's cesspool", "the cauldron"},
    "a8_s06_solaris_temple_act8": {"the solaris temple level 2"},
    "a8_s07_solaris_concourse_bath_house": {"the high gardens", "the pools of terror"},
    "a8_s08_lunaris_concourse_and_temple": {"the lunaris temple level 2"},
    "a8_s09_harbour_bridge": {"the sky shrine"},
    "a9_s02_descent_vastiri_desert": {"the vastiri desert", "the oasis", "the sand pit"},
    "a9_s03_foothills_boiling_lake": {"the boiling lake"},
    "a9_s05_the_quarry": {"the refinery", "the shrine of the winds"},
    "a9_s06_belly_and_rotting_core": {"the black heart"},
    "a10_s01_cathedral_rooftop": {"the cathedral apex"},
    "a10_s05_torched_desecrated_chambers": {"the desecrated chambers", "the sanctum of innocence"},
    "a10_s07_feeding_trough": {"the altar of hunger"},
}


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

    @property
    def is_town_hub(self) -> bool:
        """Return True if this step is a safe Town Hub."""
        if "TOWN" in self.compass.upper():
            return True
        z = self.zone_name.strip().lower()
        return z in (
            "lioneye's watch",
            "the forest encampment",
            "the sarn encampment",
            "highgate",
            "overseer's tower",
            "the bridge encampment",
            "oriath docks",
        )

    @property
    def has_boss_or_quest_objective(self) -> bool:
        """Return True if this step requires killing a boss or picking up a quest item."""
        if self.is_town_hub:
            return False
        return any(a.get("tag", "").upper() in ("BOSS", "QUEST") for a in self.actions)

    @property
    def allows_logout_or_hub_return(self) -> bool:
        """Return True if this step is a dead-end boss/quest zone exited via Logout, Portal, or Waypoint to Town/Hub."""
        combined = f"{self.next_exit} {self.portal_tip} {self.summary}".lower()
        return any(
            kw in combined
            for kw in ("logout", "relog", "portal back", "return to", "take wp to", "via portal", "to town")
        )

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

        # Step completion & active zone visit state
        self.completed_steps: Set[str] = set()
        self.newly_completed_steps: List[str] = []
        self._active_log_step_index: Optional[int] = None
        self._visited_zones_in_active_step: Set[str] = set()
        self._objective_triggered_in_active_step: bool = False
        self._has_progressed_via_log: bool = False

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

        if not self.steps or not self._has_progressed_via_log:
            return "locked"

        reached_step = self.steps[min(len(self.steps) - 1, self.max_reached_index)]
        if reached_step.act > trial.act:
            return "unlocked"

        if reached_step.act == trial.act:
            # Check if unlock_zone appears at or before max_reached_index in the same Act
            unlock_norm = trial.unlock_zone.strip().lower()
            zone_norm = trial.zone_name.strip().lower()
            for idx in range(0, self.max_reached_index + 1):
                s = self.steps[idx]
                if s.act == trial.act and (s.matches_zone(unlock_norm) or s.matches_zone(zone_norm)):
                    return "unlocked"

        return "locked"

    def select_index(self, index: int) -> RouteStep:
        """Manually jump to a specific step index (does not alter in-game progress or unlock trials)."""
        if not self.steps:
            return self.current_step
        self.active_fallback = None
        self.current_index = max(0, min(len(self.steps) - 1, int(index)))
        return self.current_step

    def next_step(self) -> RouteStep:
        """Advance one step forward in the route view (does not unlock trials)."""
        self.active_fallback = None
        if self.current_index < len(self.steps) - 1:
            self.current_index += 1
        return self.current_step

    def prev_step(self) -> RouteStep:
        """Move one step backward in the route view."""
        self.active_fallback = None
        if self.current_index > 0:
            self.current_index -= 1
        return self.current_step

    def reset_progress(self) -> RouteStep:
        """Reset route position, completed steps, and in-game progression state back to Act 1 Step 1."""
        self.current_index = 0
        self.max_reached_index = 0
        self.active_fallback = None
        self.completed_steps.clear()
        self.newly_completed_steps.clear()
        self._active_log_step_index = None
        self._visited_zones_in_active_step.clear()
        self._objective_triggered_in_active_step = False
        self._has_progressed_via_log = False
        return self.current_step

    def _can_complete_step_on_exit(self, prev_idx: int, new_idx: int, new_zone_norm: str) -> bool:
        """
        Determine whether leaving `self.steps[prev_idx]` for `self.steps[new_idx]` (`new_zone_norm`)
        should automatically mark `prev_step` as completed (`✅`).
        """
        if prev_idx < 0 or prev_idx >= len(self.steps) or prev_idx == new_idx:
            return False

        prev_step = self.steps[prev_idx]
        new_step = self.steps[new_idx]

        # 1. Special dependency: The Ship Graveyard requires Ship Graveyard Cave (Allflame) before Fairgraves
        if prev_step.step_id == "a1_s13_ship_graveyard":
            if (
                "a1_s14_ship_graveyard_cave" not in self.completed_steps
                and not self._objective_triggered_in_active_step
            ):
                return False

        # 2. Multi-zone boss/quest steps: verify required boss/quest sub-zone was entered (or dialogue triggered)
        req_subzones = REQUIRED_SUBZONES_BY_STEP_ID.get(prev_step.step_id)
        if req_subzones:
            if not (self._visited_zones_in_active_step & req_subzones) and not self._objective_triggered_in_active_step:
                return False
            # Once the boss/quest sub-zone was visited, leaving to a forward step or Town completes the step
            if new_idx > prev_idx or new_step.is_town_hub or self._objective_triggered_in_active_step:
                return True
            return False

        # 3. Single-zone steps with a Boss or Quest Item objective
        if prev_step.has_boss_or_quest_objective:
            if self._objective_triggered_in_active_step:
                return True
            # Exiting forward into the next campaign step (e.g. Hillock -> Lioneye's Watch, 3 Glyphs -> Submerged)
            if new_idx > prev_idx:
                return True
            # Exiting a dead-end boss/quest zone via Logout/Portal to a Town Hub (e.g. Hailrake -> Lioneye's Watch,
            # Dweller -> Lioneye's Watch, Fidelitas -> Forest Encampment, Kraityn -> Forest Encampment)
            if prev_step.allows_logout_or_hub_return:
                if new_step.is_town_hub:
                    return True
                # Returning from a sub-dungeon directly to its parent outdoor zone (e.g. Weaver's Chambers -> Western Forest,
                # Ship Graveyard Cave -> Ship Graveyard)
                if prev_step.step_id in ("a1_s14_ship_graveyard_cave", "a2_s09_weavers_chambers") and (
                    new_idx == prev_idx - 1
                ):
                    return True
            return False

        # 4. Town Hubs & pure traversal steps: complete when moving forward (or returning to the route from a Town Hub)
        if prev_step.is_town_hub:
            return True
        return new_idx > prev_idx

    def on_zone_entered(self, zone_name: str, track_completion: bool = True) -> RouteStep:
        """
        Match a newly entered zone name from Client.txt against the route:
        1. Look forward from `current_index` (up to 16 steps ahead) for an exact case-insensitive match.
        2. Otherwise search all steps for an exact case-insensitive match (preferring closest index).
        3. If the zone is not in `data/acts/`, set a non-destructive `active_fallback` step.
        """
        normalized = zone_name.strip().lower()
        if not normalized:
            return self.current_step

        best_idx: Optional[int] = None

        # 1. Forward lookahead window (handles revisiting zones or skipping optional sub-steps)
        lookahead_limit = min(len(self.steps), self.current_index + 16)
        for idx in range(self.current_index, lookahead_limit):
            if self.steps[idx].matches_zone(normalized):
                best_idx = idx
                break

        # 2. Global search across all steps (choose closest step to current_index)
        if best_idx is None:
            matching_indices = [
                idx
                for idx, s in enumerate(self.steps)
                if s.matches_zone(normalized)
            ]
            if matching_indices:
                best_idx = min(matching_indices, key=lambda i: abs(i - self.current_index))

        if best_idx is not None:
            prev_log_idx = self._active_log_step_index
            if track_completion and prev_log_idx is not None and best_idx != prev_log_idx:
                if self._can_complete_step_on_exit(prev_log_idx, best_idx, normalized):
                    done_id = self.steps[prev_log_idx].step_id
                    if done_id not in self.completed_steps:
                        self.completed_steps.add(done_id)
                        self.newly_completed_steps.append(done_id)

            if prev_log_idx != best_idx:
                self._active_log_step_index = best_idx
                self._visited_zones_in_active_step = {normalized}
                self._objective_triggered_in_active_step = False
            else:
                self._visited_zones_in_active_step.add(normalized)
                req_sub = REQUIRED_SUBZONES_BY_STEP_ID.get(self.steps[best_idx].step_id)
                if req_sub and normalized in req_sub:
                    self._objective_triggered_in_active_step = True

            self.current_index = best_idx
            if track_completion:
                self._has_progressed_via_log = True
                self.max_reached_index = max(self.max_reached_index, self.current_index)
            self.active_fallback = None
            return self.current_step

        # 3. Unmapped / Endgame Map zone fallback
        current_act = self.steps[self.current_index].act if self.steps else 1
        self.active_fallback = build_fallback_step(zone_name.strip(), act=current_act)
        return self.current_step

    def process_log_event(self, event: LogEvent, track_completion: bool = True) -> bool:
        """
        Process a parsed LogEvent from Client.txt.
        Returns True if the state changed in a way that requires a UI refresh.
        """
        self.last_log_timestamp = event.timestamp
        if event.event_type == "ZONE_ENTERED" and event.zone_name:
            self.on_zone_entered(event.zone_name, track_completion=track_completion)
            return True
        if event.event_type == "NPC_DIALOGUE" and event.npc_name:
            if self._active_log_step_index is not None:
                step = self.steps[self._active_log_step_index]
                speaker_lower = event.npc_name.strip().lower()
                step_blob = f"{step.summary} {step.boss_info} {' '.join(a.get('text', '') for a in step.actions)}".lower()
                # Check if any word (3+ chars) of the NPC/boss name appears in the active step's boss/quest description
                speaker_tokens = [tok for tok in re.split(r"[^a-z0-9]+", speaker_lower) if len(tok) >= 4]
                if any(tok in step_blob for tok in speaker_tokens):
                    self._objective_triggered_in_active_step = True
            return False
        if event.event_type == "LEVEL_UP":
            self.character_name = event.character_name
            self.character_level = event.level
            return True
        if event.event_type == "WINDOW_FOCUS" and event.window_focused is not None:
            if self.poe_window_focused != event.window_focused:
                self.poe_window_focused = event.window_focused
                return True
        return False
