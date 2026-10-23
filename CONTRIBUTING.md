# Development

The manager uses Python's standard library only. Tests must use temporary fake home directories and injected command runners. Never install packages, invoke a real restore, start services, change terminal preferences, or modify an actual user's dotfiles in CI/tests.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
python3 -m unittest discover -s tests -v
./setup.sh check
/bin/bash -n setup.sh
/bin/zsh -n dotfiles/zshrc
/bin/zsh -n dotfiles/zprofile
/bin/zsh -n dotfiles/p10k.zsh
./setup.sh restore --profile full --extras
```

Keep all default restore behavior read-only. Add regression tests for path handling, backup/recovery, failure conditions, and privacy boundaries. Do not update personal snapshots from a CI runner's environment. Explain any added backup path, upstream source change, or newly executable installation step in the pull request.

No license has been selected for the original repository code; discuss substantial third-party contributions with the owner first. See [third-party notices](THIRD_PARTY_NOTICES.md) for existing upstream material.
