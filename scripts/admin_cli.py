#!/usr/bin/env python3
"""
CLI-утилита для управления администраторами Remnawave Admin Panel.

Позволяет сбросить пароль, создать нового суперадмина или вывести список
администраторов — напрямую через подключение к базе данных.

Использование:
    python3 scripts/admin_cli.py reset-password [--username USERNAME]
    python3 scripts/admin_cli.py create-superadmin --username USERNAME [--password PASSWORD]
    python3 scripts/admin_cli.py list-admins

Примеры:
    # Сбросить пароль для admin (будет сгенерирован новый)
    python3 scripts/admin_cli.py reset-password

    # Сбросить пароль с указанием имени пользователя
    python3 scripts/admin_cli.py reset-password --username myadmin

    # Сбросить пароль с указанием нового пароля
    python3 scripts/admin_cli.py reset-password --username admin --password 'MyNew$ecure1'

    # Создать нового суперадмина
    python3 scripts/admin_cli.py create-superadmin --username newadmin

    # Создать суперадмина с указанным паролем
    python3 scripts/admin_cli.py create-superadmin --username newadmin --password 'MyP@ssw0rd!'

    # Показать всех администраторов
    python3 scripts/admin_cli.py list-admins

Переменные окружения:
    DATABASE_URL  — строка подключения к PostgreSQL (читается из .env автоматически)

Из Docker:
    docker exec -it <container_name> python3 scripts/admin_cli.py reset-password
"""
import asyncio
import argparse
import os
import re
import secrets
import string
import sys
from pathlib import Path
from typing import Tuple

# ── Bootstrap project paths ──────────────────────────────────────
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# ── Load .env ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    load_dotenv(project_root / ".env")
except ImportError:
    pass  # dotenv is optional — DATABASE_URL can come from environment

# ── Dependency checks ────────────────────────────────────────────
try:
    import asyncpg
except ImportError:
    print("Ошибка: модуль 'asyncpg' не установлен")
    print(f"  pip3 install -r {project_root / 'requirements.txt'}")
    sys.exit(1)

try:
    import bcrypt as _bcrypt
except ImportError:
    print("Ошибка: модуль 'bcrypt' не установлен")
    print(f"  pip3 install -r {project_root / 'requirements.txt'}")
    sys.exit(1)


# ── Password helpers (self-contained, no heavy imports) ──────────
# Mirrors logic from web.backend.core.admin_credentials but avoids
# importing the full web.backend.core package (which pulls in jose,
# pydantic-settings, etc.).

MIN_PASSWORD_LENGTH = 8

_LOWER = "abcdefghjkmnpqrstuvwxyz"
_UPPER = "ABCDEFGHJKMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SPECIAL = "!@#$%^&*_+-="
_ALL_CHARS = _LOWER + _UPPER + _DIGITS + _SPECIAL


def validate_password_strength(password: str) -> Tuple[bool, str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r"[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`\"()]", password):
        return False, "Password must contain at least one special character"
    return True, ""


