#!/bin/bash
# Works with macOS's bundled Bash. Preview is the default; never run as root.
set -eu
MACENV_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
macenv_apply=false
macenv_bootstrap=false
for macenv_arg in "$@"; do
  case "$macenv_arg" in
    --apply) macenv_apply=true ;;
    --install-homebrew) macenv_bootstrap=true ;;
  esac
done

macenv_validate_bootstrap() {
  local macenv_configs_only=false macenv_extras=false
  [ "${1:-}" = restore ] || return 1
  shift
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --profile)
        shift
        case "${1:-}" in core|full) ;; *) return 1 ;; esac ;;
      --extras) macenv_extras=true ;;
      --configs-only) macenv_configs_only=true ;;
      --apply|--install-homebrew) ;;
      *) return 1 ;;
    esac
    shift
  done
  [ "$macenv_configs_only" = false ] || [ "$macenv_extras" = false ]
}

macenv_python_ready() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null
}

if [ "$macenv_bootstrap" = true ] && [ "$macenv_apply" = true ]; then
  macenv_validate_bootstrap "$@" || { echo 'Invalid bootstrap arguments; no installer started.' >&2; exit 1; }
  [ "$(uname -s)" = Darwin ] || { echo 'Homebrew bootstrap requires macOS.' >&2; exit 1; }
  [ "$(id -u)" -ne 0 ] || { echo 'Run as your normal user, not sudo/root.' >&2; exit 1; }
  [ "${1:-}" = restore ] || { echo '--install-homebrew is only valid with restore.' >&2; exit 1; }
  if ! command -v brew >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/brew ] && [ ! -x /usr/local/bin/brew ]; then
    # Official interactive installer retains its own confirmation/admin prompts.
    /bin/bash -c "$(/usr/bin/curl --fail --silent --show-error --location https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  if [ -x /opt/homebrew/bin/brew ] && [ "$(uname -m)" = arm64 ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  if ! macenv_python_ready; then
    brew install python@3.13
    macenv_python="$(brew --prefix python@3.13)/bin/python3.13"
  fi
fi

if [ -z "${macenv_python:-}" ] && ! macenv_python_ready; then
  echo 'Python 3.9+ is required. For a fresh Mac: ./setup.sh restore --apply --install-homebrew' >&2
  exit 1
fi
exec "${macenv_python:-python3}" "$MACENV_ROOT/scripts/macenv.py" "$@"
