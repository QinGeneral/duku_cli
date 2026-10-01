#!/usr/bin/env python3
"""Check publishable files without printing credential values (stdlib only)."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {"抓包", "读", "读库v2", "听", "cache", "metadata", ".duku"}
PRIVATE_SUFFIXES = {
    ".epub", ".mp3", ".mp4", ".m4a", ".m3u8", ".ts", ".apk",
    ".har", ".pcap", ".pcapng", ".pem", ".key", ".p12", ".sqlite",
}
PATTERNS = {
    "personal home path": re.compile(r"/(?:Users|home)/[\w.-]+/|[A-Za-z]:\\Users\\[\w.-]+\\"),
    "email address": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "phone-like value": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "embedded credential": re.compile(
        r'''(?i)(?:satoken|token|password|secret|api[_-]?key|security[_-]?token|authorization|cookie)'''
        r'''\s*["']?\s*[:=]\s*["']([A-Za-z0-9+/_=.\-]{20,})["']'''
    ),
    "URL credential": re.compile(r"(?i)[?&](?:token|satoken|api[_-]?key|signature|securitytoken)=[A-Za-z0-9+/_=.%-]{20,}"),
    "bearer credential": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider credential": re.compile(r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{24,})\b"),
}


def public_files():
    # Never scan a parent repository when this export has no .git yet.
    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, check=True, capture_output=True,
        )
        return sorted({ROOT / name.decode("utf-8") for name in result.stdout.split(b"\0") if name})
    local_only = {".git", ".venv", "venv", "__pycache__", "build", "dist", ".pytest_cache"}
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file()
        and not any(part in local_only or part.endswith(".egg-info") for part in p.relative_to(ROOT).parts)
    )


def check(path):
    relative = path.relative_to(ROOT)
    parts = relative.parts
    private = (
        any(part in PRIVATE_DIRS or "《读库》总目" in part or "chrome-profile" in part for part in parts)
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or path.name in {"config.json", "header.json", ".env", ".DS_Store"}
        or (path.name.startswith(".env.") and path.name != ".env.example")
        or (path.name.startswith("cookies") and path.suffix == ".json")
        or ".git" in parts
    )
    if private:
        yield f"{relative}: private/generated file"
    if path.is_symlink():
        yield f"{relative}: symbolic link requires manual review"
        return
    if not path.exists():
        return
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return  # Binary privacy is handled by the filename rules and manual review.
    for number, line in enumerate(content.splitlines(), start=1):
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                # This conventional sample number is only used by mocked offline tests.
                if label == "phone-like value" and parts[0] == "tests" and match.group() == "138" + "00138000":
                    continue
                yield f"{relative}:{number}: {label}"


def main():
    paths = public_files()
    findings = [finding for path in paths for finding in check(path)]
    if findings:
        print("Public file check failed (values omitted):")
        print("\n".join(findings))
        return 1
    print(f"Public file check passed: {len(paths)} files; no matches in configured rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
