# VIKI Improvement Plan — Brain, Skills & Architecture
## Generated: 2026-02-12 | Based on full codebase audit
## Last Updated: 2026-02-12 10:58 IST

---

## CURRENT STATE AUDIT

### What Works ✅
- 5-layer Cortex (Perception → Interpretation → Deliberation → Reflection → Meta-Cognition)
- Judgment Engine routing (REFLEX/SHALLOW/DEEP/REFUSE)
- Local Ollama LLM (viki-evolved) + OpenAI API fallback
- 17 registered skills + aliases
- Conversation memory (just added)
- URL auto-fetching (just added)
- Media control via OS-level keys
- System control with 30+ app whitelist
- Soul personality injection
- Cognitive Signals (frustration/confidence/urgency/curiosity)
- World Model (persistent state)
- Learning Module (semantic + lessons)
- Intelligence Scorecard + Benchmark suite

### What's Broken or Stub-Only 🔴
- `InterpretationLayer` (Layer 2) — returns hardcoded dict, no actual intent parsing
- `ReflectionLayer` (Layer 4) — pass-through, no self-critique
- `MetaCognitionLayer` (Layer 5) — hardcoded "Process was optimal"
- World Model understanding not injected into LLM prompts
- Cognitive Signals modulation built but never applied to prompt
- Dream Module — stub (watches for idle, does nothing)
- Reflector — generates candidate prompts but never applies them
- BioModule — unknown state (not audited)
- Skill discovery — `discover_skills()` is empty
- Long-term memory — disabled by default, no implementation
- `VIKIResponse.final_thought` is forced by heuristics — model can't produce it naturally
- Research skill — DuckDuckGo returns garbage results (Chinese Baidu pages)

---

## PHASE 1: FIX THE FUNDAMENTALS ✅ DONE
*Make what exists actually work properly*

### 1.1 Fix ThoughtObject — Simplify LLM Schema
**Problem**: The `ThoughtObject` has 10 fields (intent_vector, assumptions, constraints, risk_score, rejected_strategies, symbolic_graph, provenance...) that local models can't fill. 6 out of 6 heuristic patches exist just to force this.
**Solution**:
- Create `ThoughtObjectLite` with only 3 fields: `intent_summary`, `primary_strategy`, `confidence`
- Use `ThoughtObjectLite` for SHALLOW, full `ThoughtObject` for DEEP
- Remove all 6 FIX patches from `llm.py` — they won't be needed

**Files**: `schema.py`, `llm.py`, `cortex.py`
**Effort**: Low | **Impact**: High

### 1.2 Fix Research Skill — Switch to `ddgs`
**Problem**: `duckduckgo_search` package is deprecated (renamed to `ddgs`). Returns garbage.
**Solution**:
- `pip install ddgs`
- Update import: `from ddgs import DDGS`
- Add region parameter: `ddgs.text(query, region='wt-wt', max_results=5)`
- Add `safesearch='off'` for unfiltered results

**Files**: `research_skill.py`, `requirements.txt`
**Effort**: Low | **Impact**: High

### 1.3 Inject World Model + Signals into LLM Prompt
**Problem**: World understanding and cognitive signals are computed but never used.
**Solution**: In `DeliberationLayer._logic()`, add:
```python
world_context = controller.world.get_understanding()
signals_context = f"Current state: {signals.get_modulation()}"
prompt.add_context(f"{world_context}\n{signals_context}")
```

**Files**: `cortex.py`, `controller.py`
**Effort**: Low | **Impact**: Medium

### 1.4 Fix DuckDuckGo Search Region
**Problem**: Search returns Chinese results because no language/region is set.
**Solution**: Add `region='en-us'` to DDG search call.

**Files**: `research_skill.py`
**Effort**: Trivial | **Impact**: High

---

## PHASE 2: ACTIVATE DORMANT LAYERS ✅ DONE
*Turn stubs into real functionality*

