#!/usr/bin/env python3
"""A small stdlib-only Mac setup manager. No writes are implicit in restore."""

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FILES = (
    ".zshrc",
    ".zprofile",
    ".zshenv",
    ".zlogin",
    ".zlogout",
    ".p10k.zsh",
    ".hushlogin",
    ".zshrc.local",
    ".zprofile.local",
    ".tmux.conf",
    ".iterm2_shell_integration.zsh",
    ".nvmrc",
    ".nvm/alias/default",
    ".nvm/default-packages",
    ".config/bpytop/bpytop.conf",
    ".config/btop/btop.conf",
    ".config/htop/htoprc",
    ".config/atuin/config.toml",
    ".config/ranger/rc.conf",
    ".config/ranger/rifle.conf",
    ".config/ranger/commands.py",
    ".config/ranger/scope.sh",
    "Library/Preferences/com.googlecode.iterm2.plist",
    ".config/iterm2/com.googlecode.iterm2.plist",
    "Library/Application Support/Code/User/settings.json",
    "Library/Application Support/Code/User/keybindings.json",
    ".config/zed/settings.json",
    ".config/zed/keymap.json",
)
PUBLIC_CONFIGS = {
    "zprofile": ".zprofile",
    "zshrc": ".zshrc",
    "p10k.zsh": ".p10k.zsh",
    "bpytop/bpytop.conf": ".config/bpytop/bpytop.conf",
    "btop/btop.conf": ".config/btop/btop.conf",
    "htop/htoprc": ".config/htop/htoprc",
    "atuin/config.toml": ".config/atuin/config.toml",
}
DYNAMIC_PROFILE = "Library/Application Support/iTerm2/DynamicProfiles/rahul-macenv.json"
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9@+_.-]*(?:/[A-Za-z0-9][A-Za-z0-9@+_.-]*){0,2}\Z")
BREW_LINE = re.compile(r'(tap|brew|cask) "([A-Za-z0-9@+_./-]+)"\Z')
SENSITIVE = re.compile(
    r"/Users/|(?m:^[^#\n]*/home/)|-----BEGIN [A-Z ]*PRIVATE KEY|\b(?:ghp_|github_pat_|sk-[A-Za-z0-9]|AKIA[A-Z0-9])|Bearer\s+\S+|"
    r"(?im:^[^#\n]*(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[^\s#]+)"
)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def execute(argv):
    streamed = (
        argv[1:3] == ["bundle", "install"]
        or argv[0] == "/bin/bash"
        or "--install-extension" in argv
        or (Path(argv[0]).name in ("npm", "pipx") and "install" in argv)
    )
    result = subprocess.run(
        argv,
        check=False,
        capture_output=not streamed,
        text=True,
        env={**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"},
    )
    if result.returncode:
        # Package manager diagnostics may contain private paths or credentials.
        raise RuntimeError(
            f"{Path(argv[0]).name} {argv[1] if len(argv) > 1 else ''} failed (exit {result.returncode}); inspect locally, not in a public issue"
        )
    return result.stdout or ""


def find_brew():
    preferred = "/opt/homebrew/bin/brew" if platform.machine() == "arm64" else "/usr/local/bin/brew"
    return preferred if Path(preferred).is_file() else shutil.which("brew")


def valid_relative(relative):
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in ("..", ".") for part in path.parts)
        or "\\" in relative
    ):
        raise ValueError("Unsafe relative path")
    return path


def target_path(home, relative):
    relative = valid_relative(relative)
    target = home.joinpath(*relative.parts)
    current = home
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing symlink destination: {relative}")
    if target.exists() and not target.is_file():
        raise ValueError(f"Expected a file, not a directory: {relative}")
    return target


def directory_path(home, relative):
    relative = valid_relative(relative)
    current = home
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError(f"Unsafe directory destination: {relative}")
    return current


def allowed_backup_path(relative):
    valid_relative(relative)
    if relative in PRIVATE_FILES or relative == DYNAMIC_PROFILE:
        return True
    return any(
        relative.startswith(prefix)
        for prefix in (
            ".config/nnn/plugins/",
            ".config/nnn/bookmarks/",
            ".oh-my-zsh/custom/",
            "Library/Fonts/",
            "Library/Application Support/iTerm2/DynamicProfiles/",
            "Library/Application Support/Code/User/snippets/",
        )
    ) and not any(part.startswith(".") for part in PurePosixPath(relative).parts[1:])


