# Terminal toolkit

The complete captured package list is [manifests/Brewfile.full](manifests/Brewfile.full), with versions and optional extras in [the inventory](manifests/inventory.json). This page highlights tools actually found on the inspected Mac; it is not another installation script.

| Purpose | Tools |
| --- | --- |
| File browsing | nnn, yazi, ranger, lf, Midnight Commander, superfile |
| Search and navigation | fzf, ripgrep (`rg`), fd, zoxide (`z`) |
| Files and diffs | eza (`ls`/`ll`/`la` aliases), bat, git-delta, difftastic, jless, jq |
| Monitoring | bpytop, btop, htop, neohtop |
| Shell/history | Zsh, Oh My Zsh, Powerlevel10k, Atuin, autosuggestions, syntax highlighting |
| Development | Git, gh, Node/NVM, pnpm, Deno, Python, pipx, Go, Rust, Ruby, Neovim, tmux, VS Code |
| Networking | curl, wget, nmap, cloudflared, speedtest, wakeonlan |
| Media and documents | yt-dlp, ffmpeg, ImageMagick, Ghostscript, Tesseract, TeX tooling |

The managed shell guards optional commands: missing tools should not break startup. `nnn` is available as `n`. Atuin's private history/account state is not stored in this repository. Homebrew services are inventoried but never automatically started.

Examples after installation:

```sh
n                    # nnn file browser
bpytop               # Python-based monitor
btop                 # C++ resource monitor
z project            # zoxide directory jump
rg 'search term' .   # recursive source search
yt-dlp --help        # maintained downloader, replacing old youtube-dl notes
```

Some captured tools overlap because this is a personal environment snapshot, not a claim that everyone needs every package. Start with the core profile on a clean machine if you do not want the whole historical toolset.