### 2.1 Interpretation Layer — Real Intent Parsing
**Current**: Returns `{"raw_input": data, "estimated_intent": "user_generic_request"}`
**Upgrade**:
- Extract entities (URLs, file paths, app names, numbers)
- Classify intent type (question, command, conversation, code_request)
- Detect sentiment (urgent, casual, frustrated)
- Output enriched context dict that Deliberation uses

```python
class InterpretationLayer(CortexLayer):
    async def _logic(self, data: str) -> Dict[str, Any]:
        # Entity extraction via regex
        urls = re.findall(r'https?://[^\s]+', data)
        files = re.findall(r'[\w/\\]+\.\w{1,5}', data)
        numbers = re.findall(r'\b\d+\.?\d*\b', data)
        
        # Intent classification (keyword-based, fast)
        intent = self._classify(data)
        sentiment = self._detect_sentiment(data)
        
        return {
            "raw_input": data,
            "entities": {"urls": urls, "files": files, "numbers": numbers},
            "intent_type": intent,
            "sentiment": sentiment
        }
```

**Files**: `cortex.py`
**Effort**: Medium | **Impact**: High

### 2.2 Reflection Layer — Post-Decision Self-Critique
**Current**: Pass-through, does nothing.
**Upgrade**:
- Check if the action makes sense for the intent
- Detect hallucination patterns (references to things not in context)
- Verify skill_name exists in registry
- If confidence < 0.3, escalate to DEEP

```python
class ReflectionLayer(CortexLayer):
    def __init__(self, skill_registry=None):
        self.skill_registry = skill_registry

    async def _logic(self, response: VIKIResponse) -> VIKIResponse:
        # Validate action references valid skill
        if response.action and self.skill_registry:
            if not self.skill_registry.get_skill(response.action.skill_name):
                response.action = None  # Remove invalid action
                response.final_response += " (I couldn't find the right tool for this.)"
        
        # Check for hallucination markers
        if response.final_response:
            hallucination_phrases = ["I've reviewed", "I can see that", "Based on my analysis"]
            # If these appear without URL context, flag it
            ...
        
        return response
```

**Files**: `cortex.py`
**Effort**: Medium | **Impact**: High

### 2.3 MetaCognition Layer — Real Process Optimization
**Current**: Hardcoded "Process was optimal"
**Upgrade**:
- Track latency per layer
- Detect if reasoning was too slow → recommend REFLEX caching
- Auto-learn: if same input pattern succeeds 3x, suggest adding to reflex patterns

**Files**: `cortex.py`
**Effort**: Medium | **Impact**: Medium

---

## PHASE 3: SMARTER BRAIN ✅ DONE
*Upgrade reasoning quality*

### 3.1 Multi-Model Routing per Layer
**Current**: Same model for everything.
**Upgrade**:
- SHALLOW → use `phi3` (fast, 3B params)
- DEEP → use `deepseek-r1` (reasoning specialist)
- VISION → use `llava`
- CODING → use `deepseek-coder`
- The ModelRouter already supports capabilities — just wire it up

**Files**: `cortex.py`, `controller.py`
**Effort**: Low | **Impact**: High

### 3.2 ReAct Loop (Reason + Act iteratively)
**Current**: Single-shot: LLM thinks once → one action → done.
**Upgrade**: Allow multi-step reasoning:
```
User: "Find my IP address and scan my local network"
Step 1: LLM decides → action: python_interpreter(code="import socket; ...")
Step 2: Result fed back → LLM decides → action: security_tools(action='net_scan')
Step 3: Result fed back → LLM synthesizes final answer
```

**Architecture**:
```python
for step in range(max_steps):
    viki_resp = await self.cortex.process(current_context)
    if viki_resp.action:
        result = await execute_skill(viki_resp.action)
        current_context += f"\nAction Result: {result}"
    else:
        break  # No more actions needed
return viki_resp.final_response
```

**Files**: `controller.py`
**Effort**: High | **Impact**: Very High (this is what makes an "agent" vs a "chatbot")

