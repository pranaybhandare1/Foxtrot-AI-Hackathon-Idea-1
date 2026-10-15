"""Oura connector: pagination, rate-limit handling, auth URL, incremental windows (no network)."""

import json
import urllib.parse
from datetime import date

import pytest
from t1d_core.settings import Config, Layers, load_config
from t1d_pipelines.sources.oura import landing
from t1d_pipelines.sources.oura.auth import authorize_url, read_env_file
from t1d_pipelines.sources.oura.client import OuraApiError, OuraClient


def fake_opener(responses):
    calls = []

    def opener(req):
        calls.append(req.full_url)
        status, headers, body = responses.pop(0)
        return status, headers, json.dumps(body).encode()

    return opener, calls


def test_paginates_and_honours_retry_after():
    opener, calls = fake_opener(
        [
            (200, {}, {"data": [{"id": "a"}], "next_token": "t2"}),
            (429, {"Retry-After": "7"}, {}),
            (200, {}, {"data": [{"id": "b"}], "next_token": None}),
        ]
    )
    slept = []
    client = OuraClient(lambda: "tok", opener=opener, sleep=slept.append)
    docs = list(client.paginate("/v2/usercollection/daily_sleep", {"start_date": "2026-01-01"}))
    assert [d["id"] for d in docs] == ["a", "b"]
    assert slept == [7.0]
    assert "next_token=t2" in calls[-1]


def test_client_raises_on_forbidden():
    opener, _ = fake_opener([(403, {}, {"detail": "scope"})])
    with pytest.raises(OuraApiError) as e:
        OuraClient(lambda: "tok", opener=opener).get("/v2/usercollection/workout")
    assert e.value.status == 403


def test_authorize_url_has_state_scopes_and_localhost_redirect():
    url = authorize_url(load_config(), "client-123", "STATE")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert q["state"] == "STATE" and q["response_type"] == "code"
    assert q["redirect_uri"].startswith("http://localhost:")
    assert "daily" in q["scope"].split()


def test_env_parser(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# c\nOURA_CLIENT_ID=abc\nOURA_CLIENT_SECRET='s3'\n\nBROKEN\n")
    assert read_env_file(p) == {"OURA_CLIENT_ID": "abc", "OURA_CLIENT_SECRET": "s3"}


class FakeClient:
    requests = 0

    def paginate(self, path, params):
        self.requests += 1
        return iter([{"id": path.rsplit("/", 1)[-1], **params}])

    def get(self, path, params=None):
        self.requests += 1
        return {"id": "info"}


def test_pull_writes_immutable_batch_and_next_pull_overlaps(tmp_path):
    real = load_config()
    cfg = Config(raw=real.raw, layers=Layers(tmp_path))
    m1 = landing.pull(cfg, client=FakeClient(), today=date(2026, 10, 14))
    assert m1["window"] == {"start": "2026-01-01", "end": "2026-10-15"}
    assert m1["counts"]["daily_sleep"] == 1 and m1["counts"]["heartrate"] > 1
    m2 = landing.pull(cfg, client=FakeClient(), today=date(2026, 10, 20))
    assert m2["window"]["start"] == "2026-10-12"  # previous end minus overlap_days (3)
