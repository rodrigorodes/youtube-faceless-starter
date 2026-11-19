"""Backup e restauração do Postgres (n8n + schema studio), só biblioteca padrão.

Uso:
  python scripts/backup.py backup            # grava backups/faceless-<data>.sql.gz + .sha256
  python scripts/backup.py verify <arquivo>
  python scripts/backup.py restore <arquivo> --yes   # SOBRESCREVE o banco atual
Credenciais ficam no container (variáveis POSTGRES_*); nada é impresso.
"""
import gzip
import hashlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose"]
PG_DUMP = 'pg_dump --clean --if-exists --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"'
PSQL = 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" "$POSTGRES_DB"'


def write_backup(dump: bytes, out_dir: Path, now: datetime) -> Path:
    if not dump.strip():
        raise ValueError("dump vazio: backup recusado")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"faceless-{now:%Y%m%d-%H%M%S}.sql.gz"
    data = gzip.compress(dump, mtime=0)
    path.write_bytes(data)
    (out_dir / (path.name + ".sha256")).write_text(f"{hashlib.sha256(data).hexdigest()}  {path.name}\n", encoding="utf-8")
    return path


def verify_backup(path: Path) -> bool:
    path = Path(path)
    sum_file = path.with_name(path.name + ".sha256")
    if not path.is_file() or not sum_file.is_file():
        return False
    data = path.read_bytes()
    if sum_file.read_text(encoding="utf-8").split()[0] != hashlib.sha256(data).hexdigest():
        return False
    try:
        return bool(gzip.decompress(data).strip())
    except (OSError, EOFError):
        return False


def _compose_exec(script: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, "exec", "-T", "postgres", "sh", "-c", script], cwd=ROOT, input=stdin, capture_output=True)


def main(argv: list[str]) -> int:
    cmd, args = (argv[0] if argv else ""), argv[1:]
    if cmd == "backup":
        proc = _compose_exec(PG_DUMP)
        if proc.returncode != 0:
            print("pg_dump falhou (a stack está de pé? docker compose ps)")
            return 1
        path = write_backup(proc.stdout, ROOT / "backups", datetime.now())
        print(f"backup gravado: {path} ({'verificado' if verify_backup(path) else 'FALHOU NA VERIFICAÇÃO'})")
        return 0 if verify_backup(path) else 1
    if cmd == "verify" and args:
        ok = verify_backup(Path(args[0]))
        print("íntegro" if ok else "CORROMPIDO ou sem checksum")
        return 0 if ok else 1
    if cmd == "restore" and args:
        if "--yes" not in args:
            print("restore SOBRESCREVE o banco atual; repita com --yes se for isso mesmo")
            return 2
        path = Path(args[0])
        if not verify_backup(path):
            print("arquivo corrompido ou sem checksum: restauração recusada")
            return 1
        proc = _compose_exec(PSQL, gzip.decompress(path.read_bytes()))
        print("restaurado" if proc.returncode == 0 else "psql falhou (nada foi confirmado como restaurado)")
        return proc.returncode
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
