"""Resumable downloads, tested against a local server that drops the connection mid-file."""
import http.server
import threading

import h5py
import numpy as np
import requests

import fetch


class Result:
    def __init__(self, url, name, size, scene="NISAR_X_001"):
        self.properties = {"url": url, "fileName": name, "sceneName": scene, "bytes": {name: {"bytes": size}}}


def serve(payload, drop_first_at):
    state = {"calls": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            state["calls"] += 1
            start = int(self.headers["Range"].split("=")[1].split("-")[0]) if self.headers.get("Range") else 0
            body = payload[start:]
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if state["calls"] == 1:                       # first request: cut the connection partway
                self.wfile.write(body[:drop_first_at])
                self.wfile.flush()
                self.connection.close()
                return
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def make_h5(path):
    with h5py.File(path, "w") as f:
        f["data"] = np.arange(200_000, dtype="float32")
    return path.read_bytes()


def test_download_resumes_after_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    payload = make_h5(tmp_path / "src.h5")
    server, state = serve(payload, drop_first_at=len(payload) // 3)
    url = f"http://127.0.0.1:{server.server_address[1]}/p.h5"
    out = fetch.download(Result(url, "p.h5", len(payload)), tmp_path / "dl", requests.Session())
    server.shutdown()
    assert out.read_bytes() == payload and state["calls"] >= 2
    assert not (tmp_path / "dl" / "p.h5.part").exists()


def test_truncated_file_from_old_download_is_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    payload = make_h5(tmp_path / "src.h5")
    (tmp_path / "dl").mkdir()
    (tmp_path / "dl" / "p.h5").write_bytes(payload[: len(payload) // 2])   # what asf_search left behind
    assert fetch.usable_h5([tmp_path / "dl" / "p.h5"]) == []
    server, state = serve(payload, drop_first_at=10**9)
    url = f"http://127.0.0.1:{server.server_address[1]}/p.h5"
    out = fetch.download(Result(url, "p.h5", len(payload)), tmp_path / "dl", requests.Session())
    server.shutdown()
    assert out.read_bytes() == payload
    assert fetch.usable_h5([out]) == [out]


def test_newest_versions_only(tmp_path):
    a1 = Result("u", "a1", 1, "NISAR_GCOV_A_20260904_001")
    a2 = Result("u", "a2", 1, "NISAR_GCOV_A_20260904_002")
    b1 = Result("u", "b1", 1, "NISAR_GCOV_A_20260916_001")
    assert fetch.latest_versions([a1, a2, b1]) == [a2, b1]
    for name in ("X_20260904_001.h5", "X_20260904_002.h5"):
        make_h5(tmp_path / name)
    assert [p.name for p in fetch.usable_h5(sorted(tmp_path.glob("X_*.h5")))] == ["X_20260904_002.h5"]


def test_one_track_keeps_the_majority(tmp_path):
    names = ["NISAR_L2_PR_GUNW_022_162_A_007_023_4000_SH_20260613T1_P.h5",
             "NISAR_L2_PR_GUNW_022_162_A_006_023_4000_SH_20260613T1_P.h5",
             "NISAR_L2_PR_GUNW_026_061_A_007_028_4000_SH_20260724T0_P.h5",
             "SYNTHETIC_demo_pair.h5"]
    kept = [p.name for p in fetch.one_track([tmp_path / n for n in names])]
    assert kept == [names[0], names[1], names[3]]