def generate_password(length: int = 20) -> str:
    chars = [
        secrets.choice(_LOWER),
        secrets.choice(_UPPER),
        secrets.choice(_DIGITS),
        secrets.choice(_SPECIAL),
    ]
    for _ in range(length - 4):
        chars.append(secrets.choice(_ALL_CHARS))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(
        password.encode("utf-8"), _bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

# ── Colours (optional, disabled when piped) ──────────────────────
_USE_COLOR = sys.stdout.isatty()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _USE_COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _USE_COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _USE_COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _USE_COLOR else text


# ── Database helpers ─────────────────────────────────────────────

def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(_red("Ошибка: DATABASE_URL не задан."))
        print("Укажите через переменную окружения или в файле .env")
        sys.exit(1)
    return url


async def _connect() -> asyncpg.Connection:
    url = _get_database_url()
    try:
        return await asyncpg.connect(url)
    except Exception as e:
        print(_red(f"Не удалось подключиться к базе данных: {e}"))
        sys.exit(1)


async def _get_superadmin_role_id(conn: asyncpg.Connection) -> int:
    """Return the 'superadmin' role ID, or exit with error."""
    row = await conn.fetchrow(
        "SELECT id FROM admin_roles WHERE name = 'superadmin'"
    )
    if not row:
        print(_red("Ошибка: роль 'superadmin' не найдена в admin_roles."))
        print("Убедитесь, что миграции RBAC (0009) были применены.")
        sys.exit(1)
    return row["id"]


# ── Commands ─────────────────────────────────────────────────────

async def cmd_reset_password(args: argparse.Namespace) -> None:
    """Reset password for an existing admin account."""
    username = args.username
    conn = await _connect()

    try:
        # Try admin_accounts (RBAC) first
        account = await conn.fetchrow(
            "SELECT id, username, is_active FROM admin_accounts "
            "WHERE LOWER(username) = LOWER($1)",
            username,
        )

        # Fallback to legacy admin_credentials
        legacy = None
        if not account:
            legacy = await conn.fetchrow(
                "SELECT id, username FROM admin_credentials "
                "WHERE LOWER(username) = LOWER($1)",
                username,
            )

        if not account and not legacy:
            print(_red(f"Администратор '{username}' не найден."))
            print()
            # Show available admins
            rows = await conn.fetch(
                "SELECT username, is_active FROM admin_accounts ORDER BY id"
            )
            if rows:
                print("Доступные аккаунты:")
                for r in rows:
                    status = _green("активен") if r["is_active"] else _red("отключён")
                    print(f"  - {r['username']} ({status})")
            sys.exit(1)

        # Generate or use provided password
        if args.password:
            password = args.password
            is_valid, err = validate_password_strength(password)
            if not is_valid:
                print(_red(f"Пароль не соответствует требованиям: {err}"))
                print()
                print("Требования к паролю:")
                print("  - Минимум 8 символов")
                print("  - Хотя бы одна заглавная буква")
                print("  - Хотя бы одна строчная буква")
                print("  - Хотя бы одна цифра")
                print("  - Хотя бы один спецсимвол (!@#$%^&*_+-=)")
                sys.exit(1)
            generated = False
        else:
            password = generate_password()
            generated = True

        pw_hash = hash_password(password)
        actual_username = (account or legacy)["username"]

        # Update in admin_accounts
        if account:
            await conn.execute(
                "UPDATE admin_accounts SET password_hash = $1, "
                "is_generated_password = $2, updated_at = NOW() "
                "WHERE id = $3",
                pw_hash,
                generated,
                account["id"],
            )

        # Update in legacy admin_credentials too (for backward compatibility)
        if legacy or account:
            await conn.execute(
                "UPDATE admin_credentials SET password_hash = $1, "
                "is_generated = $2, updated_at = NOW() "
                "WHERE LOWER(username) = LOWER($3)",
                pw_hash,
                generated,
                username,
            )

        print()
        print(_green("=" * 55))
        print(_green(f"  Пароль для '{actual_username}' успешно сброшен!"))
        print(_green("=" * 55))
        print()
        print(f"  Логин:   {_bold(actual_username)}")
        print(f"  Пароль:  {_bold(password)}")
        print()
        if generated:
            print(_yellow("  Рекомендуется сменить пароль после входа в панель."))
            print()

    finally:
        await conn.close()


async def cmd_create_superadmin(args: argparse.Namespace) -> None:
    """Create a new superadmin account."""
    username = args.username
    conn = await _connect()

    try:
        # Check if username already exists
        existing = await conn.fetchrow(
            "SELECT id FROM admin_accounts WHERE LOWER(username) = LOWER($1)",
            username,
        )
        if existing:
            print(_red(f"Администратор '{username}' уже существует."))
            print("Используйте 'reset-password' для сброса пароля.")
            sys.exit(1)

        # Get superadmin role
        role_id = await _get_superadmin_role_id(conn)

        # Generate or use provided password
        if args.password:
            password = args.password
            is_valid, err = validate_password_strength(password)
            if not is_valid:
                print(_red(f"Пароль не соответствует требованиям: {err}"))
                print()
                print("Требования к паролю:")
                print("  - Минимум 8 символов")
                print("  - Хотя бы одна заглавная буква")
                print("  - Хотя бы одна строчная буква")
                print("  - Хотя бы одна цифра")
                print("  - Хотя бы один спецсимвол (!@#$%^&*_+-=)")
                sys.exit(1)
            generated = False
        else:
            password = generate_password()
            generated = True

        pw_hash = hash_password(password)

        # Insert into admin_accounts
        await conn.execute(
            """
            INSERT INTO admin_accounts
                (username, password_hash, role_id, is_active, is_generated_password)
            VALUES ($1, $2, $3, true, $4)
            """,
            username,
            pw_hash,
            role_id,
            generated,
        )

        # Also insert into legacy admin_credentials for backward compatibility
        await conn.execute(
            """
            INSERT INTO admin_credentials (username, password_hash, is_generated)
            VALUES ($1, $2, $3)
            ON CONFLICT (username) DO UPDATE
                SET password_hash = $2, is_generated = $3, updated_at = NOW()
            """,
            username,
            pw_hash,
            generated,
        )

        print()
        print(_green("=" * 55))
        print(_green(f"  Суперадмин '{username}' успешно создан!"))
        print(_green("=" * 55))
        print()
        print(f"  Логин:   {_bold(username)}")
        print(f"  Пароль:  {_bold(password)}")
        print(f"  Роль:    superadmin")
        print()
        if generated:
            print(_yellow("  Рекомендуется сменить пароль после входа в панель."))
            print()

    finally:
        await conn.close()


async def cmd_list_admins(_args: argparse.Namespace) -> None:
    """List all admin accounts."""
    conn = await _connect()

    try:
        rows = await conn.fetch(
            """
            SELECT
                a.id,
                a.username,
                a.telegram_id,
                r.name as role_name,
                r.display_name as role_display,
                a.is_active,
                a.is_generated_password,
                a.created_at
            FROM admin_accounts a
            LEFT JOIN admin_roles r ON r.id = a.role_id
            ORDER BY a.id
            """
        )

        if not rows:
            print(_yellow("Администраторов не найдено в admin_accounts."))
            print()
            # Check legacy table
            legacy = await conn.fetch(
                "SELECT id, username, is_generated FROM admin_credentials ORDER BY id"
            )
            if legacy:
                print("Найдены записи в legacy-таблице admin_credentials:")
                for r in legacy:
                    gen = " (auto-generated password)" if r["is_generated"] else ""
                    print(f"  - {r['username']}{gen}")
            return

        print()
        print(_bold(f"  Администраторы ({len(rows)}):"))
        print("  " + "-" * 70)
        print(
            f"  {'ID':<5} {'Username':<20} {'Role':<15} {'TG ID':<15} "
            f"{'Status':<10} {'Gen.pwd'}"
        )
        print("  " + "-" * 70)

        for r in rows:
            status = _green("active") if r["is_active"] else _red("disabled")
            gen_pwd = _yellow("yes") if r["is_generated_password"] else "no"
            tg_id = str(r["telegram_id"]) if r["telegram_id"] else "-"
            role = r["role_name"] or "-"
            print(
                f"  {r['id']:<5} {r['username']:<20} {role:<15} {tg_id:<15} "
                f"{status:<10} {gen_pwd}"
            )

        print("  " + "-" * 70)
        print()

    finally:
        await conn.close()


# ── Entrypoint ───────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remnawave Admin CLI — управление администраторами",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s reset-password                        # Сбросить пароль для 'admin'
  %(prog)s reset-password --username myuser      # Сбросить пароль для 'myuser'
  %(prog)s create-superadmin --username newadmin  # Создать суперадмина
  %(prog)s list-admins                            # Список всех админов

Из Docker:
  docker exec -it <container> python3 scripts/admin_cli.py reset-password
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    # reset-password
    rp = subparsers.add_parser(
        "reset-password",
        help="Сбросить пароль существующего администратора",
    )
    rp.add_argument(
        "--username",
        default="admin",
        help="Имя администратора (по умолчанию: admin)",
    )
    rp.add_argument(
        "--password",
        default=None,
        help="Новый пароль (если не указан — будет сгенерирован автоматически)",
    )

    # create-superadmin
    cs = subparsers.add_parser(
        "create-superadmin",
        help="Создать нового суперадмина",
    )
    cs.add_argument(
        "--username",
        required=True,
        help="Имя нового администратора",
    )
    cs.add_argument(
        "--password",
        default=None,
        help="Пароль (если не указан — будет сгенерирован автоматически)",
    )

    # list-admins
    subparsers.add_parser(
        "list-admins",
        help="Показать всех администраторов",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Dispatch
    commands = {
        "reset-password": cmd_reset_password,
        "create-superadmin": cmd_create_superadmin,
        "list-admins": cmd_list_admins,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