### 3.3 Tool-Use Schema (Function Calling)
**Current**: LLM guesses skill names from a text list.
**Upgrade**: Use proper JSON function-calling schema:
```json
{
  "tools": [
    {
      "name": "media_control",
      "description": "Control media playback",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["play_pause", "next_track", "volume_up"]}
        }
      }
    }
  ]
}
```
Ollama supports this via the `tools` parameter in `/api/chat`.

**Files**: `llm.py`, `base.py` (add `schema` property to skills), `cortex.py`
**Effort**: High | **Impact**: Very High (eliminates 90% of parsing issues)

---

## PHASE 4: NEW SKILLS ✅ DONE

### 4.1 Clipboard Skill
- Read/write system clipboard
- `pyperclip` library
- Useful for: "copy this", "paste what I copied"

### 4.2 Window Manager Skill
- List open windows (`pygetwindow`)
- Focus/minimize/maximize specific windows
- "switch to Chrome", "minimize all windows"

### 4.3 Screenshot + OCR Skill
- Take screenshots (`pyautogui.screenshot()`)
- OCR with `pytesseract` or local vision model
- "what's on my screen?", "read the error message"

### 4.4 Email/Calendar Skill
- Read emails via IMAP
- Send emails via SMTP
- Calendar integration (Google Calendar API)

### 4.5 Shell Command Skill
- Execute PowerShell/CMD commands
- With safety sandboxing (no `rm -rf`, no `format`)
- "how much disk space do I have?", "list running processes"

### 4.6 Notification Skill
- Windows toast notifications via `win10toast` or `plyer`
- Scheduled reminders: "remind me in 30 minutes to..."

---

## PHASE 5: LONG-TERM EVOLUTION ✅ DONE

### 5.1 Persistent Long-Term Memory
- SQLite-backed episodic memory
- Semantic search over past conversations
- User preference learning (preferred apps, coding style, schedule)

### 5.2 Dynamic Skill Auto-Discovery
- Implement `SkillRegistry.discover_skills()` to scan plugin directories
- Hot-reload skills without restart
- User-defined skills via YAML/Python

### 5.3 Voice Interface
- STT: Whisper (local via `faster-whisper`)
- TTS: `piper` or `edge-tts`
- Wake word detection: "Hey VIKI"
- Already have VoiceModule skeleton — flesh it out

### 5.4 Web UI Dashboard
- Already have `viki/ui/` directory
- Real-time WebSocket status
- Conversation history browser
- Skill metrics dashboard
- Settings editor

### 5.5 Multi-Agent Swarm
- Already have `SwarmSkill` skeleton
- Spawn sub-agents for complex tasks
- Parallel execution with result aggregation

---

## PRIORITY ORDER (What to do first)

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| 🔴 P0 | Fix Research Skill (DDG region/package) | High | 15 min |
| 🔴 P0 | Simplify ThoughtObject schema | High | 1 hour |
| 🟡 P1 | Multi-model routing per layer | High | 2 hours |
| 🟡 P1 | Activate Interpretation Layer | High | 3 hours |
| 🟡 P1 | Activate Reflection Layer | High | 2 hours |
| 🟡 P1 | ReAct Loop (multi-step reasoning) | Very High | 4 hours |
| 🟢 P2 | Tool-use schema (function calling) | Very High | 6 hours |
| 🟢 P2 | Clipboard + Window Manager skills | Medium | 2 hours |
| 🟢 P2 | Shell Command skill | Medium | 2 hours |
| 🔵 P3 | Voice interface (STT/TTS) | Medium | 1 day |
| 🔵 P3 | Persistent SQLite memory | Medium | 1 day |
| 🔵 P3 | Web UI Dashboard | Medium | 2 days |
| ⚪ P4 | Multi-agent swarm | Low (for now) | 3 days |
| ⚪ P4 | Self-evolution triggers | Low (for now) | 2 days |

---

## ARCHITECTURE DIAGRAM (Target State)

