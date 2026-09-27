#!/bin/bash

# Requires python3 and wget. Only direct wget commands in shell-form RUNs are
# mirrored: literal ARG defaults, ${NAME}, HTTP(S), and optional -O filename.
# Container output paths are flattened into sources/. No Dockerfile shell runs.
exec python3 - "$@" <<'PY'
import argparse
import pathlib
import re
import shlex
import subprocess
import sys
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description="Download Dockerfile wget sources safely")
parser.add_argument("--dry-run", action="store_true", help="print commands without writing files")
parser.add_argument("dockerfile", nargs="?", default="Dockerfile")
options = parser.parse_args()
variables = {}
downloads = []


def expand(value):
    def replace(match):
        name = match.group(1)
        if name not in variables:
            raise ValueError(f"undefined ARG: {name}")
        return variables[name]

    value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, value)
    if "$" in value or "`" in value:
        raise ValueError(f"unsupported shell expansion: {value}")
    return value


try:
    text = pathlib.Path(options.dockerfile).read_text()
    # Dockerfile continuation lines may contain whole-line comments.
    text = re.sub(r"(?m)^\s*#.*$", "", text)
    text = re.sub(r"\\\n(?:\s*\n)*", " ", text)
    for line in text.splitlines():
        instruction, _, body = line.strip().partition(" ")
        if instruction.upper() == "ARG":
            words = shlex.split(body, comments=True)
            if len(words) != 1 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
                raise ValueError(f"only literal ARG assignments are supported: {line}")
            name, value = words[0].split("=", 1)
            if "$" in value or "`" in value:
                raise ValueError(f"ARG {name} must have a literal default")
            variables[name] = value
        elif instruction.upper() == "RUN":
            lexer = shlex.shlex(body, posix=True, punctuation_chars=";&|<>()")
            lexer.whitespace_split = True
            command = []
            for token in [*lexer, "&&"]:
                if token and all(char in ";&|<>()" for char in token):
                    if command and command[0] == "wget":
                        if token not in ("&&", ";"):
                            raise ValueError("wget pipes, substitutions and redirections are unsupported")
                        args = [expand(word) for word in command[1:]]
                        output = None
                        if args[:1] == ["-O"] and len(args) >= 2:
                            output = pathlib.PurePosixPath(args[1]).name
                            args = args[2:]
                        if len(args) != 1 or urlsplit(args[0]).scheme not in ("http", "https"):
                            raise ValueError(f"expected wget [-O filename] HTTP(S)-URL: {command}")
                        if not urlsplit(args[0]).netloc:
                            raise ValueError(f"URL has no host: {args[0]}")
                        if output is not None and (not output or output in (".", "..", "-")):
                            raise ValueError("wget -O requires a regular filename")
                        downloads.append(["wget", *(["-O", output] if output else []), "--", args[0]])
                    command = []
                else:
                    command.append(token)
    if not downloads:
        raise ValueError("no supported wget commands found")
    if not options.dry_run:
        pathlib.Path("sources").mkdir(exist_ok=True)
    for command in downloads:
        if options.dry_run:
            print(shlex.join(command))
        else:
            subprocess.run(command, cwd="sources", check=True)
except (OSError, ValueError, subprocess.CalledProcessError) as error:
    print(f"getSources.sh: {error}", file=sys.stderr)
    sys.exit(1)
PY
