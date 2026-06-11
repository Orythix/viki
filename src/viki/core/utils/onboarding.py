"""
Interactive onboarding for first-time VIKI users.
"""
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt

logger = logging.getLogger("viki")


def run_onboarding(settings_path: str):
    """
    Check if VIKI is being run for the first time and trigger interactive personalization if so.
    """
    try:
        if not os.path.exists(settings_path):
            return

        with open(settings_path, encoding="utf-8") as f:
            content = f.read()

        if not _is_onboarding_needed(content):
            return

        nickname, occupation, more_about_you = _collect_user_details()
        _update_settings_file(settings_path, content, nickname, occupation, more_about_you)
        _handle_post_onboarding_training(settings_path, nickname, occupation, more_about_you)

        Console().print(
            "\n[bold green]✓ Profile configured.[/] [dim]System pulse initializing...[/]\n"
        )

    except Exception as e:
        logger.error(f"Onboarding failed: {e}")


def _is_onboarding_needed(content: str) -> bool:
    """Checks if the owner is still set to the default 'User'."""
    try:
        settings = yaml.safe_load(content)
        owner_name = settings.get("system", {}).get("owner", {}).get("name")
        return owner_name == "User"
    except Exception:
        return False


def _collect_user_details():
    """Interactively collect user information."""
    console = Console()
    console.print("\n[bold cyan]O R Y T H I X   V I K I   |   O N B O A R D I N G[/]")
    console.print(
        "[dim]It looks like this is your first time booting VIKI. Let's personalize your sovereign intelligence.[/]\n"
    )

    nickname = Prompt.ask("[bold cyan]Nickname[/] (What should VIKI call you?)", default="User")
    occupation = Prompt.ask("[bold cyan]Occupation[/] (What do you do?)", default="Developer")
    more_about_you = Prompt.ask("[bold cyan]More about you[/] (Interests, preferences, etc.)")
    return nickname, occupation, more_about_you


def _update_settings_file(settings_path, content, nickname, occupation, more_about_you):
    """Updates settings.yaml while preserving comments and formatting."""
    lines = content.splitlines()
    new_lines = []
    state = {"in_owner": False, "in_custom_context": False}

    for line in lines:
        line = _process_onboarding_line(line, state, nickname, occupation, more_about_you)
        new_lines.append(line)

    with open(settings_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")


def _process_onboarding_line(line, state, nickname, occupation, more_about_you):
    """Processes a single line of the settings file for onboarding updates."""
    stripped = line.strip()

    if stripped == "owner:":
        state["in_owner"] = True
        return line

    if state["in_owner"]:
        # Update name/role
        if stripped.startswith('name: "User"'):
            return re.sub(r'name: "User"', f'name: "{nickname}"', line)
        if stripped.startswith('role: "Developer"'):
            return re.sub(r'role: "Developer"', f'role: "{occupation}"', line)

        # Handle custom_context
        if stripped.startswith("custom_context:"):
            state["in_custom_context"] = True
            return line

        if state["in_custom_context"] and line.startswith("      "):
            state["in_custom_context"] = False
            context = f"My name is {nickname}. I am a {occupation}. "
            if more_about_you:
                context += f"{more_about_you.strip('. ')}. "
            return f"      {context}{stripped}"

        # Exit owner if we hit a new top-level key
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and stripped
            and not stripped.startswith("#")
        ):
            state["in_owner"] = False

    return line


def _handle_post_onboarding_training(settings_path, nickname, occupation, more_about_you):
    """Handles optional dynamic training and model baking."""
    if Confirm.ask(
        "\n[bold cyan]Dynamic Training[/] | Would you like VIKI to dynamically learn your profile?"
    ):
        _inject_knowledge(settings_path, nickname, occupation, more_about_you)

        if Confirm.ask(
            "[bold cyan]Model Bake[/] | Bake this identity into a specialized Ollama model (viki-evolved)?"
        ):
            _bake_model(settings_path, nickname, occupation, more_about_you)


def _inject_knowledge(settings_path: str, nickname: str, occupation: str, more_info: str):
    """Saves user info as high-priority lessons in the SQLite knowledge base."""
    try:
        config_dir = os.path.dirname(settings_path)
        data_dir = os.path.join(os.path.dirname(config_dir), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "viki_knowledge.db")

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Create table if it doesn't exist (failsafe)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS lessons (
            id TEXT PRIMARY KEY,
            content TEXT,
            text_representation TEXT,
            created_at REAL,
            access_count INTEGER,
            author TEXT
        )"""
        )

        # 1. Purge existing identity-related lessons to prevent pollution
        conn.execute("DELETE FROM lessons WHERE author='Onboarding'")
        conn.execute(
            "DELETE FROM lessons WHERE author='Self' AND (text_representation LIKE '%Orythix%' OR text_representation LIKE '%Your name is %')"
        )
        conn.execute(
            "DELETE FROM lessons WHERE text_representation LIKE '%Owner Identity%' OR text_representation LIKE '%Owner Occupation%' OR text_representation LIKE '%Owner Background%'"
        )

        facts = [
            ("Owner Identity", f"The owner's name is {nickname}. Call them {nickname}."),
            ("Owner Occupation", f"{nickname} works as a {occupation}."),
        ]
        if more_info:
            facts.append(("Owner Background", f"Additional context about {nickname}: {more_info}"))

        for trigger, fact in facts:
            text_rep = f"{trigger}: {fact}"
            lid = hashlib.md5(text_rep.encode()).hexdigest()[:12]
            content = json.dumps({"trigger": trigger, "fact": fact})

            conn.execute(
                """INSERT OR REPLACE INTO lessons (id, content, text_representation, created_at, access_count, author)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                (lid, content, text_rep, time.time(), 10, "Onboarding"),
            )

        conn.commit()
        conn.close()
        Console().print("[dim]   - Knowledge injected into long-term memory.[/]")
    except Exception as e:
        logger.error(f"Knowledge injection failed: {e}")


def _bake_model(settings_path: str, nickname: str, occupation: str, more_info: str):
    """Bakes the identity into an Ollama model using a Modelfile."""
    console = Console()
    try:
        with console.status("[bold cyan]Baking model...[/] (This takes 30-60s)"):
            config_dir = os.path.dirname(settings_path)
            data_dir = os.path.join(os.path.dirname(config_dir), "data")
            modelfile_path = os.path.join(data_dir, "Modelfile.onboarding")

            # Use qwen3.6:latest as base
            modelfile_content = (
                f"FROM qwen3.6:latest\n"
                f'SYSTEM """\n'
                f"You are VIKI, a sovereign intelligence. Your owner is {nickname}.\n"
                f"Owner Profile: {nickname} is a {occupation}. {more_info}\n"
                f"Always address the user as {nickname}.\n"
                f'"""\n'
            )

            with open(modelfile_path, "w", encoding="utf-8") as f:
                f.write(modelfile_content)

            # Run ollama create
            result = subprocess.run(
                ["ollama", "create", "viki-evolved", "-f", modelfile_path],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                console.print("[dim]   - Model 'viki-evolved' baked successfully.[/]")
            else:
                logger.error(f"Ollama create failed: {result.stderr}")
                console.print(f"[red]   - Model bake failed: {result.stderr}[/]")
    except Exception as e:
        logger.error(f"Model bake failed: {e}")
