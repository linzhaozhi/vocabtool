"""Tests for APKG download persistence across Streamlit session loss."""

import json
import os

from ui import helpers


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.query_params = {}
        self.downloads = []
        self.successes = []
        self.warnings = []
        self.errors = []

    def download_button(self, **kwargs):
        self.downloads.append(kwargs)
        return False

    def success(self, message):
        self.successes.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


def test_generated_package_recovers_after_session_state_is_lost(monkeypatch, tmp_path):
    fake_st = FakeStreamlit()
    recovery_dir = tmp_path / "recovery"
    monkeypatch.setattr(helpers, "st", fake_st)
    monkeypatch.setattr(helpers, "_apkg_recovery_dir", lambda: str(recovery_dir))

    source_path = tmp_path / "generated.apkg"
    source_path.write_bytes(b"valid-apkg-content")
    token = helpers.reserve_anki_download(
        path_key="import_anki_pkg_path",
        name_key="import_anki_pkg_name",
        section="4️⃣ 导入卡片",
    )
    helpers.set_anki_pkg(
        str(source_path),
        "测试牌组",
        path_key="import_anki_pkg_path",
        name_key="import_anki_pkg_name",
        recovery_token=token,
        section="4️⃣ 导入卡片",
    )

    stable_path = fake_st.session_state["import_anki_pkg_path"]
    assert os.path.isfile(stable_path)
    assert not source_path.exists()
    assert fake_st.query_params[helpers.constants.APKG_RECOVERY_QUERY_PARAM] == token

    fake_st.session_state = {}
    assert helpers.restore_anki_pkg_from_query() is True
    assert fake_st.session_state["import_anki_pkg_path"] == stable_path
    assert fake_st.session_state["import_anki_pkg_name"] == "测试牌组.apkg"

    helpers.render_active_anki_download()
    assert fake_st.successes == ["APKG 已生成，可直接下载。"]
    assert len(fake_st.downloads) == 1
    assert fake_st.downloads[0]["data"] == b"valid-apkg-content"
    assert fake_st.downloads[0]["file_name"] == "测试牌组.apkg"
    assert fake_st.downloads[0]["on_click"] == "ignore"
    assert fake_st.downloads[0]["key"] == "active_anki_download_button"


def test_recovery_rejects_expired_or_unsafe_metadata(monkeypatch, tmp_path):
    fake_st = FakeStreamlit()
    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir()
    monkeypatch.setattr(helpers, "st", fake_st)
    monkeypatch.setattr(helpers, "_apkg_recovery_dir", lambda: str(recovery_dir))

    token = "safe_token_123456"
    fake_st.query_params[helpers.constants.APKG_RECOVERY_QUERY_PARAM] = token
    metadata_path = recovery_dir / f"download_{token}.json"
    metadata_path.write_text(
        json.dumps({
            "file": "../../outside.apkg",
            "name": "bad.apkg",
            "path_key": "import_anki_pkg_path",
            "name_key": "import_anki_pkg_name",
            "created_at": 9999999999,
        }),
        encoding="utf-8",
    )

    assert helpers.restore_anki_pkg_from_query() is False
    assert fake_st.session_state == {}


def test_failed_generation_cancels_reserved_download_token(monkeypatch, tmp_path):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(helpers, "st", fake_st)
    monkeypatch.setattr(helpers, "_apkg_recovery_dir", lambda: str(tmp_path))

    token = helpers.reserve_anki_download(
        path_key="import_anki_pkg_path",
        name_key="import_anki_pkg_name",
        section="4️⃣ 导入卡片",
    )
    helpers.cancel_anki_download_reservation(
        token,
        path_key="import_anki_pkg_path",
    )

    assert helpers.constants.APKG_RECOVERY_QUERY_PARAM not in fake_st.query_params
    assert "import_anki_pkg_path_recovery_token" not in fake_st.session_state
    assert "active_anki_download_path_key" not in fake_st.session_state
