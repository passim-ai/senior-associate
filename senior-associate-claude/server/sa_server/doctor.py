"""The setup check: what a build needs on this Mac, each with a plain line and, when it's missing, the fix and the
request that has Claude do it."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any

from .common import MATTERS_FOLDER_ASK, MATTERS_FOLDER_HOWTO, plugin_version, show_path
from .context import Context
from .folders import exemplars_list
from .profile import PROFILE_NEEDED, load_profile

# Where installers put the tools besides PATH: Homebrew (Apple silicon, then Intel) and MacPorts. A build looks in
# PATH and these, so a check that passes means a build finds the tool.
EXTRA_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")


def find_tool(names: tuple[str, ...], extra: tuple[str, ...] = ()) -> tuple[str, bool]:
    """Where a tool is, and whether Claude's own PATH finds it there. ("", False) when it isn't installed."""
    for n in names:
        found = shutil.which(n)
        if found:
            return found, True
    candidates = [str(Path(d) / n) for d in EXTRA_BIN_DIRS for n in names] + list(extra)
    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p), False
    return "", False


def _tool_check(id_: str, label: str, names: tuple[str, ...], *, required: bool, does: str, missing: str,
                extra: tuple[str, ...] = ()) -> dict[str, Any]:
    path, on_path = find_tool(names, extra)
    check: dict[str, Any] = {"id": id_, "label": label, "ok": bool(path), "required": required,
                             "level": "required" if required else "optional"}
    if path:
        check["detail"] = does if on_path else f"{does} If a build can't find it, quit Claude with ⌘Q and reopen it."
        return check
    check["detail"] = missing
    if platform.system() != "Darwin":
        check["fix"] = f"Install {label} for your system, then restart Claude."
        return check
    check["fix"] = f"Claude can install {label} for you."
    check["ask"] = f"Install {label} for Immigration Packet Builder."
    return check


def _matters_folder_check(ctx: Context) -> dict[str, Any]:
    root = ctx.matters_root
    home = Path.home().resolve()
    check: dict[str, Any] = {"id": "matters_folder", "label": "Matters folder", "required": True, "level": "required"}
    too_broad = {home, Path("/").resolve(), (home / "Documents").resolve(), (home / "Desktop").resolve(),
                 (home / "Downloads").resolve(), (home / "Library").resolve()}
    if root in too_broad:
        check.update(ok=False, detail=f"{show_path(root)} holds more than client matters, so every folder in it would show up as a matter.",
                     fix=MATTERS_FOLDER_HOWTO, ask=MATTERS_FOLDER_ASK)
        return check
    if root.exists() and not root.is_dir():
        ok = False
    elif root.is_dir():
        ok = os.access(root, os.W_OK | os.X_OK)
    else:
        parent = next((p for p in root.parents if p.exists()), None)
        ok = bool(parent and parent.is_dir() and os.access(parent, os.W_OK | os.X_OK))
    if ok:
        made = "" if root.is_dir() else " It's created when you start your first matter."
        check.update(ok=True, detail=f"Immigration Packet Builder keeps one folder per client matter in {show_path(root)}.{made}")
    else:
        check.update(ok=False, detail=f"Immigration Packet Builder can't save in {show_path(root)}.",
                     fix=MATTERS_FOLDER_HOWTO, ask=MATTERS_FOLDER_ASK)
    return check


def _profile_check(ctx: Context) -> dict[str, Any]:
    profile = load_profile(ctx)
    missing = [label for key, label in PROFILE_NEEDED.items() if not profile.get(key)]
    check: dict[str, Any] = {"id": "profile", "label": "Your details", "required": False, "level": "recommended",
                             "ok": not missing}
    if missing:
        listed = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " and " + missing[-1]
        check["detail"] = (
            "Your name, firm and bar number for the G-28 and the letter." if len(missing) == len(PROFILE_NEEDED)
            else f"Your name, firm and bar number for the G-28 and the letter. Still missing: {listed}."
        )
        check["fix"] = "Add your details. It takes about 2 minutes, once."
    else:
        check["detail"] = "Your name, firm and bar number go on the G-28 and the letter."
    return check


def _model_letters_check(ctx: Context) -> dict[str, Any]:
    letters = exemplars_list(ctx)
    check: dict[str, Any] = {"id": "model_letters", "label": "Model letters", "required": False, "level": "optional",
                             "ok": bool(letters)}
    if letters:
        check["detail"] = f"{len(letters)} letter{'s' if len(letters) != 1 else ''} in your firm's style for Claude to follow."
    else:
        check["detail"] = "No model letters yet, so Claude uses its standard letter format."
        check["fix"] = "To follow your firm's style, Claude can use a folder of your cover letters (.docx)."
        check["ask"] = "Use my firm's model letters with Immigration Packet Builder."
    return check


def doctor(ctx: Context) -> dict[str, Any]:
    """What a build needs on this Mac, each with a plain line and, when it's missing, the fix and the request that has
    Claude do it."""
    tools = [
        _tool_check("ghostscript", "Ghostscript", ("gs",), required=True, does="Prints the filled USCIS forms.",
                    missing="Prints the filled USCIS forms. A build can't finish the forms without it."),
        _tool_check("libreoffice", "LibreOffice", ("soffice", "libreoffice"), required=False,
                    does="Makes the cover letter's PDF match Word exactly.",
                    missing="Optional. Makes the cover letter's PDF match Word exactly; without it the PDF is made another way.",
                    extra=("/Applications/LibreOffice.app/Contents/MacOS/soffice", "~/Applications/LibreOffice.app/Contents/MacOS/soffice")),
        _tool_check("poppler", "Poppler", ("pdftotext",), required=False, does="Helps Claude read the text in PDFs.",
                    missing="Optional. Helps Claude read the text in PDFs more quickly."),
    ]
    checks: list[dict[str, Any]] = [{"id": "uv", "label": "uv", "ok": True, "required": True, "level": "required",
                                     "detail": "Runs Immigration Packet Builder's tools."}]
    checks.append(tools[0])
    checks.append(_matters_folder_check(ctx))
    checks.append(_profile_check(ctx))
    checks.extend(tools[1:])
    checks.append(_model_letters_check(ctx))
    return {"checks": checks, "version": plugin_version(ctx), "ok": all(c["ok"] for c in checks if c["required"])}

