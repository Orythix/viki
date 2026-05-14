import re
from typing import List, Optional

def condense_text(text: str, max_chars: int = 3000, query: Optional[str] = None) -> str:
    """
    Condenses text for local LLM consumption.
    1. Removes boilerplate lines.
    2. Collapses whitespace.
    3. If query is provided, prioritizes blocks containing query terms.
    """
    if not text:
        return ""

    # 1. Basic Cleanup
    # Collapse horizontal whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    # Filter out common boilerplate lines
    lines = text.splitlines()
    cleaned_lines = []
    
    boilerplate_keywords = [
        "cookie", "privacy policy", "terms of use", "subscribe", 
        "sign in", "log in", "all rights reserved", "copyright",
        "skip to content", "menu", "navigation"
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line) < 10: # Skip very short snippets
            continue
        lower_line = line.lower()
        if any(kw in lower_line for kw in boilerplate_keywords):
            continue
        cleaned_lines.append(line)

    # 2. Query-based Prioritization
    if query and len(cleaned_lines) > 20:
        query_terms = set(re.findall(r'\w+', query.lower()))
        scored_lines = []
        for line in cleaned_lines:
            line_terms = set(re.findall(r'\w+', line.lower()))
            score = len(query_terms & line_terms)
            scored_lines.append((score, line))
        
        # Keep lines with scores > 0, or at least some context
        # Sort by original order, but filter by score
        # We want to keep some non-scoring lines for flow
        final_lines = []
        for i, (score, line) in enumerate(scored_lines):
            if score > 0:
                final_lines.append(line)
            elif i < 5 or i > len(scored_lines) - 5: # Keep start/end
                final_lines.append(line)
        cleaned_lines = final_lines

    # 3. Final Assembly and Truncation
    result = "\n".join(cleaned_lines)
    if len(result) > max_chars:
        # Try to truncate at a newline
        trunc_point = result.rfind('\n', 0, max_chars)
        if trunc_point == -1:
            trunc_point = max_chars
        result = result[:trunc_point] + "\n... (further content truncated for token efficiency)"
    
    return result

def summarize_heuristic(text: str) -> str:
    """
    Extreme condensation: Keep only headers (lines ending in :) and first sentences.
    """
    lines = text.splitlines()
    summary = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.endswith(':') or len(line) < 80: # Likely a header or title
            summary.append(line)
        else:
            # Keep only the first sentence
            match = re.match(r'[^.!?]+[.!?]', line)
            if match:
                summary.append(match.group(0))
    return "\n".join(summary)
