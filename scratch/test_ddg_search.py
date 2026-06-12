import sys

try:
    from ddgs import DDGS

    print("Imported DDGS from ddgs")
except ImportError:
    try:
        from duckduckgo_search import DDGS

        print("Imported DDGS from duckduckgo_search")
    except ImportError:
        print("Failed to import DDGS")
        sys.exit(1)

try:
    with DDGS() as ddgs:
        # Try default parameters
        res = list(ddgs.text("latest Angular version", max_results=5))
        print(f"Results with text(): {res}")
except Exception as e:
    print(f"Error calling text(): {e}")

try:
    with DDGS() as ddgs:
        # Try with region, safesearch
        res = list(
            ddgs.text("latest Angular version", region="wt-wt", safesearch="off", max_results=5)
        )
        print(f"Results with params: {res}")
except Exception as e:
    print(f"Error calling text() with params: {e}")
