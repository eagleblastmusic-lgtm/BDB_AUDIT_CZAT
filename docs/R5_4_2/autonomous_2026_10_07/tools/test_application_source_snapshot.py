"""Application dirty-byte identity and fail-closed source readback controls."""
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import application_source_snapshot as snapshot
from execution import ROOT


class ApplicationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "._nf02_current_audit/application_snapshot_controls" / str(uuid.uuid4())
        self.root.mkdir(parents=True)
        for name, data in {"src/pkg/a.py": b"first\r\nsecond\r", "src/pkg/b.bin": b"\xff\r\n",
                           "build/build_single_file.py": b"recipe", "requirements-f2.lock": b"exact==1\n"}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def collector(self, src):
        return [("pkg/a.py", b"first\nsecond\n"), ("pkg/b.bin", b"\xff\r\n")]

    def test_exact_raw_bytes_and_existing_normalized_payload_remain_distinct(self):
        files, manifest = snapshot.construct(self.root, self.collector)
        self.assertEqual(files["raw/src/pkg/a.py"], b"first\r\nsecond\r")
        self.assertEqual(files["payload/pkg/a.py"], b"first\nsecond\n")
        self.assertEqual(files["payload/pkg/b.bin"], files["raw/src/pkg/b.bin"])
        self.assertEqual(len(manifest["entries"]), 4)
        self.assertNotIn("git_head", manifest)

    def test_missing_recipe_or_lock_is_not_silently_omitted(self):
        for name in ("build/build_single_file.py", "requirements-f2.lock"):
            path = self.root / name
            data = path.read_bytes()
            path.unlink()
            with self.subTest(name=name), self.assertRaises(FileNotFoundError):
                snapshot.construct(self.root, self.collector)
            path.write_bytes(data)

    def test_payload_omission_extra_duplicate_or_changed_bytes_reject(self):
        cases = [self.collector(None)[:1], self.collector(None) + [("other", b"x")],
                 self.collector(None) + [self.collector(None)[0]], [("pkg/a.py", b"changed"), self.collector(None)[1]]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "PAYLOAD"):
                snapshot.construct(self.root, lambda src: rows)

    def test_unresolved_lfs_and_nonfile_reject(self):
        path = self.root / "src/pkg/a.py"
        path.write_bytes(b"version https://git-lfs.github.com/spec/v1\r\noid sha256:x\r\n")
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_LFS"):
            snapshot.construct(self.root, self.collector)
        with self.assertRaisesRegex(ValueError, "NOT_REGULAR"):
            snapshot.regular(self.root, self.root / "src")

    def test_inventory_and_raw_drift_during_collection_reject(self):
        for action in (lambda: (self.root / "src/pkg/a.py").write_bytes(b"mutated"),
                       lambda: (self.root / "src/new.bin").write_bytes(b"added")):
            before = snapshot.inventory(self.root)
            def mutate(src):
                rows = self.collector(src)
                action()
                return rows
            with self.assertRaisesRegex(ValueError, "INPUT_DRIFT"):
                snapshot.construct(self.root, mutate)
            for name, (data, _) in before.items():
                (self.root / name).write_bytes(data)

    def test_mode_drift_reject(self):
        original = snapshot.inventory
        calls = 0
        def altered(root):
            nonlocal calls
            calls += 1
            value = original(root)
            if calls > 1:
                name = next(iter(value))
                data, mode = value[name]
                value[name] = (data, mode ^ 0o100)
            return value
        with patch.object(snapshot, "inventory", altered), self.assertRaisesRegex(ValueError, "INPUT_DRIFT"):
            snapshot.construct(self.root, self.collector)

    def test_retained_byte_and_inventory_tamper_reject(self):
        files, _ = snapshot.construct(self.root, self.collector)
        directory = self.root / "retained"
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        snapshot.verify(directory, files)
        target = directory / "raw/src/pkg/a.py"
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "READBACK_BYTES"):
            snapshot.verify(directory, files)
        target.write_bytes(files["raw/src/pkg/a.py"])
        (directory / "extra").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "READBACK_INVENTORY"):
            snapshot.verify(directory, files)

    def test_escape_and_symlink_reject(self):
        with self.assertRaisesRegex(ValueError, "PATH_ESCAPE"):
            snapshot.regular(self.root, self.root.parent / "outside")
        target = self.root / "src/pkg/a.py"
        # Verify the security branch without requiring Windows symlink privilege.
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path == target or original(path)):
            with self.assertRaisesRegex(ValueError, "SYMLINK"):
                snapshot.construct(self.root, self.collector)


if __name__ == "__main__":
    unittest.main()
