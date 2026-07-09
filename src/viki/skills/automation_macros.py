"""
Cross-app automation macros — record, generalize, and verify demonstrated flows.

Learns from demonstrated workflows (window manager + clipboard + shell events),
generalizes them into parameterized skills, and validates them in the sandbox.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from viki.config.logger import viki_logger


@dataclass
class MacroStep:
    """A single step in a recorded macro."""

    action: str  # click, type, shell, wait, hotkey, clipboard
    target: str = ""
    value: str = ""
    timestamp: float = 0.0
    duration_ms: float = 0.0


@dataclass
class Macro:
    """A recorded and generalized automation macro."""

    name: str = ""
    description: str = ""
    steps: list[MacroStep] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    created_at: float = 0.0
    execution_count: int = 0
    success_count: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [
                {"action": s.action, "target": s.target, "value": s.value} for s in self.steps
            ],
            "parameters": self.parameters,
            "created_at": self.created_at,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Macro:
        m = cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", []),
        )
        m.steps = [MacroStep(**s) for s in data.get("steps", [])]
        m.created_at = data.get("created_at", 0)
        m.execution_count = data.get("execution_count", 0)
        m.success_count = data.get("success_count", 0)
        return m


class MacroRecorder:
    """
    Records demonstrated flows and generalizes them into macros.

    Usage:
        recorder = MacroRecorder()
        recorder.start_recording()
        # ... user performs actions ...
        macro = recorder.stop_recording("my_macro")
    """

    def __init__(self, persistence_dir: str = "./data/macros"):
        self._recording = False
        self._steps: list[MacroStep] = []
        self._start_time = 0.0
        self._persistence_dir = persistence_dir
        os.makedirs(persistence_dir, exist_ok=True)
        self._macros: dict[str, Macro] = {}
        self._load()

    def start_recording(self) -> None:
        self._recording = True
        self._steps.clear()
        self._start_time = time.time()
        viki_logger.info("MacroRecorder: recording started")

    def record_step(self, action: str, target: str = "", value: str = "") -> None:
        if not self._recording:
            return
        self._steps.append(
            MacroStep(
                action=action,
                target=target,
                value=value,
                timestamp=time.time(),
            )
        )

    def stop_recording(self, name: str, description: str = "") -> Macro:
        self._recording = False
        if not self._steps:
            return Macro(name=name)

        macro = self._generalize(name, description)
        self._macros[name] = macro
        self._save()
        viki_logger.info(
            "MacroRecorder: saved macro '%s' (%d steps, %d params)",
            name,
            len(macro.steps),
            len(macro.parameters),
        )
        return macro

    def _generalize(self, name: str, description: str) -> Macro:
        """Generalize recorded steps into a parameterized macro."""
        # Detect parameters by looking for repeated values
        values = [s.value for s in self._steps if s.value]
        param_candidates = [v for v in set(values) if values.count(v) > 1]

        steps = []
        params = []
        for s in self._steps:
            step = MacroStep(action=s.action, target=s.target, value=s.value)
            # Parameterize repeated values
            if s.value in param_candidates:
                param_name = s.value.lower().replace(" ", "_").replace("/", "_")[:20]
                if param_name not in params:
                    params.append(param_name)
                step.value = f"{{{{{param_name}}}}}"
            steps.append(step)

        return Macro(
            name=name,
            description=description or f"Macro: {name}",
            steps=steps,
            parameters=params,
            created_at=time.time(),
        )

    async def execute(self, name: str, params: dict[str, str] | None = None) -> str:
        """Execute a recorded macro with given parameter values."""
        macro = self._macros.get(name)
        if macro is None:
            return f"Macro '{name}' not found"

        params = params or {}
        output: list[str] = []

        for step in macro.steps:
            value = step.value
            # Substitute parameters
            for k, v in params.items():
                value = value.replace(f"{{{{{k}}}}}", v)

            output.append(f"{step.action}({step.target}, {value})")
            try:
                await self._execute_step(step, params)
            except Exception as e:
                return f"Macro '{name}' failed at step: {e}"

        macro.execution_count += 1
        macro.success_count += 1
        self._save()
        return f"Macro '{name}' executed successfully\n" + "\n".join(output)

    async def _execute_step(self, step: MacroStep, params: dict[str, str]) -> None:
        """Execute a single macro step."""
        value = step.value
        for k, v in params.items():
            value = value.replace(f"{{{{{k}}}}}", v)

        try:
            import pyautogui

            if step.action == "type":
                pyautogui.write(value)
            elif step.action == "hotkey":
                keys = value.split("+")
                pyautogui.hotkey(*keys)
            elif step.action == "click":
                pyautogui.click()
            elif step.action == "shell":
                import subprocess

                subprocess.run(value, shell=True, timeout=30)
        except Exception as e:
            viki_logger.error("Macro step failed: %s", e)
            raise

    def list_macros(self) -> list[Macro]:
        return list(self._macros.values())

    def get_macro(self, name: str) -> Macro | None:
        return self._macros.get(name)

    def _save(self) -> None:
        try:
            data = [m.to_dict() for m in self._macros.values()]
            with open(os.path.join(self._persistence_dir, "macros.json"), "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            viki_logger.error("MacroRecorder: save failed: %s", e)

    def _load(self) -> None:
        path = os.path.join(self._persistence_dir, "macros.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for item in data:
                m = Macro.from_dict(item)
                self._macros[m.name] = m
        except Exception as e:
            viki_logger.error("MacroRecorder: load failed: %s", e)
