import sqlite3
import json
import os
import argparse
from typing import List, Dict, Any

def export_to_alpaca(messages: List[Dict[str, Any]], output_file: str):
    dataset = []
    # Alpaca expects Instruction-Input-Output.
    # We'll treat the user prompt as Instruction and VIKI response as Output.
    # Grouping by pairs of User -> Assistant.
    
    for i in range(len(messages) - 1):
        if messages[i]['role'] == 'user' and messages[i+1]['role'] == 'assistant':
            dataset.append({
                "instruction": messages[i]['content'],
                "input": "",
                "output": messages[i+1]['content']
            })
            
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=4)
    print(f"Exported {len(dataset)} pairs to {output_file} (Alpaca format)")

def export_to_sharegpt(messages: List[Dict[str, Any]], output_file: str):
    dataset = []
    # Group by sessions if possible, or just one long conversation
    # ShareGPT/Conversational format: [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]
    
    # Simple grouping by consecutive pairs
    conversations = []
    for i in range(len(messages)):
        role_map = {'user': 'human', 'assistant': 'gpt'}
        conversations.append({
            "from": role_map.get(messages[i]['role'], messages[i]['role']),
            "value": messages[i]['content']
        })
    
    # Wrap in single entry (or split by session_id if we want multiple short convos)
    # Let's split by sessions
    sessions = {}
    for i in range(len(messages)):
        sid = messages[i].get('session_id', 'default')
        if sid not in sessions: sessions[sid] = []
        
        role_map = {'user': 'human', 'assistant': 'gpt'}
        sessions[sid].append({
            "from": role_map.get(messages[i]['role'], messages[i]['role']),
            "value": messages[i]['content']
        })
    
    sharegpt_dataset = [{"conversations": conv} for conv in sessions.values()]
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sharegpt_dataset, f, indent=4)
    print(f"Exported {len(sharegpt_dataset)} sessions to {output_file} (ShareGPT format)")

def main():
    parser = argparse.ArgumentParser(description="Export VIKI memory to training dataset.")
    parser.add_argument("--db", type=str, default="data/viki_memory.db", help="Path to viki_memory.db")
    parser.add_argument("--output", type=str, default="viki_dataset.json", help="Output file name")
    parser.add_argument("--format", type=str, choices=["alpaca", "sharegpt"], default="sharegpt", help="Dataset format")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db):
        print(f"Error: Database {args.db} not found.")
        return

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT role, content, session_id, timestamp FROM messages ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        messages = [dict(row) for row in rows]
    except Exception as e:
        print(f"Error reading database: {e}")
        return
    finally:
        conn.close()

    if not messages:
        print("No messages found in database.")
        return

    if args.format == "alpaca":
        export_to_alpaca(messages, args.output)
    else:
        export_to_sharegpt(messages, args.output)

if __name__ == "__main__":
    main()
