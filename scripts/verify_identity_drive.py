import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


def main():
    print(
        "This script has moved to tests/integration/ \u2014 run 'pytest tests/integration/ -m slow' instead"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
