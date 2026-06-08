
import asyncio
import os
import sys

# Add viki to path
sys.path.append(os.path.abspath("."))

from skills.builtins.code_search_skill import CodeSearchSkill

async def main():
    skill = CodeSearchSkill()
    # Force scan of workspace
    workspace = os.path.abspath("workspace")
    print(f"Scanning {workspace}...")
    skill.scan(workspace, incremental=False)
    
    print("\nSearching for 'viki_secret_key_12345'...")
    results = skill.search("viki_secret_key_12345")
    
    if not results:
        print("FAIL: No results found for global content!")
    else:
        print(f"SUCCESS: Found {len(results)} results.")
        for r in results:
            print(f"Match in {r.path} lines {r.start_line}-{r.end_line}")

if __name__ == "__main__":
    asyncio.run(main())
