"""เทสต์ตัวแทนเครื่อง — เน้นเรื่องกุญแจที่ต้องใช้ซ้ำได้ เพราะเป็นหัวใจของการใช้บนคอมตัวเอง."""

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

AGENT_PATH = Path(__file__).resolve().parent.parent / "agent" / "spice_agent.py"


@pytest.fixture()
def agent(tmp_path, monkeypatch):
    """โหลดตัวแทนเครื่องมาแบบสด ๆ โดยชี้ที่เก็บกุญแจไปยังโฟลเดอร์ชั่วคราว."""
    spec = importlib.util.spec_from_file_location("spice_agent_under_test", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "CONFIG_DIR", str(tmp_path / ".spice"))
    monkeypatch.setattr(module, "CONFIG_PATH", str(tmp_path / ".spice" / "config.json"))
    monkeypatch.setattr(module, "log", lambda *args, **kwargs: None)
    yield module
    sys.modules.pop(spec.name, None)


class FakeClient:
    """ไคลเอนต์ปลอมที่จดไว้ว่าถูกเรียกทำอะไรบ้าง."""

    instances: list = []

    def __init__(self, server, token="", worker_id=""):
        self.server = server
        self.token = token
        self.worker_id = worker_id
        self.registered_with = None
        self.heartbeats = 0
        self.heartbeat_error = None
        FakeClient.instances.append(self)

    def register(self, pair_code, name):
        self.registered_with = (pair_code, name)
        self.token = "spk_brand-new-token"
        self.worker_id = "wk_newly_paired"
        return {"owner_email": "owner@spice.local"}

    def heartbeat(self, status, drive_mounted):
        self.heartbeats += 1
        if self.heartbeat_error:
            raise RuntimeError(self.heartbeat_error)
        return {"ok": True}


def make_args(**overrides):
    defaults = {"server": "", "pair": "", "name": "", "no_drive": True, "reset": False}
    return argparse.Namespace(**{**defaults, **overrides})


@pytest.fixture(autouse=True)
def clear_instances():
    FakeClient.instances = []


# ── เก็บกุญแจไว้ใช้ซ้ำ ───────────────────────────────────────
def test_first_pairing_saves_the_key(agent):
    client, _ = agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)

    assert client.registered_with[0] == "ABCD-1234"
    saved = agent.load_config()
    assert saved["worker_token"] == "spk_brand-new-token"
    assert saved["worker_id"] == "wk_newly_paired"
    assert saved["server"] == "https://spice.example.com"
    assert saved["owner"] == "owner@spice.local"


def test_second_run_needs_no_pair_code_and_no_server(agent):
    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)
    FakeClient.instances = []

    # รันเปล่า ๆ เหมือนตอนเปิดเครื่องใหม่
    client, settings = agent.resolve_credentials(make_args(), FakeClient)

    assert client.token == "spk_brand-new-token"
    assert client.registered_with is None        # ต้องไม่ไปจับคู่ใหม่
    assert client.heartbeats == 1                # แต่ต้องเช็กก่อนว่ากุญแจยังใช้ได้
    assert settings["server"] == "https://spice.example.com"


def test_key_file_is_not_readable_by_other_users(agent):
    import os
    import stat

    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)
    mode = stat.S_IMODE(os.stat(agent.CONFIG_PATH).st_mode)
    assert mode == 0o600


def test_revoked_key_is_thrown_away_with_a_clear_message(agent):
    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)

    def rejecting_factory(server, token="", worker_id=""):
        client = FakeClient(server, token, worker_id)
        client.heartbeat_error = "worker/heartbeat → 401: token ถูกเพิกถอน"
        return client

    with pytest.raises(SystemExit) as caught:
        agent.resolve_credentials(make_args(), rejecting_factory)

    assert "ยังไม่เคยจับคู่" in str(caught.value)
    assert agent.load_config() == {}              # กุญแจที่ใช้ไม่ได้ต้องถูกลบทิ้ง


