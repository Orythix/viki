"""
A/B Testing Framework for Model Comparison
Enables data-driven model selection and validation.
"""
import time
import asyncio
from typing import Dict, Any, List
from viki.config.logger import viki_logger


class ModelABTest:
    """A/B test new models against current model."""
    
    def __init__(self, controller):
        self.controller = controller
        self.test_prompts = self._load_default_test_prompts()
    
    def _load_default_test_prompts(self) -> List[Dict[str, Any]]:
        """Load default test prompts for model comparison."""
        return [
            {
                'prompt': 'What is 2 + 2?',
                'expected_keywords': ['4', 'four'],
                'category': 'basic_math'
            },
            {
                'prompt': 'Write a Python function to calculate factorial.',
                'expected_keywords': ['def', 'factorial', 'return'],
                'category': 'coding'
            },
            {
                'prompt': 'Explain what machine learning is in one sentence.',
                'expected_keywords': ['algorithm', 'data', 'learn'],
                'category': 'explanation'
            },
            {
                'prompt': 'What are three benefits of exercise?',
                'expected_keywords': ['health', 'fitness', 'benefit'],
                'category': 'reasoning'
            },
            {
                'prompt': 'Translate "hello world" to Spanish.',
                'expected_keywords': ['hola', 'mundo'],
                'category': 'translation'
            },
            {
                'prompt': 'What is the capital of France?',
                'expected_keywords': ['Paris'],
                'category': 'factual'
            },
            {
                'prompt': 'List three programming languages.',
                'expected_keywords': ['Python', 'Java', 'JavaScript', 'C++', 'Ruby'],
                'category': 'listing'
            },
            {
                'prompt': 'Summarize the importance of clean code.',
                'expected_keywords': ['maintainable', 'readable', 'quality'],
                'category': 'summarization'
            },
        ]
    
    async def compare_models(self, model_a_name: str, model_b_name: str) -> Dict[str, Any]:
        """Compare two models on test prompts."""
        viki_logger.info(f"A/B Test: Comparing {model_a_name} vs {model_b_name}")
        
        model_a = self.controller.model_router.models.get(model_a_name)
        model_b = self.controller.model_router.models.get(model_b_name)
        
        if not model_a:
            return {'error': f"Model {model_a_name} not found"}
        if not model_b:
            return {'error': f"Model {model_b_name} not found"}
        
        results = {
            'model_a': {
                'name': model_a_name,
                'scores': [],
                'latencies': [],
                'errors': 0
            },
            'model_b': {
                'name': model_b_name,
                'scores': [],
                'latencies': [],
                'errors': 0
            },
            'test_count': len(self.test_prompts)
        }
        
        # Test each prompt on both models
        for i, test_case in enumerate(self.test_prompts):
            viki_logger.debug(f"A/B Test: Running test {i+1}/{len(self.test_prompts)}")
            
            # Test model A
            response_a, latency_a, error_a = await self._test_model(model_a, test_case)
            score_a = self._score_response(test_case, response_a)
            
            results['model_a']['scores'].append(score_a)
            results['model_a']['latencies'].append(latency_a)
            if error_a:
                results['model_a']['errors'] += 1
            
            # Test model B
            response_b, latency_b, error_b = await self._test_model(model_b, test_case)
            score_b = self._score_response(test_case, response_b)
            
            results['model_b']['scores'].append(score_b)
            results['model_b']['latencies'].append(latency_b)
            if error_b:
                results['model_b']['errors'] += 1
            
            # Small delay between tests
            await asyncio.sleep(0.5)
        
        # Calculate aggregates
        results['model_a']['avg_score'] = sum(results['model_a']['scores']) / len(results['model_a']['scores'])
        results['model_a']['avg_latency'] = sum(results['model_a']['latencies']) / len(results['model_a']['latencies'])
        
        results['model_b']['avg_score'] = sum(results['model_b']['scores']) / len(results['model_b']['scores'])
        results['model_b']['avg_latency'] = sum(results['model_b']['latencies']) / len(results['model_b']['latencies'])
        
        # Determine winner (weighted: 70% score, 30% speed)
        score_a_weighted = results['model_a']['avg_score'] * 0.7 - (results['model_a']['avg_latency'] / 10.0) * 0.3
        score_b_weighted = results['model_b']['avg_score'] * 0.7 - (results['model_b']['avg_latency'] / 10.0) * 0.3
        
        results['winner'] = model_a_name if score_a_weighted > score_b_weighted else model_b_name
        results['score_difference'] = abs(score_a_weighted - score_b_weighted)
        
        viki_logger.info(f"A/B Test Complete: Winner is {results['winner']} "
                        f"(Score: A={results['model_a']['avg_score']:.2f}, B={results['model_b']['avg_score']:.2f})")
        
        return results
    
    async def _test_model(self, model, test_case: Dict) -> tuple:
        """Test a model with a single prompt. Returns (response, latency, error)."""
        prompt = test_case['prompt']
        messages = [
            {'role': 'system', 'content': 'You are VIKI, a helpful AI assistant.'},
            {'role': 'user', 'content': prompt}
        ]
        
        try:
            start_time = time.time()
            response = await model.chat(messages, temperature=0.7)
            latency = time.time() - start_time
            
            return response, latency, False
        
        except Exception as e:
            viki_logger.warning(f"Model test failed: {e}")
            return "", 0.0, True
    
    def _score_response(self, test_case: Dict, response: str) -> float:
        """Score response quality (0-1)."""
        if not response:
            return 0.0
        
        score = 0.5  # Baseline
        
        # 1. Length check (reasonable response)
        if 10 < len(response) < 500:
            score += 0.15
        elif len(response) >= 500:
            score += 0.05  # Too long is less preferred
        
        # 2. Contains expected keywords
        expected = test_case.get('expected_keywords', [])
        if expected:
            response_lower = response.lower()
            matches = sum(1 for kw in expected if kw.lower() in response_lower)
            keyword_score = min(0.3, (matches / len(expected)) * 0.3)
            score += keyword_score
        
        # 3. Not a placeholder response
        placeholders = ['processing', 'thinking', 'one moment', 'working on it', 'please wait']
        if not any(p in response.lower() for p in placeholders):
            score += 0.1
        
        # 4. Contains proper formatting (for code)
        if test_case.get('category') == 'coding':
            if 'def ' in response or 'function' in response or '```' in response:
                score += 0.1
        
        # 5. Not an error message
        error_indicators = ['error', 'failed', 'cannot', 'unable', 'sorry']
        if not any(err in response.lower() for err in error_indicators):
            score += 0.05
        
        return min(1.0, score)
    
    def load_custom_test_prompts(self, prompts: List[Dict[str, Any]]):
        """Load custom test prompts for specialized testing."""
        self.test_prompts = prompts
        viki_logger.info(f"Loaded {len(prompts)} custom test prompts")
    
    async def quick_validation(self, model_name: str) -> Dict[str, Any]:
        """Quick validation of a single model."""
        model = self.controller.model_router.models.get(model_name)
        
        if not model:
            return {'error': f"Model {model_name} not found"}
        
        results = {
            'model': model_name,
            'scores': [],
            'latencies': [],
            'errors': 0
        }
        
        # Test on subset of prompts (faster)
        test_subset = self.test_prompts[:5]
        
        for test_case in test_subset:
            response, latency, error = await self._test_model(model, test_case)
            score = self._score_response(test_case, response)
            
            results['scores'].append(score)
            results['latencies'].append(latency)
            if error:
                results['errors'] += 1
        
        results['avg_score'] = sum(results['scores']) / len(results['scores'])
        results['avg_latency'] = sum(results['latencies']) / len(results['latencies'])
        results['passed'] = results['avg_score'] > 0.6 and results['errors'] == 0
        
        viki_logger.info(f"Validation: {model_name} - Score: {results['avg_score']:.2f}, "
                        f"Latency: {results['avg_latency']:.2f}s, Passed: {results['passed']}")
        
        return results
