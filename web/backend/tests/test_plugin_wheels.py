"""Отбор wheel: удаление по реальному имени пакета и чистка старых версий."""
import pytest

from web.backend.core import plugin_installer as pi


@pytest.fixture
def plugins_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(pi.PLUGINS_DIR_ENV, str(tmp_path))
    return tmp_path


def _wheel(d, name):
    (d / name).write_bytes(b"x")
    return name


def test_wheels_of_plugin_matches_package_with_suffix(plugins_dir):
    """У smart_support дистрибутив — rwa_plugin_smart_support_tool.

    Удаление раньше искало точное «rwa-plugin-smart-support» и не находило
    ни одного файла, поэтому плагин не удалялся.
    """
    _wheel(plugins_dir, "rwa_plugin_smart_support_tool-1.1.0-py3-none-any.whl")
    _wheel(plugins_dir, "rwa_plugin_smart_support_tool-1.2.0-py3-none-any.whl")
    _wheel(plugins_dir, "rwa_plugin_block_radar-0.5.1-py3-none-any.whl")

    found = sorted(w.name for w in pi.wheels_of_plugin("smart_support"))
    assert found == [
        "rwa_plugin_smart_support_tool-1.1.0-py3-none-any.whl",
        "rwa_plugin_smart_support_tool-1.2.0-py3-none-any.whl",
    ]
    assert [w.name for w in pi.wheels_of_plugin("block_radar")] == [
        "rwa_plugin_block_radar-0.5.1-py3-none-any.whl"
    ]


def test_version_key_orders_numerically():
    """«0.10.0» новее «0.2.0» — как строки порядок обратный."""
    assert pi.version_key("0.10.0") > pi.version_key("0.2.0")
    assert pi.version_key("1.0.0") > pi.version_key("0.99.99")
    assert pi.version_key("0.5.1") > pi.version_key("0.5.0")


def test_drop_other_versions_keeps_only_current(plugins_dir):
    for v in ("0.2.0", "0.3.0", "0.4.0", "0.5.1"):
        _wheel(plugins_dir, f"rwa_plugin_block_radar-{v}-py3-none-any.whl")
    other = _wheel(plugins_dir, "rwa_plugin_smart_support_tool-1.2.0-py3-none-any.whl")

    dropped = pi.drop_other_versions(
        "rwa-plugin-block-radar", keep="rwa_plugin_block_radar-0.5.1-py3-none-any.whl"
    )

    assert len(dropped) == 3
    left = sorted(p.name for p in pi.list_wheel_files())
    assert left == ["rwa_plugin_block_radar-0.5.1-py3-none-any.whl", other]


def test_scan_installs_newest_not_last_alphabetically(plugins_dir, monkeypatch):
    """Из нескольких версий ставится новейшая, а не последняя по имени."""
    for v in ("0.2.0", "0.10.0"):
        _wheel(plugins_dir, f"rwa_plugin_block_radar-{v}-py3-none-any.whl")

    monkeypatch.setattr(pi, "is_distribution_installed", lambda *a, **k: False)
    calls = []
    monkeypatch.setattr(pi, "_pip_install", lambda wheel: calls.append(wheel.name))

    installed = pi.scan_and_install_wheels()

    assert calls == ["rwa_plugin_block_radar-0.10.0-py3-none-any.whl"]
    assert installed == ["rwa_plugin_block_radar-0.10.0-py3-none-any.whl"]
