#!/usr/bin/env python3
"""Régénère les sections automatiques du README.md.

Chaque section automatique est délimitée par deux marqueurs :

    <!-- AUTO:NOM:START -->
    ... contenu régénéré ...
    <!-- AUTO:NOM:END -->

Tout ce qui se trouve en dehors de ces marqueurs est rédigé à la main et
n'est jamais modifié par ce script.

Usage :
    python scripts/update_readme.py          # met à jour README.md
    python scripts/update_readme.py --check  # code retour 1 si le README n'est pas à jour

Le script n'utilise que la bibliothèque standard et produit un résultat
déterministe : il dépend uniquement du contenu suivi par git, jamais de
l'heure d'exécution.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"

# Présent dans le message des commits générés par la CI : permet de les
# exclure de l'historique affiché.
BOT_TAG = "[readme-bot]"

# Architecture cible (cahier des charges, §19).
ARCHITECTURE = [
    ("app", "Paquet de l'application (point d'entrée : streamlit_app.py)"),
    ("pages", "Pages et tableaux de bord Streamlit"),
    ("domain", "Règles métier : PRU, valorisation, plus-values, devises"),
    ("services", "Orchestration : actualisation, sauvegarde, archivage"),
    ("connectors", "Fournisseurs de données : yfinance, Finnhub, SEC EDGAR, saisie manuelle"),
    ("models", "Modèles SQLAlchemy et schémas Pydantic"),
    ("database", "Accès SQLite et gestion des sessions"),
    ("config", "Paramètres de l'application (clés API hors dépôt)"),
    ("tests", "Tests automatisés"),
    ("migrations", "Migrations de schéma Alembic"),
]

# Stack cible (cahier des charges, §19 et annexe B) : libellé -> paquet PyPI.
STACK = [
    ("Streamlit", "streamlit"),
    ("SQLAlchemy", "sqlalchemy"),
    ("Alembic", "alembic"),
    ("Pandas", "pandas"),
    ("Pydantic", "pydantic"),
    ("Plotly", "plotly"),
    ("yfinance", "yfinance"),
    ("FastAPI (téléphone)", "fastapi"),
]

LANGUAGES = {
    ".py": "Python",
    ".ipynb": "Notebook",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".ini": "INI",
    ".cfg": "INI",
    ".txt": "Texte",
    ".sql": "SQL",
    ".sh": "Shell",
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
}

TREE_MAX_DEPTH = 3
TREE_MAX_CHILDREN = 15
COMMITS_SHOWN = 10


# --------------------------------------------------------------------------
# Accès git
# --------------------------------------------------------------------------

def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout.strip()


def tracked_files() -> list[str]:
    """Fichiers suivis par git (le README reflète le dépôt, pas le poste local)."""
    output = git("ls-files")
    return sorted(line for line in output.splitlines() if line)


def format_date(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    try:
        from zoneinfo import ZoneInfo

        moment = moment.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:  # base de fuseaux horaires absente
        pass
    return moment.strftime("%d/%m/%Y %H:%M")


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

def section_meta() -> str:
    # Les commits du bot sont ignorés : le README décrit le dernier changement réel.
    commits = [
        line.split("|", 2)
        for line in git("log", "--format=%h|%cI|%s").splitlines()
        if BOT_TAG not in line
    ]
    if not commits:
        return "_Aucun commit pour l'instant._"
    short_hash, date, _ = commits[0]
    total = len(commits)
    return (
        f"> 🔄 **Dernière mise à jour :** {format_date(date)} (heure de Paris) · "
        f"commit `{short_hash}` · {total} commit{'s' if total > 1 else ''} au total"
    )


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "—"
    filled = round(width * done / total)
    percent = round(100 * done / total)
    return f"`{'█' * filled}{'░' * (width - filled)}` {percent} %"


def section_progress() -> str:
    if not ROADMAP.exists():
        return "_Fichier `docs/ROADMAP.md` introuvable._"

    sections: list[list] = []  # [titre, cochés, total]
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sections.append([line[3:].strip(), 0, 0])
            continue
        match = re.match(r"\s*[-*] \[([ xX])\]", line)
        if match and sections:
            sections[-1][2] += 1
            if match.group(1) in "xX":
                sections[-1][1] += 1

    sections = [s for s in sections if s[2]]
    if not sections:
        return "_Aucune tâche trouvée dans `docs/ROADMAP.md`._"

    rows = ["| Étape | Avancement | Fait |", "|---|---|---|"]
    for title, done, total in sections:
        rows.append(f"| {title} | {progress_bar(done, total)} | {done}/{total} |")
    done = sum(s[1] for s in sections)
    total = sum(s[2] for s in sections)
    rows.append(f"| **Total** | {progress_bar(done, total)} | **{done}/{total}** |")
    return "\n".join(rows)


def section_architecture(files: list[str]) -> str:
    # Accepte les deux dispositions : /<dossier> ou /app/<dossier>. Les
    # sous-dossiers de app/ ayant leur propre ligne ne sont pas comptés dans app/.
    nested = tuple(f"app/{name}/" for name, _ in ARCHITECTURE if name != "app")
    rows = ["| Dossier | Rôle | État | Fichiers Python |", "|---|---|---|---|"]
    for name, role in ARCHITECTURE:
        prefixes = [f"{name}/"] if name == "app" else [f"{name}/", f"app/{name}/"]
        found = [prefix for prefix in prefixes if any(f.startswith(prefix) for f in files)]
        if found:
            count = sum(
                1
                for f in files
                if f.endswith(".py")
                and any(f.startswith(p) for p in found)
                and not (name == "app" and f.startswith(nested))
            )
            location = ", ".join(f"`{p}`" for p in found)
            rows.append(f"| {location} | {role} | ✅ Présent | {count} |")
        else:
            rows.append(f"| `{name}/` | {role} | ⬜ À créer | — |")
    return "\n".join(rows)


def build_tree(files: list[str]) -> dict:
    tree: dict = {}
    for path in files:
        node = tree
        for part in path.split("/"):
            node = node.setdefault(part, {})
    return tree


def count_files(node: dict) -> int:
    return sum(count_files(child) if child else 1 for child in node.values())


def render_tree(node: dict, prefix: str = "", depth: int = 1) -> list[str]:
    # Dossiers d'abord, puis fichiers, chacun par ordre alphabétique.
    entries = sorted(node.items(), key=lambda item: (not item[1], item[0].lower()))
    hidden = max(0, len(entries) - TREE_MAX_CHILDREN)
    entries = entries[:TREE_MAX_CHILDREN]
    lines: list[str] = []
    for index, (name, child) in enumerate(entries):
        last = index == len(entries) - 1 and not hidden
        branch = "└── " if last else "├── "
        if child:
            if depth >= TREE_MAX_DEPTH:
                lines.append(f"{prefix}{branch}{name}/  ({count_files(child)} fichiers)")
            else:
                lines.append(f"{prefix}{branch}{name}/")
                lines.extend(render_tree(child, prefix + ("    " if last else "│   "), depth + 1))
        else:
            lines.append(f"{prefix}{branch}{name}")
    if hidden:
        lines.append(f"{prefix}└── … (+{hidden} éléments)")
    return lines


def section_structure(files: list[str]) -> str:
    if not files:
        return "_Aucun fichier suivi par git._"
    lines = [f"{ROOT.name}/", *render_tree(build_tree(files))]
    return "```text\n" + "\n".join(lines) + "\n```"


AUTO_SECTION = re.compile(r"(<!-- AUTO:(\w+):START -->).*?(<!-- AUTO:\2:END -->)", re.DOTALL)


def read_text(path: str) -> str | None:
    try:
        content = (ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if path == "README.md":
        # Sans les sections générées, sinon les statistiques dépendraient
        # d'elles-mêmes et le README ne serait jamais stable.
        content = AUTO_SECTION.sub(r"\1\3", content)
    return content


def declared_dependencies(files: list[str]) -> set[str]:
    names: set[str] = set()
    for path in files:
        base = path.rsplit("/", 1)[-1]
        content = read_text(path)
        if content is None:
            continue
        if base.startswith("requirements") and base.endswith(".txt"):
            lines = content.splitlines()
        elif base == "pyproject.toml":
            # Lignes du type "pandas>=2.2", entre guillemets, dans les listes de dépendances.
            lines = re.findall(r"""^\s*["']([A-Za-z0-9_.\-\[\]]+[^"']*)["']\s*,?\s*$""", content, re.M)
        else:
            continue
        for line in lines:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = re.match(r"[A-Za-z0-9_.\-]+", line)
            if match:
                names.add(match.group(0).lower().replace("_", "-"))
    return names


def section_stats(files: list[str]) -> str:
    by_language: Counter = Counter()
    lines_by_language: Counter = Counter()
    tests = 0
    for path in files:
        language = LANGUAGES.get(Path(path).suffix.lower(), "Autres")
        by_language[language] += 1
        content = read_text(path)
        if content is None:
            continue
        lines_by_language[language] += sum(1 for line in content.splitlines() if line.strip())
        name = path.rsplit("/", 1)[-1]
        if path.endswith(".py") and (path.startswith("tests/") or "/tests/" in path or name.startswith("test_")):
            tests += len(re.findall(r"^\s*(?:async\s+)?def test_", content, re.M))

    rows = ["| Langage | Fichiers | Lignes (hors vides) |", "|---|---|---|"]
    for language, count in sorted(by_language.items(), key=lambda item: (-item[1], item[0])):
        rows.append(f"| {language} | {count} | {lines_by_language[language]} |")
    rows.append(f"| **Total** | **{len(files)}** | **{sum(lines_by_language.values())}** |")

    deps = declared_dependencies(files)
    stack = ["| Brique | Paquet | Déclaré |", "|---|---|---|"]
    for label, package in STACK:
        stack.append(f"| {label} | `{package}` | {'✅' if package in deps else '⬜'} |")

    return "\n".join(
        [
            *rows,
            "",
            f"**Tests automatisés détectés :** {tests}",
            "",
            "**Stack cible** (dépendances lues dans `requirements*.txt` / `pyproject.toml`) :",
            "",
            *stack,
        ]
    )


def section_commits() -> str:
    log = git("log", f"-{COMMITS_SHOWN * 3}", "--format=%h|%cI|%an|%s")
    rows = []
    for line in log.splitlines():
        short_hash, date, author, subject = line.split("|", 3)
        if BOT_TAG in subject:
            continue
        subject = subject.replace("|", "\\|")
        rows.append(f"| `{short_hash}` | {format_date(date)[:10]} | {author} | {subject} |")
        if len(rows) == COMMITS_SHOWN:
            break
    if not rows:
        return "_Aucun commit pour l'instant._"
    return "\n".join(["| Commit | Date | Auteur | Message |", "|---|---|---|---|", *rows])


# --------------------------------------------------------------------------
# Assemblage
# --------------------------------------------------------------------------

def replace_section(text: str, name: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!-- AUTO:{name}:START -->)(.*?)(<!-- AUTO:{name}:END -->)", re.DOTALL
    )
    if not pattern.search(text):
        print(f"⚠️  Marqueurs AUTO:{name} absents du README, section ignorée.", file=sys.stderr)
        return text
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def render(text: str) -> str:
    files = tracked_files()
    sections = {
        "META": section_meta(),
        "PROGRESS": section_progress(),
        "ARCHITECTURE": section_architecture(files),
        "STRUCTURE": section_structure(files),
        "STATS": section_stats(files),
        "COMMITS": section_commits(),
    }
    for name, content in sections.items():
        text = replace_section(text, name, content)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="échoue si le README n'est pas à jour"
    )
    args = parser.parse_args()

    current = README.read_text(encoding="utf-8")
    updated = render(current)

    if args.check:
        if updated != current:
            print("README.md n'est pas à jour : lancez `python scripts/update_readme.py`.")
            return 1
        print("README.md est à jour.")
        return 0

    if updated != current:
        README.write_text(updated, encoding="utf-8")
        print("README.md mis à jour.")
    else:
        print("README.md déjà à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
