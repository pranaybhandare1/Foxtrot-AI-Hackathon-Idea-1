"""Command line entry point: `uv run t1d <command>`."""

from __future__ import annotations

import argparse
import json
import time

from t1d_core.settings import load_config

LAYERS = ["landing", "raw", "transformed", "clean", "ontology", "quality"]


def _has_oura(cfg) -> bool:
    return any((cfg.layers.landing / "oura").glob("pull_*/_manifest.json"))


def _run_layer(name: str, cfg) -> dict:
    """One medallion step across every source. Order matters: Oura is transformed before CareLink
    (its observed time zones correct pump-clock local time) and cleaned after it (its objects link to Day)."""
    from t1d_pipelines.sources.carelink import landing as cl_landing
    from t1d_pipelines.sources.carelink import raw as cl_raw
    from t1d_pipelines.sources.carelink import transformed as cl_transformed
    from t1d_pipelines.sources.carelink.clean import build as cl_clean
    from t1d_pipelines.sources.oura import clean as oura_clean
    from t1d_pipelines.sources.oura import raw as oura_raw
    from t1d_pipelines.sources.oura import transformed as oura_transformed

    oura = _has_oura(cfg)
    if name == "landing":
        return {"carelink": cl_landing.land(cfg)["status"], "oura": "pulled separately (make oura-pull)"}
    if name == "raw":
        return {"carelink": cl_raw.build(cfg)} | ({"oura": oura_raw.build(cfg)} if oura else {})
    if name == "transformed":
        out = {"oura": oura_transformed.build(cfg)} if oura else {}
        return out | {"carelink": cl_transformed.build(cfg)}
    if name == "clean":
        return {"carelink": cl_clean(cfg), "oura": oura_clean.build(cfg)}
    if name == "ontology":
        from t1d_ontology import publish

        return publish.build(cfg)
    if name == "quality":
        from t1d_pipelines.quality import checks

        return checks.run(cfg)
    raise ValueError(name)


def main() -> None:
    parser = argparse.ArgumentParser(prog="t1d", description="T1D decision-support data pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run pipeline layers in order")
    run.add_argument("--from", dest="start", choices=LAYERS, default=LAYERS[0])
    run.add_argument("--to", dest="end", choices=LAYERS, default=LAYERS[-1])
    oura = sub.add_parser("oura", help="Oura ring: connect (one-time OAuth consent) or pull raw data")
    oura.add_argument("action", choices=["connect", "pull", "status"])
    oura.add_argument("--since", help="pull from this date (YYYY-MM-DD) instead of the incremental default")
    args = parser.parse_args()

    cfg = load_config()
    if args.command == "run":
        layers = LAYERS[LAYERS.index(args.start) : LAYERS.index(args.end) + 1]
        for name in layers:
            started = time.perf_counter()
            result = _run_layer(name, cfg)
            print(f"[{name}] {time.perf_counter() - started:.1f}s {json.dumps(result, default=str)[:600]}")
            if name == "quality" and result.get("failed"):
                raise SystemExit(1)
    elif args.command == "oura":
        _oura(args, cfg)


def _oura(args, cfg) -> None:
    from datetime import date

    from t1d_pipelines.sources.oura import auth, landing

    if args.action == "connect":
        print(json.dumps(auth.connect(cfg)))
    elif args.action == "pull":
        since = date.fromisoformat(args.since) if args.since else None
        manifest = landing.pull(cfg, since=since)
        print(json.dumps({k: manifest[k] for k in ("pull_id", "window", "requests", "counts", "skipped")}, indent=2))
    else:
        pulls = landing.previous_pulls(cfg)
        print(
            json.dumps(
                {
                    "connected": auth.token_path(cfg).exists(),
                    "pulls": [
                        {"pull_id": p["pull_id"], "window": p["window"], "documents": sum(p["counts"].values())}
                        for p in pulls
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