def safe_public(data):
    text = data.decode("utf-8")
    if SENSITIVE.search(text):
        raise ValueError("Possible private value in public export; review locally instead")
    return data


def parse_brewfile(text):
    entries = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = BREW_LINE.fullmatch(line)
        if not match or not TOKEN.fullmatch(match[2]) or ".." in match[2]:
            raise ValueError(
                "Brewfile must contain only plain tap/brew/cask entries; executable Ruby and service directives are forbidden"
            )
        entries.add((match[1], match[2]))
    return sorted(entries, key=lambda entry: (("tap", "brew", "cask").index(entry[0]), entry[1]))


def brewfile(entries):
    return "# Generated package names only; no credentials or service autostart.\n" + "".join(
        f'{kind} "{name}"\n' for kind, name in entries
    )


def public_iterm(preferences):
    profiles = preferences.get("New Bookmarks", [])
    if not profiles:
        raise ValueError("No iTerm2 profiles found")
    selected = next(
        (p for p in profiles if p.get("Guid") == preferences.get("Default Bookmark Guid")),
        profiles[0],
    )
    keys = {
        "Normal Font",
        "Non Ascii Font",
        "Use Non-ASCII Font",
        "ASCII Anti Aliased",
        "Non-ASCII Anti Aliased",
        "ASCII Ligatures",
        "Non-ASCII Ligatures",
        "Use Bold Font",
        "Use Italic Font",
        "Use Bright Bold",
        "Draw Powerline Glyphs",
        "Horizontal Spacing",
        "Vertical Spacing",
        "Columns",
        "Rows",
        "Transparency",
        "Blur",
        "Blur Radius",
        "Cursor Type",
        "Blinking Cursor",
        "Scrollback Lines",
        "Unlimited Scrollback",
        "Use Separate Colors for Light and Dark Mode",
        "Silence Bell",
        "Visual Bell",
    }
    profile = {
        key: value
        for key, value in selected.items()
        if key in keys
        or re.fullmatch(
            r"(?:Ansi \d+|Background|Foreground|Bold|Cursor|Cursor Text|Selection|Selected Text|Link) Color(?: \((?:Dark|Light)\))?",
            key,
        )
    }
    # No original names, commands, working dirs, keybinding text, AI settings, or host rules.
    profile.update(
        {
            "Name": "Rahul · Main",
            "Guid": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "https://github.com/RahulSinghParmar/zsh-terminal/main-profile",
                )
            ),
            "Custom Command": "No",
            "Command": "",
            "Custom Directory": "No",
            "Working Directory": "",
        }
    )
    return {"Profiles": [profile]}


