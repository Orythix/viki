"""
Continuous Learning Pipeline
Manages automated model improvement cycles.
"""
import os
import time
import json
import asyncio
from typing import Dict, Any, Optional
from viki.config.logger import viki_logger
from viki.core.forge_config import resolve_forge_output_ollama_tag


class ContinuousLearner:
    """Manages automated model improvement cycles."""
    
    def __init__(self, controller):
        self.controller = controller
        self.training_schedule = "weekly"  # daily, weekly, monthly
        self.min_lessons_for_training = 100
        self.last_training_time = 0
        self.training_enabled = True
        # Phase 5: eval-gated promotion configuration.
        sys_cfg = (controller.settings.get("system") or {}) if getattr(controller, "settings", None) else {}
        forge_cfg = (controller.settings.get("forge") or {}) if getattr(controller, "settings", None) else {}
        self.promotion_min_index_delta = float(
            sys_cfg.get("promotion_min_index_delta", forge_cfg.get("promotion_min_index_delta", 0.01))
        )
        self.promotion_min_consecutive_passes = int(
            sys_cfg.get("promotion_min_consecutive_passes", forge_cfg.get("promotion_min_consecutive_passes", 2))
        )
        data_dir = sys_cfg.get("data_dir", "./data")
        self.promotion_state_path = os.path.join(data_dir, "promotion_state.json")
        self._promotion_state: Dict[str, Any] = self._load_promotion_state()
    
    def _schedule_to_seconds(self) -> float:
        """Convert schedule string to seconds."""
        schedules = {
            'hourly': 3600,
            'daily': 86400,
            'weekly': 604800,
            'monthly': 2592000,
        }
        return schedules.get(self.training_schedule, 604800)
    
    async def check_and_train(self):
        """Check if training is due and execute."""
        if not self.training_enabled:
            return
        
        lesson_count = self.controller.learning.get_total_lesson_count()
        time_since_last = time.time() - self.last_training_time
        schedule_seconds = self._schedule_to_seconds()
        
        # Check conditions
        should_train = (
            lesson_count >= self.min_lessons_for_training and
            time_since_last >= schedule_seconds
        )
        
        if should_train:
            viki_logger.info(f"ContinuousLearner: Training conditions met "
                           f"(lessons: {lesson_count}, time since last: {time_since_last/3600:.1f}h)")
            await self._execute_training_cycle()
        else:
            viki_logger.debug(f"ContinuousLearner: Training not due yet "
                            f"(lessons: {lesson_count}/{self.min_lessons_for_training}, "
                            f"next in: {(schedule_seconds - time_since_last)/3600:.1f}h)")
    
    async def _execute_training_cycle(self):
        """Full training cycle: prepare, train, validate, deploy."""
        viki_logger.info("=" * 60)
        viki_logger.info("ContinuousLearner: Starting automated training cycle")
        viki_logger.info("=" * 60)
        
        try:
            # 1. Export dataset
            dataset_path = "./data/training_dataset.jsonl"
            viki_logger.info("ContinuousLearner: Exporting training dataset...")
            export_result = self.controller.learning.export_training_dataset(
                dataset_path,
                format="jsonl",
                settings=self.controller.settings,
            )
            viki_logger.info(f"ContinuousLearner: {export_result}")
            
            # 2. Trigger forge
            viki_logger.info("ContinuousLearner: Triggering model forge...")
            forge = self.controller.skill_registry.get_skill('internal_forge')
            if not forge:
                viki_logger.error("ContinuousLearner: Forge skill not found")
                return
            
            # Use auto strategy (will choose LoRA if available, otherwise Ollama)
            result = await forge.execute({"strategy": "auto", "steps": 50})
            viki_logger.info(f"ContinuousLearner: Forge result: {result}")
            
            # 3. Validate new model (if successfully created)
            if "SUCCESS" in result.upper() or "COMPLETE" in result.upper():
                new_model_name = resolve_forge_output_ollama_tag(self.controller.settings)
                viki_logger.info(f"ContinuousLearner: Validating {new_model_name}...")

                is_valid = await self._validate_model(new_model_name)

                if is_valid:
                    viki_logger.info(f"ContinuousLearner: Validation passed for {new_model_name}")
                    self.last_training_time = time.time()
                    # Phase 5: eval-gated auto-promotion.
                    promoted = await self.maybe_promote(new_model_name)
                    self.controller.learning.save_lesson(
                        trigger="Model training completed",
                        fact=(
                            f"Trained {new_model_name} with {self.controller.learning.get_total_lesson_count()} lessons; "
                            f"promotion={'yes' if promoted else 'pending eval gate'}"
                        ),
                        source="continuous_learning",
                    )
                else:
                    viki_logger.warning(f"ContinuousLearner: Validation failed for {new_model_name}")
            else:
                viki_logger.warning("ContinuousLearner: Forge did not complete successfully")
        
        except Exception as e:
            viki_logger.error(f"ContinuousLearner: Training cycle failed: {e}", exc_info=True)
        
        finally:
            viki_logger.info("=" * 60)
            viki_logger.info("ContinuousLearner: Training cycle complete")
            viki_logger.info("=" * 60)
    
    async def _validate_model(self, model_name: str) -> bool:
        """Validate model with quick tests."""
        # Check if model exists in Ollama
        try:
            import subprocess
            result = await asyncio.to_thread(
                subprocess.run,
                ['ollama', 'list'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if model_name not in result.stdout:
                viki_logger.warning(f"Model {model_name} not found in Ollama")
                return False
            
            # Use A/B testing framework for validation
            if hasattr(self.controller, 'ab_tester'):
                validation_result = await self.controller.ab_tester.quick_validation(model_name)
                return validation_result.get('passed', False)
            else:
                # Simple validation: just check if model responds
                model = self.controller.model_router.models.get(model_name)
                if model:
                    test_response = await model.chat([
                        {'role': 'user', 'content': 'Say hello.'}
                    ])
                    return len(test_response) > 0 and 'error' not in test_response.lower()
                
                return False
        
        except Exception as e:
            viki_logger.error(f"Model validation failed: {e}")
            return False
    
    def set_schedule(self, schedule: str):
        """Set training schedule: hourly, daily, weekly, monthly."""
        if schedule in ['hourly', 'daily', 'weekly', 'monthly']:
            self.training_schedule = schedule
            viki_logger.info(f"ContinuousLearner: Schedule set to {schedule}")
        else:
            viki_logger.warning(f"Invalid schedule: {schedule}")
    
    def set_min_lessons(self, count: int):
        """Set minimum lesson count required for training."""
        self.min_lessons_for_training = max(10, count)
        viki_logger.info(f"ContinuousLearner: Min lessons set to {self.min_lessons_for_training}")
    
    def enable(self):
        """Enable continuous learning."""
        self.training_enabled = True
        viki_logger.info("ContinuousLearner: Enabled")
    
    def disable(self):
        """Disable continuous learning."""
        self.training_enabled = False
        viki_logger.info("ContinuousLearner: Disabled")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of continuous learning."""
        lesson_count = self.controller.learning.get_total_lesson_count()
        time_since_last = time.time() - self.last_training_time
        time_until_next = max(0, self._schedule_to_seconds() - time_since_last)
        
        return {
            'enabled': self.training_enabled,
            'schedule': self.training_schedule,
            'min_lessons': self.min_lessons_for_training,
            'current_lessons': lesson_count,
            'last_training_time': self.last_training_time,
            'time_until_next_hours': round(time_until_next / 3600, 1),
            'ready_to_train': lesson_count >= self.min_lessons_for_training and time_since_last >= self._schedule_to_seconds(),
            'promotion_state': self._promotion_state,
        }

    # --------------------------- Phase 5: eval-gated promotion -----------------------------

    def _load_promotion_state(self) -> Dict[str, Any]:
        try:
            if os.path.isfile(self.promotion_state_path):
                with open(self.promotion_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            viki_logger.debug("ContinuousLearner: failed to load promotion state: %s", e)
        return {
            "current_default": None,
            "previous_default": None,
            "history": [],
            "consecutive_passes": {},
        }

    def _save_promotion_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.promotion_state_path) or ".", exist_ok=True)
            with open(self.promotion_state_path, "w", encoding="utf-8") as f:
                json.dump(self._promotion_state, f, indent=2)
        except Exception as e:
            viki_logger.debug("ContinuousLearner: failed to save promotion state: %s", e)

    async def _capability_index_for(self, model_name: str) -> Optional[float]:
        """
        Compute the latest CapabilityIndex restricted to a model's results.

        Falls back to None if the eval harness has not produced any results
        (e.g. on a fresh checkout).
        """
        try:
            from viki.core.capability_index import CapabilityIndex

            data_dir = (self.controller.settings.get("system") or {}).get("data_dir", "./data")
            forge_settings = (self.controller.settings.get("forge") or {})
            min_tasks = int(forge_settings.get("capability_index_min_tasks", 0))
            bootstrap = int(forge_settings.get("capability_index_bootstrap_iters", 0))
            # P0 fix: CapabilityIndex's signature is positional `results_root`, not
            # `eval_results_dir`. The previous keyword raised TypeError silently
            # (swallowed by the except below), so promotion never scored anything.
            ci = CapabilityIndex(
                os.path.join(data_dir, "eval_results"),
                min_tasks=min_tasks,
                bootstrap_iters=bootstrap,
                model_filter=model_name,
            )
            snapshot = ci.compute()
        except Exception as e:
            viki_logger.debug("ContinuousLearner: capability index compute failed: %s", e)
            return None
        if not snapshot or not snapshot.get("suites"):
            return None
        return float(snapshot.get("capability_index", 0.0)) if snapshot else None

    async def maybe_promote(self, candidate_model: str) -> bool:
        """
        Promote `candidate_model` to `models.default` only if its CapabilityIndex
        beats the current default by `promotion_min_index_delta` for
        `promotion_min_consecutive_passes` consecutive evaluations.

        On regression, the previous default is restored (auto-rollback).
        """
        current_default = self._promotion_state.get("current_default")
        try:
            current_default = current_default or (
                (self.controller.models_config or {}).get("models", {}).get("default")
            )
        except Exception:
            current_default = current_default or None

        candidate_score = await self._capability_index_for(candidate_model)
        if candidate_score is None:
            viki_logger.info(
                "ContinuousLearner: no eval data for %s; skipping promotion gate.",
                candidate_model,
            )
            return False
        baseline_score = await self._capability_index_for(current_default) if current_default else 0.0
        if current_default and baseline_score is None:
            viki_logger.info(
                "ContinuousLearner: no eval data for baseline %s; skipping promotion gate.",
                current_default,
            )
            return False
        baseline_score = baseline_score or 0.0

        passes = self._promotion_state.setdefault("consecutive_passes", {})
        history = self._promotion_state.setdefault("history", [])
        delta = candidate_score - baseline_score

        if delta >= self.promotion_min_index_delta:
            passes[candidate_model] = passes.get(candidate_model, 0) + 1
            viki_logger.info(
                "Promotion gate: %s passed evaluation %d/%d (delta=%.3f).",
                candidate_model,
                passes[candidate_model],
                self.promotion_min_consecutive_passes,
                delta,
            )
        else:
            passes[candidate_model] = 0
            history.append({
                "ts": time.time(),
                "candidate": candidate_model,
                "baseline": current_default,
                "candidate_score": candidate_score,
                "baseline_score": baseline_score,
                "decision": "regression",
            })
            self._save_promotion_state()
            await self._rollback_to(current_default)
            return False

        if passes[candidate_model] >= self.promotion_min_consecutive_passes:
            self._promotion_state["previous_default"] = current_default
            self._promotion_state["current_default"] = candidate_model
            history.append({
                "ts": time.time(),
                "candidate": candidate_model,
                "baseline": current_default,
                "candidate_score": candidate_score,
                "baseline_score": baseline_score,
                "decision": "promoted",
            })
            passes[candidate_model] = 0
            self._save_promotion_state()
            self._apply_default_model(candidate_model)
            return True

        self._save_promotion_state()
        return False

    async def _rollback_to(self, model_name: Optional[str]) -> None:
        """Auto-rollback to the previous default on regression."""
        if not model_name:
            return
        viki_logger.warning("ContinuousLearner: rolling back default model to %s", model_name)
        self._apply_default_model(model_name)

    def force_promote(self, model_name: str, operator: str = "operator") -> Dict[str, Any]:
        """
        P1: operator-initiated promotion. Bypasses the consecutive-passes
        gate but still records the action in promotion history.
        """
        if not model_name:
            return {"ok": False, "error": "model_name required"}
        previous = self._promotion_state.get("current_default") or (
            (self.controller.models_config or {}).get("models", {}).get("default")
        )
        self._promotion_state["previous_default"] = previous
        self._promotion_state["current_default"] = model_name
        history = self._promotion_state.setdefault("history", [])
        history.append({
            "ts": time.time(),
            "candidate": model_name,
            "baseline": previous,
            "decision": "force_promoted",
            "operator": operator,
        })
        self._save_promotion_state()
        self._apply_default_model(model_name)
        return {"ok": True, "new_default": model_name, "previous": previous}

    def force_rollback(self, model_name: Optional[str] = None, operator: str = "operator") -> Dict[str, Any]:
        """
        P1: operator-initiated rollback to the recorded previous default,
        or to an explicit `model_name` if provided.
        """
        target = model_name or self._promotion_state.get("previous_default")
        if not target:
            return {"ok": False, "error": "no previous default recorded"}
        previous = self._promotion_state.get("current_default")
        self._promotion_state["current_default"] = target
        self._promotion_state["previous_default"] = previous
        history = self._promotion_state.setdefault("history", [])
        history.append({
            "ts": time.time(),
            "candidate": target,
            "baseline": previous,
            "decision": "force_rolled_back",
            "operator": operator,
        })
        self._save_promotion_state()
        self._apply_default_model(target)
        return {"ok": True, "new_default": target, "previous": previous}

    @staticmethod
    def _same_model_tag(left: Optional[str], right: Optional[str]) -> bool:
        if not left or not right:
            return False
        l = left.strip().lower()
        r = right.strip().lower()
        aliases_l = {l}
        aliases_r = {r}
        if l.endswith(":latest"):
            aliases_l.add(l[: -len(":latest")])
        elif ":" not in l:
            aliases_l.add(f"{l}:latest")
        if r.endswith(":latest"):
            aliases_r.add(r[: -len(":latest")])
        elif ":" not in r:
            aliases_r.add(f"{r}:latest")
        return bool(aliases_l & aliases_r)

    def _default_profile_for_model(self, model_name: str) -> tuple[str, Optional[str]]:
        """
        Resolve a candidate model/tag to the profile key that should become
        `models.default`. If a raw Ollama tag is promoted, reuse the
        `viki-evolved` profile when available and retarget its `model_name`.
        """
        mc = self.controller.models_config or {}
        models_root = mc.setdefault("models", {})
        profiles = models_root.get("profiles") or {}
        if model_name in profiles:
            return model_name, None
        for profile_name, profile in profiles.items():
            if isinstance(profile, dict) and self._same_model_tag(profile.get("model_name"), model_name):
                return profile_name, None
        if "viki-evolved" in profiles:
            return "viki-evolved", model_name
        return model_name, None

    def _apply_default_model(self, model_name: str) -> None:
        try:
            mc = self.controller.models_config or {}
            models_root = mc.setdefault("models", {})
            profile_name, retarget_model_name = self._default_profile_for_model(model_name)
            models_root["default"] = profile_name
            if retarget_model_name:
                profiles = models_root.setdefault("profiles", {})
                profile = profiles.setdefault(profile_name, {})
                if isinstance(profile, dict):
                    profile["model_name"] = retarget_model_name
            # Persist to disk if possible.
            cfg_path = getattr(self.controller, "models_config_path", None)
            if not cfg_path:
                cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
                cfg_path = os.path.abspath(cfg_path)
            if os.path.isfile(cfg_path):
                try:
                    import yaml  # type: ignore

                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    data_models = data.setdefault("models", {})
                    data_models["default"] = profile_name
                    if retarget_model_name:
                        profiles = data_models.setdefault("profiles", {})
                        profile = profiles.setdefault(profile_name, {})
                        if isinstance(profile, dict):
                            profile["model_name"] = retarget_model_name
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(data, f, sort_keys=False)
                except Exception as e:
                    viki_logger.debug("ContinuousLearner: failed to rewrite models.yaml: %s", e)
            viki_logger.info("ContinuousLearner: default model profile now %s (%s)", profile_name, model_name)
        except Exception as e:
            viki_logger.warning("ContinuousLearner: apply default failed: %s", e)