def test_a_network_blip_does_not_delete_a_good_key(agent):
    """เน็ตหลุดชั่วคราวต้องไม่ทำให้ต้องไปจับคู่ใหม่ทั้งเครื่อง."""
    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)

    def flaky_factory(server, token="", worker_id=""):
        client = FakeClient(server, token, worker_id)
        client.heartbeat_error = "Connection refused"
        return client

    with pytest.raises(RuntimeError):
        agent.resolve_credentials(make_args(), flaky_factory)

    assert agent.load_config()["worker_token"] == "spk_brand-new-token"


def test_pointing_at_a_different_server_pairs_again(agent):
    agent.resolve_credentials(
        make_args(server="https://old.example.com", pair="ABCD-1234"), FakeClient)
    client, _ = agent.resolve_credentials(
        make_args(server="https://new.example.com", pair="WXYZ-5678"), FakeClient)

    assert client.registered_with[0] == "WXYZ-5678"
    assert agent.load_config()["server"] == "https://new.example.com"


def test_explicit_pair_code_overrides_a_stored_key(agent):
    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234"), FakeClient)
    client, _ = agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="NEWW-9999"), FakeClient)
    assert client.registered_with[0] == "NEWW-9999"


def test_running_with_nothing_at_all_explains_what_to_do(agent):
    with pytest.raises(SystemExit) as caught:
        agent.resolve_credentials(make_args(), FakeClient)
    assert "--server" in str(caught.value)


def test_machine_name_is_remembered(agent):
    agent.resolve_credentials(
        make_args(server="https://spice.example.com", pair="ABCD-1234",
                  name="คอมห้องนอน"), FakeClient)
    assert agent.load_config()["name"] == "คอมห้องนอน"
    _, settings = agent.resolve_credentials(make_args(), FakeClient)
    assert settings["name"] == "คอมห้องนอน"


# ── รู้จักเครื่องที่มันรันอยู่ ────────────────────────────────
def test_detects_what_hardware_it_has(agent):
    assert agent.detect_device() in {"cuda", "mps", "cpu"}


def test_reports_something_usable_even_without_a_gpu(agent):
    info = agent.gpu_info()
    assert info["gpu_name"]                      # ต้องมีชื่อเสมอ ไม่ปล่อยว่าง
    assert "python" in info["runtime"]
    assert set(info) >= {"gpu_name", "gpu_vram_mb", "gpu_used_mb", "gpu_util", "driver"}


def test_only_claims_work_it_can_actually_do(agent, monkeypatch):
    monkeypatch.setattr(agent, "detect_device", lambda: "cpu")
    monkeypatch.setattr(agent, "gpu_info", lambda: {"gpu_vram_mb": 64000})
    assert agent.capabilities() == ["text", "embedding"]    # CPU ไม่รับงานภาพ

    monkeypatch.setattr(agent, "detect_device", lambda: "cuda")
    monkeypatch.setattr(agent, "gpu_info", lambda: {"gpu_vram_mb": 15360})
    assert set(agent.capabilities()) == {"text", "embedding", "image", "audio"}

    monkeypatch.setattr(agent, "gpu_info", lambda: {"gpu_vram_mb": 6000})
    caps = agent.capabilities()
    assert "audio" in caps and "image" not in caps          # การ์ดเล็ก ถอดเสียงไหว แต่วาดภาพไม่ไหว


def test_warm_model_list_stays_bounded(agent):
    for index in range(20):
        agent.mark_warm(f"model-{index}")
    assert len(agent._warm_models) == agent.MAX_WARM
    assert agent._warm_models[-1] == "model-19"     # ตัวที่ใช้ล่าสุดอยู่ท้ายเสมอ


def test_using_a_model_again_moves_it_to_the_front(agent):
    agent.mark_warm("alpha")
    agent.mark_warm("beta")
    agent.mark_warm("alpha")
    assert agent._warm_models == ["beta", "alpha"]
