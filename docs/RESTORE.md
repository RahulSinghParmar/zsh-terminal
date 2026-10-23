# Restore and recovery runbook

## Fresh or replacement Mac

1. Make sure Apple's Command Line Tools/Git are available. macOS may require a user-confirmed installation dialog (`xcode-select --install`). Use your normal administrator account, not `sudo ./setup.sh`.
2. Clone this repository. Review `Brewfile`, `manifests/Brewfile.full`, the shell-source lock, and the captured inventory. The full profile contains development SDKs and large applications, including TeX; downloading everything can be substantial.
3. Run a preview: `./setup.sh restore --profile full --extras`. Preview only reads the checkout/current destination paths: it does not install anything, connect to package servers, or write your home directory. Python 3.9+ is needed to run the manager.
4. Apply with `./setup.sh restore --profile full --extras --apply --install-homebrew`. On a Mac without Homebrew this explicitly permits the official interactive Homebrew installer. It keeps its confirmation/admin prompts. Existing Homebrew installations are reused. If Python is missing, the wrapper installs it through Homebrew. This is a one-command workflow, not a promise of zero user interaction.
5. Open a new login shell. In iTerm2, choose **Rahul · Main** from Profiles, then make it the default manually if desired. The dynamic profile is deliberately not assigned as your default or given the original profile's GUID, so it cannot silently hijack or collide with an existing regular profile.
6. Run `./setup.sh doctor`. Differences are reported, not automatically “fixed.” Core casks may be reported missing even when equivalent fonts/iTerm were installed manually; the diagnostic is a Homebrew ownership check, not proof the app is absent.

For a lighter setup use `--profile core`. For managed configuration only use `--configs-only` (no package installation or shell-source fetching). Do not combine it with `--extras`.

## What apply does

