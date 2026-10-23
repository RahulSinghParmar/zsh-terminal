# Configuration and backup security

This is a personal setup repository with a public, deliberately limited configuration layer and a private local recovery layer.

- Never commit `local/`, raw iTerm preferences, cloud/API keys, `.ssh`, `.npmrc`, GitHub authentication files, shell history, Atuin databases/account keys, or editor account/session databases.
- Public snapshots use field allowlists and conservative secret/path screening. This is not proof that a configuration is safe to publish. Review the diff, including package names and custom tap names.
- Private backups are unencrypted and may contain sensitive values inside raw configuration. They are owner-private on disk and Git-ignored, but must still be protected and copied to encrypted off-machine storage. Do not upload them as GitHub release assets, attach them to issues, or run `git add -f local`.
- Restore executes trusted upstream code through package managers and pinned shell repositories. Brewfiles accept only plain tap/formula/cask identifiers; arbitrary Ruby and service directives are rejected. Review third-party taps and optional editor extensions before using `--apply`.
- `--install-homebrew` is an explicit opt-in to the official interactive installer. No automation should bypass OS permission prompts, application licenses, or administrator confirmation.
- Apply/recovery refuse root execution and symlink destinations. Do not run simultaneous restores or edit destination files while a restore is running; this is not an adversarial multi-user configuration manager or a globally atomic transaction.
- A restored shell/plugin/keyboard configuration can execute code. Only recover backups you trust. Checksums are not digital signatures.

For vulnerabilities use [private vulnerability reporting](https://github.com/RahulSinghParmar/zsh-terminal/security/advisories/new) if enabled, or contact the maintainer privately through the profile. Do not put secrets or personal backup contents in public reports. No response-time guarantee is provided.
