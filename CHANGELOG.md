# Changelog

## Mac environment manager — initial automation

- Captured the current Intel Mac's 235 Homebrew formulae, 7 casks, 2 custom taps, Node/NVM inventory, and VS Code extensions without credential-bearing metadata.
- Added portable core/full Brewfiles and a safe-by-default, stdlib-only setup manager with explicit apply, optional extras/Homebrew bootstrap, drift diagnostics, private backups, checksum-checked recovery, and configuration undo.
- Preserved Powerlevel10k appearance, bpytop/btop/htop preferences, and a privacy-filtered iTerm dynamic profile. Raw settings remain in ignored local backups.
- Added portable shell initialization: early architecture-aware Homebrew paths, guarded tools/Java, one NVM load, and private local override hooks. The working Mac's shell files have not been replaced.
- Added offline tests, macOS/Linux CI, manifest privacy checks, source revision locks, dependency workflow updates, recovery/security documentation, and upstream notices.
- Retained historical screenshots/manual guides; they are not the supported installation workflow. Removed tracked Finder metadata.
