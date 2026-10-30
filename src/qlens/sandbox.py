"""Run q inside a sandbox (SPEC section 6). The static pass runs here too."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


class SandboxError(RuntimeError):
    pass


@dataclass
class RunResult:
    returncode: int | None  # None on timeout
    stdout: str
    stderr: str
    timed_out: bool


def find_q() -> Path:
    cand = os.environ.get("Q") or str(Path.home() / ".kx" / "bin" / "q")
    p = Path(cand).expanduser()
    if not p.exists():
        raise SandboxError(f"q binary not found at {p} (set $Q)")
    return p.resolve()


def default_backend() -> str:
    return "sandbox-exec" if sys.platform == "darwin" else "docker"


def _q_install_paths(q_bin: Path) -> list[Path]:
    """Directories q needs to read: install root and licence location."""
    paths = [q_bin.parent.parent]
    for var in ("QHOME", "QLIC"):
        v = os.environ.get(var)
        if v:
            p = Path(v).expanduser().resolve()
            paths.append(p if p.is_dir() else p.parent)
    lic = Path.home() / ".kx"
    if lic.exists():
        paths.append(lic.resolve())
    seen: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return seen


def _sb_quote(p: Path | str) -> str:
    return '"' + str(p).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_exec_profile(q_bin: Path, read_paths: list[Path], write_dir: Path, home: Path | None = None) -> str:
    """macOS profile: no network, writes only to write_dir, exec only q, no reads under $HOME
    except q install, the given read paths and write_dir."""
    home = (home or Path.home()).resolve()
    return "\n".join(
        [
            "(version 1)",
            "(allow default)",
            "(deny network*)",
            "(deny file-write*)",
            f'(allow file-write* (subpath {_sb_quote(write_dir)}) (literal "/dev/null") (literal "/dev/dtracehelper"))',
            f"(deny file-read-data (subpath {_sb_quote(home)}))",
            f"(allow file-read-data file-read-metadata {' '.join(f'(subpath {_sb_quote(p)})' for p in [*_q_install_paths(q_bin), *read_paths, write_dir])})",
            "(deny process-exec*)",
            f"(allow process-exec (literal {_sb_quote(q_bin)}))",
            "",
        ]
    )


def docker_command(
    q_bin: Path,
    read_paths: list[Path],
    write_dir: Path,
    q_args: list[str],
    name: str,
    image: str,
    uid: int | None = None,
    gid: int | None = None,
) -> list[str]:
    """Linux: docker run with no network, read-only fs, caps dropped; workspace/q/licence mounted
    read-only at their host paths and one writable temp bind."""
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    cmd = [
        "docker", "run", "--rm", "--init", "--name", name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "256",
        "--memory", "2g", "--cpus", "1", "--user", f"{uid}:{gid}",
        "--tmpfs", "/tmp",
    ]  # fmt: skip
    mounted: list[Path] = []
    for p in [*_q_install_paths(q_bin), *read_paths]:
        if p not in mounted and p != write_dir:
            mounted.append(p)
            cmd += ["-v", f"{p}:{p}:ro"]
    cmd += ["-v", f"{write_dir}:{write_dir}:rw", "-e", f"HOME={q_bin.parent.parent.parent}"]
    for var in ("QHOME", "QLIC"):
        if os.environ.get(var):
            cmd += ["-e", f"{var}={os.environ[var]}"]
    cmd += ["-w", str(write_dir), image, str(q_bin), *q_args]
    return cmd


def run_q(
    q_args: list[str],
    read_paths: list[Path],
    write_dir: Path,
    timeout: float = 60,
    backend: str | None = None,
    image: str | None = None,
) -> RunResult:
    """Run `q <q_args>` sandboxed. write_dir must exist; it is the only writable path."""
    backend = backend or os.environ.get("QLENS_BACKEND") or default_backend()
    q_bin = find_q()
    write_dir = write_dir.resolve()
    read_paths = [Path(p).resolve() for p in read_paths]
    if backend == "sandbox-exec":
        if not shutil.which("sandbox-exec"):
            raise SandboxError("sandbox-exec not found")
        prof = write_dir / f"profile-{uuid.uuid4().hex[:8]}.sb"
        prof.write_text(sandbox_exec_profile(q_bin, read_paths, write_dir))
        cmd = ["sandbox-exec", "-f", str(prof), str(q_bin), *q_args]
        name = None
    elif backend == "docker":
        image = image or os.environ.get("QLENS_IMAGE") or "debian:stable-slim"
        name = f"qlens-{uuid.uuid4().hex[:10]}"
        cmd = docker_command(q_bin, read_paths, write_dir, q_args, name, image)
    else:
        raise SandboxError(f"unknown backend {backend!r}")
    try:
        cp = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL, cwd=write_dir,
        )  # fmt: skip
        return RunResult(cp.returncode, cp.stdout, cp.stderr, False)
    except subprocess.TimeoutExpired as e:
        if name:  # killing the docker CLI does not stop the container
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return RunResult(None, out, err, True)
