"""
Settings manager for PoE1 Campaign Speedrun Companion.

Handles persistent user configuration (opacity slider, active UI mode,
Client.txt log path, and optional extra info toggles which are OFF by default).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

DEFAULT_STEAM_LOG_PATHS = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt"),
    Path(r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\Client.txt"),
    Path(r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\Client.txt"),
    Path(r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt"),
]


def detect_default_client_log() -> str:
    """Return the first existing Path of Exile Client.txt path, or the standard Steam path."""
    for candidate in DEFAULT_STEAM_LOG_PATHS:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue
    return str(DEFAULT_STEAM_LOG_PATHS[0])


@dataclass
class AppSettings:
    """User-configurable settings. Extra info flags are OFF by default."""

    opacity: float = 0.92  # Range: 0.25 to 1.00
    ui_mode: str = "dashboard"  # "overlay" | "dashboard" | "both"
    overlay_click_through: bool = True
    overlay_x: int = 980
    overlay_y: int = 24
    auto_hide_on_poe_blur: bool = False
    client_log_path: str = ""

    # Extra info toggles — OFF by default per user design specification
    show_boss_info: bool = False
    show_gem_rewards: bool = False
    show_variants: bool = False

    def __post_init__(self) -> None:
        if not self.client_log_path:
            self.client_log_path = detect_default_client_log()
        self.opacity = max(0.25, min(1.0, float(self.opacity)))


class SettingsManager:
    """Loads and saves AppSettings to a local JSON file."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        if config_path is None:
            root_dir = Path(__file__).resolve().parent.parent
            config_path = root_dir / "config" / "user_settings.json"
        self.config_path = Path(config_path)
        self.settings: AppSettings = self.load()

    def load(self) -> AppSettings:
        """Load settings from disk, falling back to defaults if missing or invalid."""
        if not self.config_path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            valid_keys = {f for f in AppSettings.__dataclass_fields__}
            filtered = {k: v for k, v in raw.items() if k in valid_keys}
            return AppSettings(**filtered)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return AppSettings()

    def save(self) -> None:
        """Persist current settings to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(asdict(self.settings), indent=2),
            encoding="utf-8",
        )

    def set_opacity(self, opacity: float) -> float:
        """Set window opacity clamped between 0.25 and 1.00 and save."""
        self.settings.opacity = max(0.25, min(1.0, round(float(opacity), 2)))
        self.save()
        return self.settings.opacity

    def set_extra_toggle(self, field_name: str, enabled: bool) -> None:
        """Update one of the optional extra-info toggles and save."""
        if field_name not in ("show_boss_info", "show_gem_rewards", "show_variants"):
            raise ValueError(f"Unknown extra info setting: {field_name}")
        setattr(self.settings, field_name, bool(enabled))
        self.save()
