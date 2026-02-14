# Contributing to VIKI

First off, thank you for considering contributing to VIKI! It's people like you that make VIKI a more powerful and sovereign digital intelligence.

As an agent of Orythix001, your contributions help push the boundaries of local-first, private, and autonomous AI.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [What Should I Know Before I Get Started?](#what-should-i-know-before-i-get-started)
3. [How Can I Contribute?](#how-can-i-contribute)
    * [Reporting Bugs](#reporting-bugs)
    * [Suggesting Enhancements](#suggesting-enhancements)
    * [Pull Requests](#pull-requests)
4. [Styleguides](#styleguides)
    * [Git Commit Messages](#git-commit-messages)
    * [Python Styleguide](#python-styleguide)
    * [JavaScript Styleguide](#javascript-styleguide)

## Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all. Please be respectful and collaborative in all interactions.

## What Should I Know Before I Get Started?

VIKI is built on the **Orythix Cognitive Architecture**. This means:
*   **Privacy First**: No telemetry or external data leaks.
*   **Local Execution**: Primary focus is on Ollama and local LLMs.
*   **Modular Skills**: Capabilities are gated by a security-first registry.

## How Can I Contribute?

### Reporting Bugs

*   **Check the Issues**: Search if the bug has already been reported.
*   **Use the Template**: If not, open a new issue and include:
    *   A clear title and description.
    *   Steps to reproduce the bug.
    *   Your environment (OS, Python version, Ollama model).
    *   Relevant logs from `logs/viki.log`.

### Suggesting Enhancements

*   **Explain the Use Case**: Why is this feature needed? How does it help VIKI's evolution?
*   **Describe the Goal**: What should the feature do?

### Pull Requests

1.  **Fork the repo** and create your branch from `main`.
2.  **Ensure tests pass**: Run `pytest` and verify UI stability.
3.  **Update documentation**: If you change a skill or API, update the relevant `.md` files.
4.  **Submit the PR**: Reference any related issues.

## Styleguides

### Git Commit Messages

We use conventional commits:
*   `feat:`: A new feature.
*   `fix:`: A bug fix.
*   `docs:`: Documentation changes.
*   `style:`: Formatting, missing semi colons, etc; no code change.
*   `refactor:`: Refactoring production code.
*   `test:`: Adding missing tests, refactoring tests.

### Python Styleguide

*   Follow **PEP 8**.
*   Use type hints where possible.
*   Document large functions with docstrings.
*   Wrap complex logic in `asyncio.to_thread` if it involves blocking I/O to keep the cognitive loop responsive.

### JavaScript Styleguide

*   Use functional components with React Hooks.
*   Ensure components are responsive and follow the HSL dark-mode theme.
*   Maintain the "Hologram" aesthetic for UI components.

## Need Help?

If you have questions, feel free to open a discussion or contact the Orythix001 team.

---

**VIKI: Virtual Intelligence, Real Evolution.**
Designed by Orythix001. 2026.
