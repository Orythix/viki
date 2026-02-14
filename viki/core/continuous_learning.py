"""
Continuous Learning Pipeline
Manages automated model improvement cycles.
"""
import time
import asyncio
from typing import Dict, Any
from viki.config.logger import viki_logger


class ContinuousLearner:
    """Manages automated model improvement cycles."""
    
    def __init__(self, controller):
        self.controller = controller
        self.training_schedule = "weekly"  # daily, weekly, monthly
        self.min_lessons_for_training = 100
        self.last_training_time = 0
        self.training_enabled = True
    
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
            export_result = self.controller.learning.export_training_dataset(dataset_path, format='jsonl')
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
                new_model_name = "viki-born-again"  # Default forge output
                viki_logger.info(f"ContinuousLearner: Validating {new_model_name}...")
                
                is_valid = await self._validate_model(new_model_name)
                
                if is_valid:
                    viki_logger.info(f"ContinuousLearner: Validation passed for {new_model_name}")
                    # Note: Model is already created, user can manually switch to it
                    # Auto-switching could be dangerous, so we just log success
                    self.last_training_time = time.time()
                    
                    # Log to learning for future reference
                    self.controller.learning.save_lesson(
                        trigger="Model training completed",
                        fact=f"Successfully trained {new_model_name} with {self.controller.learning.get_total_lesson_count()} lessons",
                        source="continuous_learning"
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
            'ready_to_train': lesson_count >= self.min_lessons_for_training and time_since_last >= self._schedule_to_seconds()
        }
