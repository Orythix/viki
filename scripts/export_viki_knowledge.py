import json
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="Export VIKI semantic lessons to training dataset.")
    parser.add_argument("--json", type=str, default="data/lessons_semantic.json", help="Path to lessons_semantic.json")
    parser.add_argument("--output", type=str, default="viki_knowledge.txt", help="Output file name")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.json):
        print(f"Error: Knowledge file {args.json} not found.")
        return

    try:
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        lessons = data.get('lessons', [])
        
        if not lessons:
            print("No lessons found.")
            return

        with open(args.output, 'w', encoding='utf-8') as f:
            for lesson in lessons:
                # Format as facts for fine-tuning
                f.write(f"FACT: {lesson}\n")
        
        print(f"Exported {len(lessons)} knowledge items to {args.output}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
