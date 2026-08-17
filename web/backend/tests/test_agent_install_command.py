"""Команда установки агента: её копируют в консоль ноды как есть.

Живой случай из чата: GitHub ответил на скачивание установщика 429, и при
`curl … | bash` телом ответа стал текст ошибки, который bash попытался
выполнить — оператор увидел «429:: command not found» и решил, что сломан
сам агент. Отсюда два требования к команде: не лить скачанное прямо в
интерпретатор и падать на HTTP-ошибке, а не продолжать с мусором.
"""
from web.backend.api.v2.nodes import build_agent_install_command

COMMAND = build_agent_install_command(
    node_uuid="fd3a2983-4f68-45eb-8652-7557d7e15f7a",
    base_url="https://admin.example.com",
    token="agent-token",
    ws_secret="ws-secret",
)


def test_script_is_not_piped_into_shell():
    assert "| bash" not in COMMAND
    assert "|bash" not in COMMAND


def test_http_error_stops_the_install():
    # -f заставляет curl вернуть ошибку вместо тела ответа, && не пускает
    # запуск дальше, если скачивание не удалось.
    assert "-fsSL" in COMMAND
    assert "&&" in COMMAND


def test_transient_rate_limit_is_retried():
    assert "--retry 3" in COMMAND


def test_all_parameters_reach_the_installer():
    installer = COMMAND.split("&&", 1)[1]
    assert "--uuid fd3a2983-4f68-45eb-8652-7557d7e15f7a" in installer
    assert "--url https://admin.example.com" in installer
    assert "--token agent-token" in installer
    assert "--ws-secret ws-secret" in installer


def test_command_stays_single_line():
    """Панель отдаёт её одной строкой для копирования — перенос сломал бы вставку."""
    assert "\n" not in COMMAND