```
                     ┌─────────────────────────┐
                     │        USER INPUT        │
                     └────────────┬────────────┘
                                  ▼
                     ┌────────────────────────┐
                     │    JUDGMENT ENGINE      │
                     │  (REFLEX/SHALLOW/DEEP)  │
                     └──┬──────────┬──────────┘
                        │          │
              ┌─────────▼──┐  ┌───▼──────────────┐
              │   REFLEX   │  │ CONSCIOUSNESS     │
              │  (Patterns │  │  STACK             │
              │  + Cache)  │  │                    │
              └─────┬──────┘  │ L1: Perception     │
                    │         │ L2: Interpretation  │◄── Entity extraction
                    │         │ L3: Deliberation    │◄── LLM + Skills catalog
                    │         │ L4: Reflection      │◄── Self-critique
                    │         │ L5: MetaCognition   │◄── Process optimization
                    │         └───────┬────────────┘
                    │                 │
                    ▼                 ▼
              ┌──────────────────────────────┐
              │      SKILL EXECUTION         │
              │  ┌─────────┐ ┌────────────┐  │
              │  │ Media   │ │ System     │  │
              │  │ Control │ │ Control    │  │
              │  ├─────────┤ ├────────────┤  │
              │  │Research │ │ Dev Tools  │  │
              │  ├─────────┤ ├────────────┤  │
              │  │Browser  │ │ Security   │  │
              │  ├─────────┤ ├────────────┤  │
              │  │ Voice   │ │ Vision     │  │
              │  └─────────┘ └────────────┘  │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
              │     MEMORY & LEARNING        │
              │  ┌──────────┐ ┌───────────┐  │
              │  │Short-Term│ │World Model│  │
              │  │ (Chat)   │ │(Persistent)│ │
              │  ├──────────┤ ├───────────┤  │
              │  │Long-Term │ │ Lessons   │  │
              │  │ (SQLite) │ │(Semantic) │  │
              │  └──────────┘ └───────────┘  │
              └──────────────────────────────┘
```

---

## PHASE 6: SENSORY INTEGRATION ✅ DONE
*Wake up VIKI and let her see.*

### 6.1 Real-Time Voice Pipeline
- **Hotword Detection**: Implement `Porcupine` or `OpenWakeWord` for efficient "Hey VIKI" listening.
- **Fast TTS**: Replace system TTS with `Piper` or `Kokoro-80m` for neural-quality, low-latency speech.
- **Interruption Handling**: Utilize VAD (Voice Activity Detection) to stop speaking when the user interrupts.

### 6.2 Active Vision
- **Screen Monitoring**: Ability to "watch" the screen for specific events (e.g., "Tell me when the download marks 100%").
- **UI Analysis**: Use `llava` or `moondream` to understand GUI elements that accessibility APIs miss.

---

## PHASE 7: THE NEXUS ✅ DONE
*VIKI everywhere.*

### 7.1 Remote Control (Telegram/Discord)
- **Bridge Module**: Allow chatting with local VIKI via a Telegram bot from your phone.
- **Remote Actions**: "Lock my PC" or "Send me that file" from the phone.

### 7.2 Research Swarm
- **Sub-Agents**: Spawn parallel agents where one browses, one summarizes, and one writes the final report.
- **Map-Reduce**: Aggregate findings from multiple sources automatically.

---

## PHASE 8: THE FORGE ✅ DONE
*The system that builds itself.*

### 8.1 Runtime Skill Creation
- **Code Writing**: Ability to write a new `custom_skill.py` based on user request.
- **Hot-Reloading**: Load the new skill without restarting the main process.

### 8.2 Self-Healing
- **Error Analysis**: When a tool fails, analyze the stack trace and patch the code automatically.
- **Test Generation**: Write unit tests for new skills to ensure stability.

---

## COMPLETED OBJECTIVES (Recap)
- ✅ **Phase 1**: Core Architecture & Schema Fixes
- ✅ **Phase 2**: Cognitive Layers & ReAct Loop
- ✅ **Phase 3**: Multi-Model Routing & Native Tool Use
- ✅ **Phase 4**: OS Control (Windows, Shell, Clipboard, Notifications)
- ✅ **Phase 5**: Long-Term Memory (SQLite) & Plugin Discovery
