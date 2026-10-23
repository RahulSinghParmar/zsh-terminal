import contextlib
import io
import json
import plistlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macenv


class MacenvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="macenv-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "repo"
        self.home = self.base / "fake-home"
        self.root.mkdir()
        self.home.mkdir()
        (self.root / "manifests").mkdir()
        (self.root / "dotfiles").mkdir()
        (self.root / "Brewfile").write_text('brew "nnn"\ncask "iterm2"\n')
        (self.root / "manifests/Brewfile.full").write_text('brew "btop"\n')
        shutil.copyfile(
            macenv.ROOT / "manifests/shell-sources.json", self.root / "manifests/shell-sources.json"
        )
        (self.root / "dotfiles/zshrc").write_text("# portable\n")
        self.calls = []
        self.manager = macenv.Manager(self.root, self.home, self.run_command, brew="/fake/brew")
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def run_command(self, command):
        self.calls.append(command)
        if command[1:4] == ["info", "--json=v2", "--installed"]:
            return json.dumps(
                {
                    "formulae": [
                        {
                            "full_name": "nnn",
                            "installed": [{"version": "5.1", "installed_on_request": True}],
                        },
                        {"full_name": "owner/tap/tool", "installed": [{"version": "1.0"}]},
                    ],
                    "casks": [{"token": "iterm2", "installed": "3.6"}],
                }
            )
        if command[1:] == ["tap"]:
            return "owner/tap\n"
        if command[1:] == ["services", "list", "--json"]:
            return json.dumps(
                [
                    {
                        "name": "service",
                        "status": "none",
                        "user": "PRIVATE_USER",
                        "file": "/Users/PRIVATE_USER/service.plist",
                    }
                ]
            )
        if command[0] == "npm":
            return json.dumps(
                {"path": "/Users/PRIVATE_USER", "dependencies": {"npm": {"version": "11.0"}}}
            )
        if command[0] == "pipx":
            return '{"venvs":{}}'
        if command[0] == "code":
            return "publisher.extension@1.2.3\n/Users/PRIVATE_USER\n"
        if "rev-parse" in command:
            raise RuntimeError("not installed")
        return ""

    def put(self, relative, data=b"original"):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def mac(self):
        stack = contextlib.ExitStack()
        stack.enter_context(patch("macenv.platform.system", return_value="Darwin"))
        stack.enter_context(patch("macenv.os.geteuid", return_value=1000, create=True))
        return stack

    def test_preview_does_not_modify_home_or_run_commands(self):
        self.put(".zshrc")
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))
        self.manager.restore()
        self.assertEqual(
            before, sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))
        )
        self.assertEqual((self.home / ".zshrc").read_bytes(), b"original")
        self.assertEqual(self.calls, [])

    def test_install_backs_up_previous_files_and_is_idempotent(self):
        self.put(".zshrc", b"my old config")
        backup = self.manager.install_files({".zshrc": b"new"})
        manifest = json.loads((backup / "manifest.json").read_text())
        self.assertEqual(manifest["kind"], "transaction")
        self.assertEqual((backup / "files/.zshrc").read_bytes(), b"my old config")
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual((backup / "files/.zshrc").stat().st_mode & 0o777, 0o600)
        self.assertIsNone(self.manager.install_files({".zshrc": b"new"}))

    def test_capture_excludes_credentials_history_logs_and_sessions(self):
        for relative in (
            ".zshrc",
            ".p10k.zsh",
            ".config/nnn/plugins/preview",
            "Library/Fonts/Example.ttf",
        ):
            self.put(relative)
        for relative in (
            ".ssh/id_ed25519",
            ".config/gh/hosts.yml",
            ".aws/credentials",
            ".npmrc",
            ".zsh_history",
            ".config/atuin/history.db",
            ".config/btop/btop.log",
            ".config/nnn/sessions/private",
        ):
            self.put(relative, b"private")
        backup = self.manager.backup()
        entries = json.loads((backup / "manifest.json").read_text())["files"]
        self.assertEqual(
            {entry["path"] for entry in entries},
            {".zshrc", ".p10k.zsh", ".config/nnn/plugins/preview", "Library/Fonts/Example.ttf"},
        )

    def test_symlink_destinations_and_parent_directories_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.home / ".config").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.manager.install_files({".config/btop/btop.conf": b"new"})
        self.assertEqual(list(outside.iterdir()), [])
        (self.home / ".zshrc").symlink_to(outside / "secret")
        with self.assertRaises(ValueError):
            self.manager.install_files({".zshrc": b"new"})

    def test_unsafe_paths_and_directory_targets_are_refused(self):
        for path in ("../../secret", "/tmp/secret", "a/../secret", "a\\secret"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                macenv.target_path(self.home, path)
        (self.home / ".zshrc").mkdir()
        with self.assertRaises(ValueError):
            self.manager.install_files({".zshrc": b"new"})

    def test_backup_parent_symlink_refused(self):
        (self.root / "local").symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.manager.backup()

    def test_recover_previews_then_restores_exact_captured_bytes(self):
        self.put(".zshrc", b"old")
        backup = self.manager.backup()
        self.put(".zshrc", b"current")
        self.manager.recover(backup)
        self.assertEqual((self.home / ".zshrc").read_bytes(), b"current")
        with self.mac():
            self.manager.recover(backup, apply=True)
        self.assertEqual((self.home / ".zshrc").read_bytes(), b"old")
        self.assertFalse(any("install" in call for call in self.calls))

    def test_recover_refuses_tampered_backup_before_changing_anything(self):
        self.put(".zshrc", b"old")
        backup = self.manager.backup()
        (backup / "files/.zshrc").write_bytes(b"modified")
        with self.mac(), self.assertRaises(ValueError):
            self.manager.recover(backup, apply=True)
        self.assertEqual((self.home / ".zshrc").read_bytes(), b"old")

    def test_recover_rejects_traversal_and_duplicate_manifest_entries(self):
        self.put(".zshrc")
        backup = self.manager.backup()
        manifest = json.loads((backup / "manifest.json").read_text())
        original = manifest["files"][0].copy()
        for entries in ([{**original, "path": "../outside"}], [original, original]):
            (backup / "manifest.json").write_text(json.dumps({**manifest, "files": entries}))
            with self.mac(), self.assertRaises(ValueError):
                self.manager.recover(backup, apply=True)

    def test_rollback_removes_only_unchanged_new_files(self):
        backup = self.manager.install_files({".hushlogin": b""})
        with self.mac():
            self.manager.recover(backup, apply=True)
        self.assertFalse((self.home / ".hushlogin").exists())
        backup = self.manager.install_files({".hushlogin": b""})
        self.put(".hushlogin", b"edited")
        with self.mac(), self.assertRaises(ValueError):
            self.manager.recover(backup, apply=True)
        self.assertEqual((self.home / ".hushlogin").read_bytes(), b"edited")

    def test_recover_preserves_private_plugin_executable_bit(self):
        path = self.put(".config/nnn/plugins/custom", b"#!/bin/sh\n")
        path.chmod(0o755)
        backup = self.manager.backup()
        path.write_bytes(b"different")
        with self.mac():
            self.manager.recover(backup, apply=True)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_full_iterm_requires_closed_app_and_is_excluded_by_default(self):
        relative = "Library/Preferences/com.googlecode.iterm2.plist"
        self.put(relative, plistlib.dumps({"New Bookmarks": []}))
        backup = self.manager.backup()
        self.put(relative, b"current")
        with self.mac():
            self.manager.recover(backup, apply=True)
        self.assertEqual((self.home / relative).read_bytes(), b"current")
        with self.mac(), patch("macenv.subprocess.run") as process:
            process.return_value.returncode = 0
            with self.assertRaises(RuntimeError):
                self.manager.recover(backup, apply=True, full_iterm=True)
        self.assertEqual((self.home / relative).read_bytes(), b"current")

    def test_full_iterm_import_uses_defaults_without_launching_app(self):
        relative = "Library/Preferences/com.googlecode.iterm2.plist"
        data = plistlib.dumps({"New Bookmarks": []})
        self.put(relative, data)
        backup = self.manager.backup()
        self.put(relative, b"current")
        with self.mac(), patch("macenv.subprocess.run") as process:
            process.return_value.returncode = 1
            self.manager.recover(backup, apply=True, full_iterm=True)
        self.assertTrue(
            any(
                call[:3] == ["/usr/bin/defaults", "import", "com.googlecode.iterm2"]
                for call in self.calls
            )
        )
        self.assertEqual((self.home / relative).read_bytes(), data)

    def test_brewfile_rejects_executable_ruby_service_and_path_injection(self):
        for text in (
            'system "evil"',
            'brew "nnn", restart_service: true',
            'brew "../bad"',
            'brew "x";exec(1)"',
            'brew "https://example.com/private"',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                macenv.parse_brewfile(text)
        self.assertEqual(
            macenv.parse_brewfile('brew "nnn"\nbrew "nnn"\n# comment'), [("brew", "nnn")]
        )

    def test_snapshot_records_every_formula_cask_tap_without_private_metadata(self):
        self.manager.snapshot()
        inventory = (self.root / "manifests/inventory.json").read_text()
        self.assertNotIn("PRIVATE_USER", inventory)
        self.assertNotIn("service.plist", inventory)
        data = (self.root / "manifests/Brewfile.full").read_text()
        for entry in ('brew "nnn"', 'brew "owner/tap/tool"', 'cask "iterm2"', 'tap "owner/tap"'):
            self.assertIn(entry, data)
        self.assertNotIn("restart_service", data)

    def test_optional_inventory_failure_is_visible_not_fatal(self):
        original = self.manager.run

        def run(command):
            if "services" in command:
                raise RuntimeError("private failure")
            return original(command)

        self.manager.run = run
        inventory = self.manager.inventory()
        self.assertEqual(inventory["services"], [])
        self.assertTrue(inventory["warnings"])
        self.assertNotIn("private failure", json.dumps(inventory))

    def test_public_export_refuses_private_values_and_leaves_snapshot_unchanged(self):
        self.put(".p10k.zsh", b"export API_KEY=private-value")
        before = (self.root / "manifests/Brewfile.full").read_bytes()
        with self.assertRaises(ValueError):
            self.manager.snapshot(settings=True)
        self.assertEqual((self.root / "manifests/Brewfile.full").read_bytes(), before)

    def test_public_iterm_exports_visuals_without_commands_keys_or_private_names(self):
        preferences = {
            "Default Bookmark Guid": "original",
            "New Bookmarks": [
                {
                    "Guid": "original",
                    "Name": "PRIVATE_USER",
                    "Normal Font": "MesloLGSNF-Regular 12",
                    "Columns": 160,
                    "Rows": 30,
                    "Command": "ssh PRIVATE_HOST",
                    "Keyboard Map": {"key": "secret"},
                    "Working Directory": "/Users/PRIVATE_USER",
                    "Ansi 1 Color": {"Red Component": 1.0},
                    "Status Bar Layout": {"private": "data"},
                    "Bound Hosts": ["PRIVATE_HOST"],
                }
            ],
        }
        result = macenv.public_iterm(preferences)
        text = json.dumps(result)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("Keyboard Map", text)
        self.assertNotIn("Status Bar Layout", text)
        self.assertEqual(result["Profiles"][0]["Normal Font"], "MesloLGSNF-Regular 12")
        self.assertNotEqual(result["Profiles"][0]["Guid"], "original")

    def test_public_scanner_rejects_tokens_private_keys_and_home_paths(self):
        for value in (
            b"/Users/someone/private",
            b"-----BEGIN OPENSSH PRIVATE KEY-----",
            b"ghp_example",
            b"Bearer example",
            b"password=example",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                macenv.safe_public(value)
        self.assertEqual(
            macenv.safe_public(b"# secret = example comment\n"), b"# secret = example comment\n"
        )

    def test_restore_configs_only_does_not_install_or_fetch(self):
        with self.mac():
            self.manager.restore(apply=True, configs_only=True)
        self.assertEqual(self.calls, [])
        self.assertEqual((self.home / ".zshrc").read_text(), "# portable\n")

    def test_restore_merges_core_full_and_never_cleans_or_starts_services(self):
        with self.mac(), patch.object(self.manager, "ensure_sources") as sources:
            self.manager.restore(apply=True)
        sources.assert_called_once()
        self.assertTrue(
            any(
                command[1:3] == ["bundle", "install"] and "--no-upgrade" in command
                for command in self.calls
            )
        )
        self.assertFalse(
            any(
                "cleanup" in command or "start" in command or "sudo" in command
                for command in self.calls
            )
        )

    def test_package_install_failure_does_not_replace_dotfiles(self):
        self.put(".zshrc", b"original")
        self.manager.run = lambda command: (_ for _ in ()).throw(RuntimeError("install failed"))
        with self.mac(), self.assertRaises(RuntimeError):
            self.manager.restore(apply=True)
        self.assertEqual((self.home / ".zshrc").read_bytes(), b"original")

    def test_restore_on_non_macos_or_root_is_refused(self):
        with patch("macenv.platform.system", return_value="Linux"), self.assertRaises(RuntimeError):
            self.manager.restore(apply=True)
        with (
            patch("macenv.platform.system", return_value="Darwin"),
            patch("macenv.os.geteuid", return_value=0, create=True),
            self.assertRaises(RuntimeError),
        ):
            self.manager.restore(apply=True)
        self.assertEqual(self.calls, [])

    def test_shell_source_lock_rejects_untrusted_urls_targets_and_symlink_parents(self):
        path = self.root / "manifests/shell-sources.json"
        original = json.loads(path.read_text())
        for override in (
            {"url": "https://example.com/evil.git"},
            {"revision": "branch"},
            {"target": "../outside"},
        ):
            path.write_text(json.dumps([{**original[0], **override}]))
            with self.assertRaises(ValueError):
                self.manager.sources()
        path.write_text(json.dumps(original))
        (self.home / ".oh-my-zsh").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.manager.sources()

    def test_existing_shell_sources_are_preserved_without_network(self):
        for item in self.manager.sources():
            self.put(f"{item['target']}/{item['entry']}", b"keep")
        self.manager.ensure_sources()
        self.assertEqual(self.calls, [])

    def test_source_fetch_failure_does_not_leave_half_installed_target(self):
        self.manager.run = lambda command: (_ for _ in ()).throw(RuntimeError("network failed"))
        with self.assertRaises(RuntimeError):
            self.manager.ensure_sources()
        self.assertFalse((self.home / ".oh-my-zsh").exists())
        self.assertFalse(any(self.home.glob(".macenv-source-*")))

    def extras(self, **overrides):
        data = {
            "extras_inventory_only": {
                "npm": {"npm": "11.0.0", "@scope/tool": "1.2.3"},
                "pipx": {"example": "1.0.0"},
                "vscode": ["publisher.extension@1.0.0"],
            },
            "nvm_versions_inventory_only": ["v22.1.0"],
            "nvm_default": "22",
        }
        data.update(overrides)
        (self.root / "manifests/inventory.json").write_text(json.dumps(data))
        return self.manager.extras_plan()

    def test_extras_plan_pins_packages_and_does_not_replace_npm(self):
        commands, versions, alias = self.extras()
        self.assertIn(["npm", "install", "--global", "@scope/tool@1.2.3"], commands)
        self.assertIn(["pipx", "install", "example==1.0.0"], commands)
        self.assertIn(["code", "--install-extension", "publisher.extension@1.0.0"], commands)
        self.assertFalse(any(command[-1].startswith("npm@") for command in commands))
        self.assertEqual(versions, ["v22.1.0"])
        self.assertEqual(alias, "22")

    def test_extras_reject_option_and_shell_injection_before_execution(self):
        for overrides in (
            {"extras_inventory_only": {"npm": {"--evil": "1.0.0"}}},
            {"extras_inventory_only": {"pipx": {"name": "--evil"}}},
            {"extras_inventory_only": {"vscode": ["--evil.name@1.0.0"]}},
            {"nvm_versions_inventory_only": ["v22; command"]},
            {"nvm_default": "$(command)"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.extras(**overrides)
        self.assertEqual(self.calls, [])

    def test_extras_preview_makes_no_network_requests(self):
        self.extras()
        self.manager.restore(extras=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_runtime_restore_passes_values_as_quoted_positional_arguments(self):
        plan = self.extras(extras_inventory_only={})
        self.put(".nvm/nvm.sh", b"# test only")
        self.manager.restore_extras(plan)
        bash = [command for command in self.calls if command[0] == "/bin/bash"]
        self.assertEqual(len(bash), 2)
        self.assertEqual(bash[0][-1], "v22.1.0")
        self.assertIn('nvm install "$3"', bash[0][4])
        self.assertEqual(bash[1][-1], "22")

    def test_configs_only_and_extras_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            self.manager.restore(configs_only=True, extras=True)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