- Validates public configuration, paths, strict plain-name Brewfiles, source locks, and optional extras before replacing settings.
- Merges the chosen package profile with the core toolkit and runs `brew bundle install --no-upgrade`. There is no blanket `brew upgrade`, `brew bundle cleanup`, uninstall, analytics setting change, or service-start command. Dependencies can still require adjustments/upgrades; see [Homebrew's command documentation](https://docs.brew.sh/Manpage#bundle-subcommand).
- Fetches missing Oh My Zsh, Powerlevel10k, autosuggestions, and highlighting repositories at the exact recorded commits. Existing source directories are kept, not reset or automatically updated. Run doctor to check for drift. Powerlevel10k may download its platform-specific gitstatus component on first use.
- Optionally installs the captured NVM version(s), default alias, npm/pipx tools, and version-qualified VS Code extensions with `--extras`. It does not replace npm/corepack supplied with Node. These installs execute upstream package code; review the inventory first. Availability and compatibility of old versions are not guaranteed.
- Installs the tracked portable files as regular, owner-private copies, not symlinks into the checkout. Files already matching are left alone. The checkout can then move without breaking your shell.
- Stores previous versions of changed files in `~/.local/state/macenv/backups/<timestamp>-<random>/` before atomic per-file replacements. Changes to separate files and package installs are not one global transaction; interruptions can leave partial installation. Repair the problem, preview, and rerun.

Shell source retrieval and packages need network access. Homebrew packages are a **name-based desired state**, not a historical lockfile: installed versions are recorded for reference, but a restore generally gets versions available from Homebrew today. Some Intel-era formulae may be unavailable or unsupported on another macOS/CPU. There is no automatic Rosetta installation or architecture emulation.

## Keep backups current

```sh
./setup.sh backup
./setup.sh snapshot --settings
./setup.sh check
git diff --stat
git diff -- Brewfile manifests dotfiles iterm2
```

`backup` captures exact allowlisted settings into ignored `local/backups/`, including raw shell files, Powerlevel10k, terminal/tool settings, iTerm preferences, user fonts, selected nnn files, VS Code settings/keybindings/snippets, and Zed settings if present. It also records a sanitized software inventory. Files are checksummed, stored owner-private, and are **not encrypted**. Keep an encrypted, off-machine copy before losing/replacing the Mac; a backup left only inside this checkout will not survive disk loss. FileVault protects the disk at rest, not an unencrypted exported backup on another volume.

`snapshot` refreshes the public package inventory and generated full Brewfile. `--settings` additionally exports the selected appearance/tool configurations. It deliberately does **not** publish raw `.zshrc`, full iTerm preferences, VS Code settings, arbitrary custom scripts, or credentials. The tracked shell files remain curated, portable templates. Scanning catches obvious secrets and account paths but is heuristic: manually review all diffs before committing. Refreshing the inventory does not automatically change `shell-sources.json` revisions.

No cron job, LaunchAgent, automatic commit, or scheduled upload is installed. Run these commands after intentional environment changes; back up the resulting private folder securely yourself.

## Recover exact private settings

First preview against the new/current home:

```sh
./setup.sh recover --backup /path/to/private-backup
./setup.sh recover --backup /path/to/private-backup --apply
```

Recovery checks the allowlist, rejects symlink destinations/path traversal and duplicate entries, and verifies file hashes before changing anything. It saves the current versions first. Executable user plugins are restored owner-executable; other recovered files are owner-private. Hashes detect corruption but do not authenticate a backup if someone can rewrite both the files and manifest. Only recover a trusted backup.

Raw shell files contain the **old** machine's paths and initialization logic. Recover them for exact same-machine recovery/undo; prefer the portable restore templates for Intel-to-Apple-Silicon migration. Private local overrides (`.zshrc.local`, `.zprofile.local`) are supported by the templates and kept outside Git. Existing untracked customizations in `.zshrc` are backed up, but are not automatically merged into the new managed file.

### Full iTerm settings

The public dynamic profile contains the current default profile's colors, font, spacing, geometry, cursor, and selected display options. Custom commands, host rules, keybinding text, AI settings, profile names, and working directories are not public exports.

To restore **all** captured iTerm preferences, including original profiles/keybindings/global UI settings:

1. Quit iTerm2 completely.
2. Open Apple Terminal and preview with `./setup.sh recover --backup /path/to/private-backup --full-iterm`.
3. Apply with the same command plus `--apply`. The manager refuses this operation while iTerm2 is running, restores the captured preferences, and imports the standard preference domain with `defaults import`.
4. Reopen iTerm2 and review fonts, paths, application version compatibility, profile defaults, and any account/provider settings.

Only the standard preference file and `~/.config/iterm2/com.googlecode.iterm2.plist` are included automatically. If you use a custom preference folder elsewhere, back it up separately. Existing profiles continue to work; the new public dynamic profile may remain available alongside them.

### Undo managed configuration changes

Use the transaction backup printed by restore:

```sh
./setup.sh recover --backup /path/to/transaction-backup
./setup.sh recover --backup /path/to/transaction-backup --apply
```

Previous files are restored. Newly created managed files are removed **only if unchanged** since installation; edited files cause recovery to stop for manual review. Recovery does not uninstall packages, undo runtime/package installs, reset Git repositories, or reverse account sign-ins.

## Not a full Mac image

This repository does not back up your projects, application binaries/data, database contents, Docker volumes, Python virtualenvs, global pip dependencies for every interpreter, Java SDKs installed outside Homebrew, SSH/GPG keys, Keychain, Git identity/credentials, cloud credentials, browser sessions, Atuin history/account keys, editor extension account data, or system/login services. Reauthenticate from your password manager, restore project dependencies from their own lockfiles, and retain Time Machine/another full-machine backup for those needs.

Captured warnings are in `manifests/inventory.json`. On the inspected Mac, pipx's inventory command failed: its formula is captured, but its installed Python apps could not be verified. Resolve that locally and refresh the snapshot before relying on pipx recovery. Existing npm/NVM and VS Code inventories are handled separately from Homebrew. `--extras` does not imply unavailable inventories were recovered.