class Manager:
    def __init__(self, root=ROOT, home=None, run=execute, brew=None):
        self.root = Path(root).resolve()
        self.home = Path(home or Path.home()).resolve()
        self.run = run
        self.brew = brew or find_brew()

    def inventory(self):
        if not self.brew:
            raise RuntimeError("Homebrew is not installed or not on PATH")
        raw = json.loads(self.run([self.brew, "info", "--json=v2", "--installed"]))
        formulae = [
            {
                "name": item["full_name"],
                "versions": [v["version"] for v in item.get("installed", [])],
                "requested": any(
                    v.get("installed_on_request", False) for v in item.get("installed", [])
                ),
            }
            for item in raw.get("formulae", [])
        ]
        casks = [
            {"name": item.get("full_token", item["token"]), "version": item.get("installed")}
            for item in raw.get("casks", [])
        ]
        taps = self.run([self.brew, "tap"]).splitlines()
        for name in [f["name"] for f in formulae] + [c["name"] for c in casks] + taps:
            if not TOKEN.fullmatch(name) or ".." in name:
                raise ValueError("Unsupported package identifier; review locally")
        warnings = []
        try:
            services = [
                {"name": item["name"], "status": item["status"]}
                for item in json.loads(self.run([self.brew, "services", "list", "--json"]))
            ]
        except (RuntimeError, ValueError, KeyError):
            services = []
            warnings.append(
                "Homebrew service inventory unavailable; no services will be automatically started"
            )
        extras = {}
        for name, command in (
            ("npm", ["npm", "list", "-g", "--depth=0", "--json"]),
            ("pipx", ["pipx", "list", "--json"]),
            ("vscode", ["code", "--list-extensions", "--show-versions"]),
        ):
            if not shutil.which(command[0]):
                continue
            try:
                output = self.run(command)
                if name == "npm":
                    extras[name] = {
                        key: value.get("version")
                        for key, value in json.loads(output).get("dependencies", {}).items()
                    }
                elif name == "pipx":
                    extras[name] = {
                        key: value.get("metadata", {})
                        .get("main_package", {})
                        .get("package_version")
                        for key, value in json.loads(output).get("venvs", {}).items()
                    }
                else:
                    extras[name] = [
                        line
                        for line in output.splitlines()
                        if re.fullmatch(r"[\w-]+\.[\w.-]+@[\w.+-]+", line)
                    ]
            except (RuntimeError, ValueError, AttributeError):
                warnings.append(f"{name} inventory unavailable; restore separately")
        nvm = self.home / ".nvm/versions/node"
        default_alias = self.home / ".nvm/alias/default"
        default_node = (
            default_alias.read_text().strip()
            if default_alias.is_file() and not default_alias.is_symlink()
            else None
        )
        if default_node and not re.fullmatch(
            r"v?\d+(?:\.\d+){0,2}|node|stable|lts/[\w*.-]+", default_node
        ):
            default_node = None
        return {
            "schema": 1,
            "captured_at": utc(),
            "architecture": platform.machine(),
            "macos": platform.mac_ver()[0],
            "formulae": sorted(formulae, key=lambda item: item["name"]),
            "casks": sorted(casks, key=lambda item: item["name"]),
            "taps": sorted(taps),
            "services": services,
            "extras_inventory_only": extras,
            "nvm_versions_inventory_only": sorted(
                p.name
                for p in nvm.glob("v*")
                if p.is_dir() and re.fullmatch(r"v\d+\.\d+\.\d+", p.name)
            ),
            "nvm_default": default_node,
            "warnings": warnings,
        }

    def snapshot(self, settings=False):
        inventory = self.inventory()
        entries = [("tap", name) for name in inventory["taps"]]
        entries += [("brew", item["name"]) for item in inventory["formulae"]]
        entries += [("cask", item["name"]) for item in inventory["casks"]]
        # Full snapshot supplements core with fonts/iTerm that weren't brew-managed.
        outputs = {
            "manifests/Brewfile.full": brewfile(parse_brewfile(brewfile(entries))).encode(),
            "manifests/inventory.json": (
                json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
            ).encode(),
        }
        if settings:
            for source, relative in PUBLIC_CONFIGS.items():
                if source in ("zprofile", "zshrc", "atuin/config.toml"):
                    continue  # Managed templates, never raw account configuration.
                target = target_path(self.home, relative)
                if target.is_file():
                    # Public exports normalize whitespace-only lines; the private
                    # backup retains the original bytes for exact recovery.
                    outputs[f"dotfiles/{source}"] = re.sub(
                        rb"(?m)^[ \t]+$", b"", target.read_bytes()
                    )
            plist = target_path(self.home, "Library/Preferences/com.googlecode.iterm2.plist")
            if plist.is_file():
                outputs["iterm2/Profiles.json"] = (
                    json.dumps(public_iterm(plistlib.loads(plist.read_bytes())), indent=2) + "\n"
                ).encode()
        for relative, data in outputs.items():
            try:
                safe_public(data)
            except ValueError:
                raise ValueError(
                    f"Public export blocked for {relative}; inspect it privately"
                ) from None
            target_path(self.root, relative)
        for relative, data in outputs.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print(
            f"Updated {len(outputs)} public-safe snapshot files. Review git diff before publishing."
        )

    def private_paths(self):
        found = {
            relative for relative in PRIVATE_FILES if target_path(self.home, relative).is_file()
        }
        patterns = (
            "Library/Fonts/*.ttf",
            "Library/Fonts/*.otf",
            ".config/nnn/plugins/*",
            ".config/nnn/bookmarks/*",
            ".oh-my-zsh/custom/*.zsh",
            "Library/Application Support/iTerm2/DynamicProfiles/*",
            "Library/Application Support/Code/User/snippets/*",
        )
        for pattern in patterns:
            for path in self.home.glob(pattern):
                if path.is_file() and not path.is_symlink() and not path.name.startswith("."):
                    relative = path.relative_to(self.home).as_posix()
                    target_path(self.home, relative)
                    found.add(relative)
        return sorted(found)

    def backup(self, paths=None, parent=None, kind="capture", written=None):
        parent = Path(parent or self.root / "local/backups")
        base = next((base for base in (self.root, self.home) if base in parent.parents), None)
        if base is None:
            raise ValueError("Backup directory must be beneath this checkout or your home")
        directory_path(base, parent.relative_to(base).as_posix())
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = Path(
            tempfile.mkdtemp(prefix=dt.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=parent)
        )
        os.chmod(directory, 0o700)
        entries = []
        for relative in paths if paths is not None else self.private_paths():
            if not allowed_backup_path(relative):
                raise ValueError("Path is outside the backup allowlist")
            source = target_path(self.home, relative)
            item = {
                "path": relative,
                "present": source.is_file(),
                "written_sha256": (written or {}).get(relative),
            }
            if source.is_file():
                data = source.read_bytes()
                output = directory / "files" / relative
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                output.write_bytes(data)
                os.chmod(output, 0o600)
                item.update({"sha256": digest(data), "mode": source.stat().st_mode & 0o777})
            entries.append(item)
        write_json(
            directory / "manifest.json",
            {"schema": 1, "kind": kind, "created_at": utc(), "files": entries},
        )
        os.chmod(directory / "manifest.json", 0o600)
        print(
            f"Private backup: {directory} (unencrypted; keep off Git and store an encrypted off-machine copy)"
        )
        return directory

    def config_files(self):
        files = {}
        for source, relative in PUBLIC_CONFIGS.items():
            path = target_path(self.root, f"dotfiles/{source}")
            if path.is_file():
                files[relative] = safe_public(path.read_bytes())
        files[".hushlogin"] = b""
        profile = target_path(self.root, "iterm2/Profiles.json")
        if profile.is_file():
            files[DYNAMIC_PROFILE] = safe_public(profile.read_bytes())
        for relative in files:
            target_path(self.home, relative)
        return files

    def install_files(self, files, modes=None):
        changed = {
            relative: data
            for relative, data in files.items()
            if not target_path(self.home, relative).is_file()
            or target_path(self.home, relative).read_bytes() != data
        }
        if not changed:
            print("Configuration already matches; nothing replaced.")
            return None
        backup = self.backup(
            changed,
            parent=self.home / ".local/state/macenv/backups",
            kind="transaction",
            written={relative: digest(data) for relative, data in changed.items()},
        )
        for relative, data in changed.items():
            destination = target_path(self.home, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Replacing a same-directory temporary file avoids half-written dotfiles.
            fd, temporary = tempfile.mkstemp(prefix=".macenv-", dir=destination.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                os.chmod(temporary, 0o700 if (modes or {}).get(relative, 0) & 0o111 else 0o600)
                os.replace(temporary, destination)
            finally:
                if Path(temporary).exists():
                    Path(temporary).unlink()
        print(f"Installed {len(changed)} configuration files. Undo backup: {backup}")
        return backup

    def sources(self):
        items = json.loads((self.root / "manifests/shell-sources.json").read_text())
        known = {
            "https://github.com/ohmyzsh/ohmyzsh.git": (".oh-my-zsh", "oh-my-zsh.sh"),
            "https://github.com/romkatv/powerlevel10k.git": (
                ".oh-my-zsh/custom/themes/powerlevel10k",
                "powerlevel10k.zsh-theme",
            ),
            "https://github.com/zsh-users/zsh-autosuggestions.git": (
                ".oh-my-zsh/custom/plugins/zsh-autosuggestions",
                "zsh-autosuggestions.plugin.zsh",
            ),
            "https://github.com/zsh-users/zsh-syntax-highlighting.git": (
                ".oh-my-zsh/custom/plugins/zsh-syntax-highlighting",
                "zsh-syntax-highlighting.plugin.zsh",
            ),
        }
        for item in items:
            if (
                item["url"] not in known
                or not re.fullmatch(r"[a-f0-9]{40}", item["revision"])
                or (item["target"], item["entry"]) != known[item["url"]]
            ):
                raise ValueError("Invalid shell source lock")
            valid_relative(item["target"])
            valid_relative(item["entry"])
            directory_path(self.home, item["target"])
        return items

    def ensure_sources(self):
        for item in self.sources():
            target = directory_path(self.home, item["target"])
            # Existing repositories/customizations are never reset or auto-updated.
            if target.exists():
                if not (target / item["entry"]).is_file() or target.is_symlink():
                    raise ValueError(
                        f"Existing shell directory needs manual review: {item['target']}"
                    )
                print(f"Keeping existing {item['name']}; use doctor to inspect revision drift.")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".macenv-source-", dir=target.parent))
            try:
                self.run(["git", "init", "--quiet", str(temporary)])
                self.run(["git", "-C", str(temporary), "remote", "add", "origin", item["url"]])
                self.run(
                    [
                        "git",
                        "-C",
                        str(temporary),
                        "fetch",
                        "--quiet",
                        "--depth=1",
                        "origin",
                        item["revision"],
                    ]
                )
                self.run(
                    ["git", "-C", str(temporary), "checkout", "--quiet", "--detach", "FETCH_HEAD"]
                )
                if not (temporary / item["entry"]).is_file():
                    raise ValueError("Fetched source is incomplete")
                temporary.rename(target)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)  # Only our newly-created staging directory.

    def extras_plan(self):
        data = json.loads((self.root / "manifests/inventory.json").read_text())
        extras = data.get("extras_inventory_only", {})
        commands = []
        for name, version in extras.get("npm", {}).items():
            if name in ("npm", "corepack"):
                continue  # Do not replace the package manager bundled with Node.
            if not re.fullmatch(
                r"(?:@[A-Za-z0-9][\w.-]*/)?[A-Za-z0-9][\w.-]*", name
            ) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", version or ""):
                raise ValueError("Invalid npm package in inventory")
            commands.append(["npm", "install", "--global", f"{name}@{version}"])
        for name, version in extras.get("pipx", {}).items():
            if not re.fullmatch(r"[A-Za-z0-9][\w.-]*", name) or not re.fullmatch(
                r"[A-Za-z0-9][\w.+-]*", version or ""
            ):
                raise ValueError("Invalid pipx package in inventory")
            commands.append(["pipx", "install", f"{name}=={version}"])
        for extension in extras.get("vscode", []):
            if not re.fullmatch(
                r"[A-Za-z0-9][\w-]*\.[A-Za-z0-9][\w.-]*@[A-Za-z0-9][\w.+-]*", extension
            ):
                raise ValueError("Invalid VS Code extension in inventory")
            commands.append(["code", "--install-extension", extension])
        versions = data.get("nvm_versions_inventory_only", [])
        if any(not re.fullmatch(r"v\d+\.\d+\.\d+", version) for version in versions):
            raise ValueError("Invalid NVM version")
        alias = data.get("nvm_default")
        if alias and not re.fullmatch(r"v?\d+(?:\.\d+){0,2}|node|stable|lts/[\w*.-]+", alias):
            raise ValueError("Invalid NVM default alias")
        return commands, versions, alias

    def restore_extras(self, plan):
        commands, versions, alias = plan
        for binary in sorted({command[0] for command in commands}):
            if not shutil.which(binary):
                raise RuntimeError(
                    f"{binary} is required for --extras; ensure its CLI is on PATH before retrying"
                )
        if versions or alias:
            prefix = self.run([self.brew, "--prefix"]).strip() if self.brew else ""
            script = next(
                (
                    path
                    for path in (self.home / ".nvm/nvm.sh", Path(prefix) / "opt/nvm/nvm.sh")
                    if path.is_file()
                ),
                None,
            )
            if script is None:
                raise RuntimeError(
                    "NVM initialization script is missing; install nvm before --extras"
                )
            directory_path(self.home, ".nvm").mkdir(parents=True, exist_ok=True)
            for version in versions:
                self.run(
                    [
                        "/bin/bash",
                        "--noprofile",
                        "--norc",
                        "-c",
                        'export NVM_DIR="$1"; . "$2"; nvm install "$3"',
                        "macenv",
                        str(self.home / ".nvm"),
                        str(script),
                        version,
                    ]
                )
            if alias:
                self.run(
                    [
                        "/bin/bash",
                        "--noprofile",
                        "--norc",
                        "-c",
                        'export NVM_DIR="$1"; . "$2"; nvm alias default "$3"',
                        "macenv",
                        str(self.home / ".nvm"),
                        str(script),
                        alias,
                    ]
                )
        for command in commands:
            print(f"Restoring optional package/extension: {command[-1]}", flush=True)
            self.run(command)

    def restore(self, profile="full", apply=False, configs_only=False, extras=False):
        if configs_only and extras:
            raise ValueError("--configs-only and --extras cannot be combined")
        files = self.config_files()
        sources = self.sources()
        extra_plan = self.extras_plan() if extras else None
        entries = parse_brewfile((self.root / "Brewfile").read_text())
        if profile == "full":
            entries = parse_brewfile(
                brewfile(entries) + (self.root / "manifests/Brewfile.full").read_text()
            )
        print(
            f"{'APPLY' if apply else 'PREVIEW'}: {profile} profile; {len(entries)} package/tap entries; {len(files)} managed config files."
        )
        print(
            "Packages install without blanket upgrades/cleanup; no services start. Existing shell source directories are kept."
        )
        for relative, data in files.items():
            target = target_path(self.home, relative)
            print(
                f"  {'keep' if target.is_file() and target.read_bytes() == data else 'install/backup'} {relative}"
            )
        print(
            f"Shell sources: {len(sources)} pinned repositories. iTerm2: adds a dynamic profile, does not change your default."
        )
        if extra_plan:
            print(
                f"Optional extras: {len(extra_plan[0])} package/extension installs; {len(extra_plan[1])} NVM versions; default alias: {extra_plan[2] or 'unchanged'}."
            )
            for warning in json.loads((self.root / "manifests/inventory.json").read_text()).get(
                "warnings", []
            ):
                print(f"Capture warning: {warning}")
        if not apply:
            print(
                "No changes made. Add --apply to install. Full restore can download large apps/SDKs and may need administrator confirmation."
            )
            return
        if platform.system() != "Darwin":
            raise RuntimeError("Applying a restore is supported only on macOS")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise RuntimeError("Do not restore as root/sudo")
        if not configs_only:
            if not self.brew:
                raise RuntimeError("Install Homebrew first or explicitly use --install-homebrew")
            with tempfile.TemporaryDirectory(prefix="macenv-packages-") as directory:
                path = Path(directory) / "Brewfile"
                path.write_text(brewfile(entries))
                self.run([self.brew, "bundle", "install", f"--file={path}", "--no-upgrade"])
            self.ensure_sources()
        if extra_plan:
            self.restore_extras(extra_plan)
        self.install_files(files)
        print(
            "Restore completed. Open iTerm2's Rahul · Main profile; choose it as default manually if wanted."
        )

    def recover(self, backup, apply=False, full_iterm=False):
        backup = Path(backup).resolve()
        manifest = json.loads((backup / "manifest.json").read_text())
        if manifest.get("schema") != 1 or manifest.get("kind") not in ("capture", "transaction"):
            raise ValueError("Unsupported backup manifest")
        files, removals, modes, seen = {}, [], {}, set()
        for item in manifest["files"]:
            relative = item["path"]
            if relative in seen or not isinstance(item.get("present"), bool):
                raise ValueError("Duplicate or malformed backup entry")
            seen.add(relative)
            if not allowed_backup_path(relative):
                raise ValueError("Backup contains a disallowed path")
            if relative.endswith("com.googlecode.iterm2.plist") and not full_iterm:
                continue
            target = target_path(self.home, relative)
            if item["present"]:
                source = target_path(backup / "files", relative)
                data = source.read_bytes()
                if digest(data) != item["sha256"]:
                    raise ValueError("Backup checksum mismatch; no settings changed")
                if (
                    full_iterm
                    and relative.endswith("com.googlecode.iterm2.plist")
                    and not isinstance(plistlib.loads(data), dict)
                ):
                    raise ValueError("Invalid iTerm2 preferences")
                files[relative] = data
                mode = item.get("mode", 0o600)
                if not isinstance(mode, int) or mode < 0 or mode > 0o777:
                    raise ValueError("Invalid captured file permissions")
                modes[relative] = mode
            elif target.is_file():
                if digest(target.read_bytes()) != item.get("written_sha256"):
                    raise ValueError(
                        "A newly-created file was edited after install; refusing to delete it"
                    )
                removals.append(relative)
        print(
            f"{'APPLY' if apply else 'PREVIEW'} recovery: {len(files)} files; {len(removals)} unchanged newly-created files to remove."
        )
        if not apply:
            return
        if platform.system() != "Darwin" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            raise RuntimeError("Recovery requires macOS and your normal user account")
        if full_iterm:
            process = subprocess.run(["pgrep", "-x", "iTerm2"], check=False, capture_output=True)
            if process.returncode == 0:
                raise RuntimeError(
                    "Quit iTerm2 first; recover full preferences from Apple Terminal"
                )
        undo = self.backup(
            list(files) + removals, parent=self.home / ".local/state/macenv/backups", kind="capture"
        )
        self.install_files(files, modes)
        for relative in removals:
            target_path(self.home, relative).unlink()
        standard = "Library/Preferences/com.googlecode.iterm2.plist"
        if full_iterm and standard in files:
            self.run(
                ["/usr/bin/defaults", "import", "com.googlecode.iterm2", str(self.home / standard)]
            )
        print(
            f"Recovered settings. Pre-recovery copy: {undo}. Package installs are not rolled back."
        )

    def doctor(self):
        inventory = self.inventory()
        installed = {item["name"] for item in inventory["formulae"] + inventory["casks"]}
        expected = parse_brewfile((self.root / "Brewfile").read_text())
        missing = [name for kind, name in expected if kind != "tap" and name not in installed]
        sources = []
        for item in self.sources():
            try:
                revision = self.run(
                    ["git", "-C", str(self.home / item["target"]), "rev-parse", "HEAD"]
                ).strip()
            except RuntimeError:
                revision = None
            sources.append({"name": item["name"], "matches_lock": revision == item["revision"]})
        report = {
            "architecture": inventory["architecture"],
            "formulae": len(inventory["formulae"]),
            "casks": len(inventory["casks"]),
            "missing_core": missing,
            "shell_sources": sources,
            "services_inventory_only": inventory["services"],
            "warnings": inventory["warnings"],
        }
        print(json.dumps(report, indent=2))
        return not missing and all(source["matches_lock"] for source in sources)

    def check(self):
        paths = [self.root / "Brewfile"]
        for folder in ("dotfiles", "manifests", "iterm2"):
            paths.extend(path for path in (self.root / folder).rglob("*") if path.is_file())
        for path in paths:
            if path.is_symlink():
                raise ValueError("Public configuration must not contain symlinks")
            safe_public(path.read_bytes())
            if path.suffix == ".json":
                json.loads(path.read_text())
        parse_brewfile((self.root / "Brewfile").read_text())
        parse_brewfile((self.root / "manifests/Brewfile.full").read_text())
        print(
            f"Validated {len(paths)} public configuration/manifest files. This is a heuristic privacy check, not a guarantee."
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mac shell backup and restore. Restores preview unless --apply is explicit."
    )
    sub = parser.add_subparsers(dest="command")
    restore = sub.add_parser("restore", help="Preview or apply a portable setup")
    restore.add_argument("--profile", choices=("core", "full"), default="full")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--configs-only", action="store_true")
    restore.add_argument(
        "--extras",
        action="store_true",
        help="Also restore captured NVM versions, npm/pipx packages and VS Code extensions",
    )
    restore.add_argument(
        "--install-homebrew",
        action="store_true",
        help="Explicitly permit official Homebrew bootstrap in setup.sh",
    )
    snapshot = sub.add_parser(
        "snapshot", help="Refresh public package inventory, optionally reviewed appearance settings"
    )
    snapshot.add_argument("--settings", action="store_true")
    sub.add_parser("backup", help="Create a private local allowlisted settings backup")
    recover = sub.add_parser("recover", help="Preview or recover a private settings backup")
    recover.add_argument("--backup", required=True)
    recover.add_argument("--apply", action="store_true")
    recover.add_argument("--full-iterm", action="store_true")
    sub.add_parser("doctor", help="Read-only inventory and drift diagnostics")
    sub.add_parser("check", help="Validate public manifests and screen for obvious private values")
    args = parser.parse_args(argv)
    manager = Manager()
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "restore":
        manager.restore(args.profile, args.apply, args.configs_only, args.extras)
    elif args.command == "snapshot":
        manager.snapshot(args.settings)
    elif args.command == "backup":
        directory = manager.backup()
        write_json(directory / "inventory.json", manager.inventory())
        os.chmod(directory / "inventory.json", 0o600)
    elif args.command == "recover":
        manager.recover(args.backup, args.apply, args.full_iterm)
    elif args.command == "doctor":
        return 0 if manager.doctor() else 1
    elif args.command == "check":
        manager.check()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as error:
        print(f"macenv: {error}", file=sys.stderr)
        sys.exit(1)
