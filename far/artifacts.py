"""Package, verify, and install FAR diagnostic data releases."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import IO, Any
from urllib.request import Request, urlopen

from far.paths import repository_root

SCHEMA_VERSION = "far-diagnostic-artifacts-v1"
ARTIFACT_ID = "far-diagnostics-v2"
DEFAULT_SOURCE = repository_root() / "diagnostics"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "data" / "diagnostics-v2.json"
DEFAULT_ARCHIVE = repository_root() / "artifact-dist" / f"{ARTIFACT_ID}.tar.gz"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def inventory(source: Path) -> dict[str, Any]:
    """Return a deterministic, exact inventory of one diagnostics directory."""

    if not source.is_dir():
        raise ValueError(f"diagnostic source is not a directory: {source}")
    files: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"diagnostic releases do not allow symlinks: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)})

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in files:
        grouped[PurePosixPath(str(item["path"])).parts[0]].append(item)
    bundles = {
        name: {
            "files": len(items),
            "bytes": sum(int(item["bytes"]) for item in items),
            "tree_sha256": _tree_digest(items),
        }
        for name, items in sorted(grouped.items())
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "source_directory": "diagnostics",
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(int(item["bytes"]) for item in files),
        "tree_sha256": _tree_digest(files),
        "bundles": bundles,
    }


def _tar_info(path: Path, arcname: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(arcname)
    info.size = path.stat().st_size
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _write_archive(source: Path, archive: Path, files: list[dict[str, Any]]) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temporary:
        tar_path = Path(temporary.name)
    try:
        with tarfile.open(tar_path, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for item in files:
                relative = str(item["path"])
                path = source / relative
                with path.open("rb") as handle:
                    tar.addfile(_tar_info(path, f"diagnostics/{relative}"), handle)
        with (
            tar_path.open("rb") as raw,
            archive.open("wb") as destination,
            gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed,
        ):
            shutil.copyfileobj(raw, compressed, length=1024 * 1024)
    finally:
        tar_path.unlink(missing_ok=True)


def pack(
    source: Path,
    archive: Path,
    manifest_path: Path,
    *,
    release_url: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic archive and its exact release manifest."""

    manifest = inventory(source)
    _write_archive(source, archive, manifest["files"])
    manifest["archive"] = {
        "filename": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": _sha256(archive),
        "release_url": release_url,
        "published": release_url is not None,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported diagnostic artifact manifest: {path}")
    return value


def verify(source: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify that a directory exactly matches a frozen manifest."""

    expected = _load_manifest(manifest_path)
    observed = inventory(source)
    keys = ("artifact_id", "files", "file_count", "total_bytes", "tree_sha256", "bundles")
    errors = [key for key in keys if observed.get(key) != expected.get(key)]
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "source": str(source),
        "manifest": str(manifest_path),
        "file_count": observed["file_count"],
        "total_bytes": observed["total_bytes"],
        "tree_sha256": observed["tree_sha256"],
    }


def _copy_stream(source: IO[bytes], destination: Path) -> None:
    with destination.open("wb") as handle:
        shutil.copyfileobj(source, handle, length=1024 * 1024)


def _obtain_archive(manifest: dict[str, Any], archive: Path | None, url: str | None) -> Path:
    if archive is not None:
        return archive
    resolved_url = url or manifest.get("archive", {}).get("release_url")
    if not resolved_url:
        raise ValueError("artifact is not published; pass --archive or --url explicitly")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temporary:
        destination = Path(temporary.name)
    request = Request(str(resolved_url), headers={"User-Agent": "FAR-artifact-installer/1.0"})
    try:
        with urlopen(request, timeout=120) as response:
            _copy_stream(response, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if member.issym() or member.islnk() or member.isdir():
                if member.isdir():
                    continue
                raise ValueError(f"archive links are forbidden: {member.name}")
            if not member.isfile() or len(parts) < 2 or parts[0] != "diagnostics":
                raise ValueError(f"unsafe artifact archive member: {member.name}")
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read archive member: {member.name}")
            _copy_stream(extracted, target)


def install(
    manifest_path: Path,
    target: Path,
    *,
    archive: Path | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Install a verified release without overwriting an existing data directory."""

    if target.exists():
        raise ValueError(f"refusing to overwrite existing target: {target}")
    manifest = _load_manifest(manifest_path)
    resolved = _obtain_archive(manifest, archive, url)
    temporary_download = archive is None
    try:
        archive_spec = manifest.get("archive", {})
        if _sha256(resolved) != archive_spec.get("sha256"):
            raise ValueError("diagnostic archive fingerprint mismatch")
        with tempfile.TemporaryDirectory(prefix="far-diagnostics-") as temporary:
            staging = Path(temporary)
            _extract_archive(resolved, staging)
            report = verify(staging / "diagnostics", manifest_path)
            if not report["valid"]:
                raise ValueError(f"diagnostic archive content mismatch: {report['errors']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging / "diagnostics"), target)
        return report | {"installed_to": str(target)}
    finally:
        if temporary_download:
            resolved.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack_parser = subparsers.add_parser("pack")
    verify_parser = subparsers.add_parser("verify")
    status_parser = subparsers.add_parser("status")
    install_parser = subparsers.add_parser("install")

    pack_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    pack_parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    pack_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    pack_parser.add_argument("--release-url")
    verify_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    verify_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    status_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    status_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    install_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    install_parser.add_argument("--target", type=Path, default=DEFAULT_SOURCE)
    install_parser.add_argument("--archive", type=Path)
    install_parser.add_argument("--url")
    args = parser.parse_args()

    if args.command == "pack":
        result = pack(args.source, args.archive, args.manifest, release_url=args.release_url)
    elif args.command == "verify":
        result = verify(args.source, args.manifest)
    elif args.command == "install":
        result = install(args.manifest, args.target, archive=args.archive, url=args.url)
    else:
        manifest = _load_manifest(args.manifest)
        result = {
            "schema_version": SCHEMA_VERSION,
            "source_present": args.source.is_dir(),
            "manifest_present": args.manifest.is_file(),
            "published": manifest.get("archive", {}).get("published") is True,
            "release_url": manifest.get("archive", {}).get("release_url"),
        }
        if args.source.is_dir():
            result["verification"] = verify(args.source, args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("valid") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
