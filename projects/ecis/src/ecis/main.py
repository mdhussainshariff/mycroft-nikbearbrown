from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ecis")


def cmd_init_db() -> None:
    """Initialise all SQLite databases."""
    from ecis.db.init_db import init_all, insert_default_weights

    print("Initialising ECIS databases…")
    init_all()
    insert_default_weights()
    print("Done.")


def cmd_ingest(tickers: list[str], source: str) -> None:
    """Fetch transcripts for given tickers."""
    from ecis.config.settings import settings

    settings.ensure_dirs()

    if source in ("edgar", "both"):
        from ecis.ingestion.edgar_fetcher import fetch_transcripts as fetch_edgar

        paths = fetch_edgar(tickers)
        print(f"EDGAR: downloaded {len(paths)} files")

    if source in ("fmp", "both"):
        from ecis.ingestion.fmp_fetcher import fetch_transcripts as fetch_fmp

        paths = fetch_fmp(tickers)
        print(f"FMP: downloaded {len(paths)} files")

    from ecis.db.ticker_registry import refresh_transcript_counts, upsert_ticker

    for t in tickers:
        upsert_ticker(t)
        refresh_transcript_counts(t)


def cmd_preprocess(tickers: list[str]) -> None:
    """Clean, normalise, chunk, and embed transcripts."""
    from ecis.preprocessing.cleaner import clean_all
    from ecis.preprocessing.normaliser import normalise_all
    from ecis.preprocessing.chunker import chunk_all
    from ecis.embedding.embedder import embed_and_store_from_file

    for ticker in tickers:
        print(f"\nProcessing {ticker}")
        cleaned = clean_all(ticker)
        print(f"  Cleaned: {len(cleaned)} files")

        normalised = normalise_all(ticker)
        print(f"  Normalised: {len(normalised)} files")

        chunk_files = chunk_all(ticker)
        print(f"  Chunked: {len(chunk_files)} files")

        total_embedded = 0
        for cf in chunk_files:
            n = embed_and_store_from_file(cf)
            total_embedded += n
        print(f"  Embedded: {total_embedded} chunks")


def cmd_extract(ticker: str, transcript_path: str, llm_model: str | None = None, force: bool = False) -> None:
    """Run the full extraction pipeline on a single transcript."""
    from ecis.graphs.pipeline_graph import run_pipeline

    print(f"Running extraction pipeline for {ticker} on {transcript_path}…")
    if llm_model:
        print(f"  LLM: {llm_model}")
    signals = run_pipeline(ticker, transcript_path, llm_model=llm_model, force=force)
    print(f"\nExtracted {len(signals)} signals:")
    for s in signals:
        model_tag = f" [{s.llm_model}]" if s.llm_model else ""
        print(
            f"  [{s.direction.value:>10}] conf={s.confidence_raw:.2f} "
            f"chunk={s.chunk_index}{model_tag} | {s.supporting_quote[:80]}…"
        )


def cmd_extract_all(tickers: list[str], llm_models: list[str] | None = None, force: bool = False) -> None:
    """Run extraction on all raw files for given tickers."""
    from ecis.config.settings import settings
    from ecis.db.crash_recovery import is_complete, log_resume_skip
    from ecis.db.ticker_registry import list_ticker_symbols, mark_extraction, upsert_ticker
    from ecis.graphs.pipeline_graph import run_pipeline

    if not tickers:
        tickers = list_ticker_symbols()
        if not tickers:
            print("No tickers in registry. Run --migrate-tickers or pass --ticker.")
            return

    models = llm_models or [settings.llm_model]
    total_signals = 0
    for ticker in tickers:
        upsert_ticker(ticker)
        raw_dirs = [settings.raw_edgar_dir / ticker, settings.raw_fmp_dir / ticker]
        files = []
        for raw_dir in raw_dirs:
            if raw_dir.exists():
                files.extend(sorted(f for f in raw_dir.iterdir() if f.is_file()))
        if not files:
            print(f"No raw files for {ticker}, skipping")
            mark_extraction(ticker, "no_files")
            continue

        print(f"\n{'='*60}")
        print(f"Extracting {ticker}: {len(files)} files × {len(models)} model(s)")
        print(f"{'='*60}")

        ticker_signals = 0
        for model in models:
            for i, raw_file in enumerate(files, 1):
                if not force and is_complete(ticker, str(raw_file), model):
                    log_resume_skip(ticker, str(raw_file), model)
                    print(f"\n  [{i}/{len(files)}] {raw_file.name}  ({model}) — resume skip")
                    continue
                print(f"\n  [{i}/{len(files)}] {raw_file.name}  ({model})")
                try:
                    signals = run_pipeline(ticker, str(raw_file), llm_model=model, force=force)
                    ticker_signals += len(signals)
                    print(f"    → {len(signals)} signals")
                except Exception as exc:
                    print(f"    → ERROR: {exc}")

        mark_extraction(ticker, "complete")
        print(f"\n  {ticker} total: {ticker_signals} signals")
        total_signals += ticker_signals

    print(f"\n{'='*60}")
    print(f"Grand total: {total_signals} signals across {len(tickers)} tickers")
    print(f"{'='*60}")
    try:
        from ecis.extraction.health import record_reader_health

        for rec in record_reader_health():
            if rec.get("alert"):
                print(f"  HEALTH {rec['alert']}")
    except Exception:
        pass


def cmd_batch(tickers: list[str], llm_models: list[str] | None = None, force: bool = False) -> None:
    """Run the full pipeline: ingest → preprocess → extract for all tickers."""
    from ecis.db.init_db import init_all, insert_default_weights
    from ecis.db.ticker_registry import refresh_transcript_counts, upsert_ticker

    init_all()
    insert_default_weights()

    cmd_ingest(tickers, source="both")
    for t in tickers:
        upsert_ticker(t)
        refresh_transcript_counts(t)
    cmd_preprocess(tickers)
    cmd_extract_all(tickers, llm_models=llm_models, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ECIS — Earnings Call Intelligence Signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--init-db", action="store_true", help="Initialise databases")
    parser.add_argument("--ticker", type=str, help="Company ticker symbol(s), comma-separated")
    parser.add_argument("--file", type=str, help="Path to a specific transcript file")
    parser.add_argument("--ingest", action="store_true", help="Fetch transcripts from EDGAR/FMP")
    parser.add_argument("--preprocess", action="store_true", help="Clean, normalise, chunk, embed")
    parser.add_argument("--extract", action="store_true", help="Run extraction pipeline")
    parser.add_argument("--batch", action="store_true", help="Full pipeline: ingest → preprocess → extract")
    parser.add_argument("--source", choices=["edgar", "fmp", "both"], default="both",
                        help="Data source for ingestion (default: both)")
    parser.add_argument("--resolve-outcomes", action="store_true",
                        help="Resolve market outcomes for extracted signals")
    parser.add_argument("--score", action="store_true", help="Print scoring report")
    parser.add_argument("--recalibrate", choices=["platt", "isotonic"],
                        help="Recalibrate signal confidences")
    parser.add_argument("--watchdog", action="store_true",
                        help="Run calibration watchdog for all readers")
    parser.add_argument("--learn", action="store_true",
                        help="Run orchestration learning graph (tune escalation thresholds)")
    parser.add_argument("--vindicate", action="store_true",
                        help="Aggregate conflict vindications and update reader weights")
    parser.add_argument("--link-trends", action="store_true",
                        help="Write retrospective trend labels onto logged signals")
    parser.add_argument("--link-decay", action="store_true",
                        help="Write 30/90/180 decay profiles onto logged signals")
    parser.add_argument("--export-qlora", type=str, metavar="PATH",
                        help="Export signal triples as QLoRA JSONL")
    parser.add_argument("--migrate-tickers", action="store_true",
                        help="Populate ticker registry from existing directories")
    parser.add_argument("--list-tickers", action="store_true",
                        help="Print the ticker registry")
    parser.add_argument("--approve", type=int, metavar="ID",
                        help="Approve a pending HITL proposal by id")
    parser.add_argument("--reject", type=int, metavar="ID",
                        help="Reject a pending HITL proposal by id")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM for extraction: llama, mistral, qwen, finetuned, both, all, or an Ollama tag")
    parser.add_argument("--force-extract", action="store_true",
                        help="Re-run extraction even if this file/model already completed")
    parser.add_argument("--force-resolve", action="store_true",
                        help="Re-fetch outcomes even if cached (splits / corrected dates)")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard")
    parser.add_argument("--api", action="store_true", help="Launch FastAPI server")
    parser.add_argument("--horizon", type=int, choices=[30, 90, 180],
                        help="Evaluation horizon in days (for --score)")
    parser.add_argument("--predict", action="store_true",
                        help="Train guidance forecast models and log predictions")
    parser.add_argument("--score-predictions", action="store_true",
                        help="Grade logged predictions against extracted guidance")
    parser.add_argument("--correlate", action="store_true",
                        help="Refresh cross-ticker guidance correlations")
    parser.add_argument("--link-linguistics", action="store_true",
                        help="Write readability / hedging / FLS / tone-shift onto signals")
    parser.add_argument("--link-surprise", action="store_true",
                        help="Write consensus surprise scores onto signals")
    parser.add_argument("--reader-health", action="store_true",
                        help="Compute per-reader health and alerts")
    parser.add_argument("--refresh-views", action="store_true",
                        help="Refresh dashboard aggregation views")
    parser.add_argument("--profile-data", action="store_true",
                        help="Write numerical / categorical data profiles")
    parser.add_argument("--lineage", action="store_true",
                        help="Backfill JSON lineage onto signals missing it")
    parser.add_argument("--completeness", action="store_true",
                        help="Per-ticker consensus / price / Chroma / outcome gaps")
    parser.add_argument("--audit-queries", action="store_true",
                        help="Time dashboard SQL and log slow queries")
    parser.add_argument("--cleanup-exemplars", action="store_true",
                        help="Deduplicate and rebalance the few-shot store")
    parser.add_argument("--evaluate", action="store_true",
                        help="Bootstrap CIs, model permutation tests, power analysis")
    parser.add_argument("--drift", action="store_true",
                        help="PSI / KL concept-drift check")
    parser.add_argument("--watch-predictions", action="store_true",
                        help="Prediction-layer decay watchdog")

    args = parser.parse_args()

    if args.init_db:
        cmd_init_db()
        return

    if args.dashboard:
        import subprocess
        import sys
        dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)])
        return

    if args.api:
        import uvicorn
        uvicorn.run("ecis.api.app:app", host="0.0.0.0", port=8000, reload=True)
        return

    tickers = [t.strip().upper() for t in args.ticker.split(",")] if args.ticker else []
    from ecis.config.settings import settings as _settings
    llm_models = _settings.resolve_llm_models(args.model) if args.model else None
    if args.model and llm_models:
        from ecis.extraction.finetuned_guard import apply_finetuned_gate

        llm_models = apply_finetuned_gate(args.model, llm_models)

    if args.migrate_tickers:
        from ecis.db.ticker_registry import migrate_from_directories
        n = migrate_from_directories()
        print(f"Migrated {n} tickers into the registry")
        return

    if args.list_tickers:
        from ecis.db.ticker_registry import list_tickers as registry_list
        rows = registry_list()
        if not rows:
            print("Ticker registry is empty. Run --migrate-tickers.")
            return
        print(f"{'Ticker':<8} {'Company':<28} {'Transcripts':>11} {'Extract':<12} {'Outcomes':<12}")
        for r in rows:
            print(
                f"{r['ticker']:<8} {r['company_name']:<28} {r['total_transcripts']:>11} "
                f"{r['extraction_status']:<12} {r['outcome_resolution_status']:<12}"
            )
        return

    if args.approve is not None or args.reject is not None:
        from ecis.db.approvals import resolve_approval
        aid = args.approve if args.approve is not None else args.reject
        approved = args.approve is not None
        result = resolve_approval(aid, approved=approved)
        print(f"Approval #{aid} → {result['status']}")
        return

    if args.learn:
        from ecis.graphs.learning_graph import run_learning
        result = run_learning()
        print("Learning graph")
        print(f"  FN rate: {result.get('false_negative_rate', 0):.4f}")
        print(f"  Missed D: {result.get('missed_from_category_d', 0)}")
        print(f"  Adjustment: {result.get('adjustment_magnitude', 0):.2%}")
        print(f"  Applied: {result.get('adjustment_applied')}")
        print(f"  HITL: {result.get('requires_human_approval')}")
        if result.get("skip_reason"):
            print(f"  {result['skip_reason']}")
        return

    if args.vindicate:
        from ecis.extraction.vindication import aggregate_vindications
        result = aggregate_vindications()
        print("Vindication aggregation")
        print(f"  Conflicts: {result['total_conflicts']}")
        print(f"  Applied: {result['applied']}")
        print(f"  HITL: {result['requires_human_approval']}")
        print(f"  {result['reason']}")
        print(f"  Weights: {result['proposed_weights']}")
        return

    if args.link_trends:
        from ecis.extraction.temporal_linking import link_trends
        ticker = tickers[0] if tickers else None
        result = link_trends(ticker=ticker)
        print("Temporal linking")
        print(f"  Labelled: {result['labelled']}")
        print(f"  By trend: {result['by_trend']}")
        return

    if args.link_decay:
        from ecis.scoring.signal_decay import link_decay
        ticker = tickers[0] if tickers else None
        result = link_decay(ticker=ticker)
        print("Signal decay")
        print(f"  Labelled: {result['labelled']}")
        print(f"  By profile: {result['by_profile']}")
        return

    if args.export_qlora:
        from ecis.scripts.export_qlora_jsonl import export_jsonl
        from pathlib import Path
        ticker = tickers[0] if tickers else None
        n = export_jsonl(Path(args.export_qlora), ticker=ticker)
        print(f"Wrote {n} QLoRA triples to {args.export_qlora}")
        return

    if args.batch:
        if not tickers:
            parser.error("--batch requires --ticker")
        cmd_batch(tickers, llm_models=llm_models, force=args.force_extract)
        return

    if args.ingest:
        if not tickers:
            parser.error("--ingest requires --ticker")
        cmd_ingest(tickers, args.source)

    if args.preprocess:
        if not tickers:
            parser.error("--preprocess requires --ticker")
        cmd_preprocess(tickers)

    if args.extract:
        if args.file:
            if not tickers:
                parser.error("--extract --file requires --ticker")
            models = llm_models or [_settings.llm_model]
            for model in models:
                cmd_extract(tickers[0], args.file, llm_model=model, force=args.force_extract)
        else:
            cmd_extract_all(tickers, llm_models=llm_models, force=args.force_extract)

    if args.resolve_outcomes:
        from ecis.scoring.outcome_resolver import resolve_all, resolve_ticker
        if tickers:
            for t in tickers:
                n = resolve_ticker(t, force=args.force_resolve)
                print(f"{t}: resolved {n} outcomes")
                from ecis.db.ticker_registry import mark_outcomes
                mark_outcomes(t)
        else:
            n = resolve_all(force=args.force_resolve)
            print(f"Resolved {n} outcomes total")

    if args.score:
        from ecis.scoring.scorer import print_scorecard
        ticker = tickers[0] if tickers else None
        print_scorecard(ticker=ticker, horizon=args.horizon)

    if args.recalibrate:
        from ecis.scoring.recalibrator import recalibrate_signals
        method = args.recalibrate
        source = tickers[0].lower() if tickers else None
        n = recalibrate_signals(method=method, source_method=source)
        print(f"Recalibrated {n} signals using {method}")

    if args.watchdog:
        from ecis.graphs.watchdog_graph import run_watchdog
        for reader in ["keyword", "finbert", "llm", "finetuned_llm", "triangulated"]:
            print(f"\nWatchdog: {reader}")
            result = run_watchdog(reader)
            action = result.get("action_type")
            if action:
                print(f"  Action: {action} — {result.get('action_details', {})}")
            else:
                print(f"  No action needed (ECE={result.get('rolling_ece', 0):.4f})")

    if args.predict:
        from ecis.prediction.models import train_and_predict
        ticker = tickers[0] if tickers else None
        result = train_and_predict(ticker)
        print("Prediction training")
        print(f"  Trained: {result.get('trained')}  n_train={result.get('n_train')}")
        if result.get("reason"):
            print(f"  {result['reason']}")
        for row in result.get("predictions") or []:
            print(
                f"  {row['ticker']} {row['as_of_date']} {row['model_name']}: "
                f"{row['predicted_direction']} ({row['predicted_confidence']:.2f})"
            )

    if args.score_predictions:
        from ecis.prediction.scorecard import print_prediction_scorecard
        print_prediction_scorecard(tickers[0] if tickers else None)

    if args.correlate:
        from ecis.extraction.correlation import update_correlations
        result = update_correlations()
        print(f"Correlations: {result['pairs']} pairs, {result['high_corr']} |r|>=0.7")

    if args.link_linguistics:
        from ecis.extraction.linguistics import link_linguistics
        result = link_linguistics(tickers[0] if tickers else None)
        print(f"Linguistics labelled: {result['labelled']}")

    if args.link_surprise:
        from ecis.prediction.surprise import link_surprise
        result = link_surprise(tickers[0] if tickers else None)
        print(f"Surprise labelled: {result['labelled']} high={result['high']} low={result['low']}")

    if args.reader_health:
        from ecis.extraction.health import record_reader_health
        for rec in record_reader_health():
            flag = f" ALERT {rec['alert']}" if rec.get("alert") else ""
            print(
                f"  {rec['reader_name']}: success={rec['success_rate']:.2f} "
                f"abstain={rec['abstention_rate']:.2f}{flag}"
            )

    if args.refresh_views:
        from ecis.db.views import refresh_views
        print(f"Views refreshed: {refresh_views()}")

    if args.profile_data:
        from ecis.quality.profiler import profile_data
        for rec in profile_data():
            extra = f" freq={rec['freq']}" if rec.get("freq") else ""
            print(f"  {rec['field_name']}: n={rec.get('n', 0)}{extra}")

    if args.lineage:
        from ecis.quality.lineage import write_lineage_for_signals
        n = write_lineage_for_signals(tickers[0] if tickers else None)
        print(f"Lineage backfilled: {n}")

    if args.completeness:
        from ecis.quality.completeness import report_completeness
        for rec in report_completeness():
            print(
                f"  {rec['ticker']}: consensus={rec['missing_consensus']} "
                f"prices={rec['missing_prices']} chroma={rec['missing_chroma']} "
                f"outcomes={rec['missing_outcomes']}"
            )

    if args.audit_queries:
        from ecis.db.query_monitor import audit_dashboard_queries
        for rec in audit_dashboard_queries():
            flag = " SLOW" if rec.get("slow") else ""
            print(f"  {rec['name']}: {rec['elapsed_ms']:.2f}ms{flag}")

    if args.cleanup_exemplars:
        from ecis.embedding.exemplar_cleanup import cleanup_exemplars
        result = cleanup_exemplars()
        print(f"Exemplars removed={result['removed']} kept={result['kept']} rebalanced={result['rebalanced']}")

    if args.evaluate:
        from ecis.scoring.evaluation import evaluate
        report = evaluate(tickers[0] if tickers else None, horizon=args.horizon)
        print("Evaluation")
        print(f"  n={report['n']}")
        boot = report.get("bootstrap") or {}
        if boot.get("brier"):
            b = boot["brier"]
            print(f"  Brier {b['estimate']:.4f} [{b['lo']:.4f}, {b['hi']:.4f}]")
        for row in report.get("model_comparisons") or []:
            print(
                f"  {row['model_a']} vs {row['model_b']}: "
                f"Δbrier={row['diff']:.4f} p={row['p_value']:.4f}"
            )
        power = report.get("power") or {}
        if power.get("ir"):
            print(f"  Extra tickers for IR 0.5: {power['ir']['extra_tickers']}")
        if power.get("brier"):
            print(f"  Extra signals for Δbrier 0.02: {power['brier']['extra_signals']}")

    if args.drift:
        from ecis.scoring.drift import check_drift
        result = check_drift()
        print(f"Drift: {result['status']}")
        for rec in result.get("features") or []:
            print(f"  {rec}")

    if args.watch_predictions:
        from ecis.prediction.decay_watch import watch_decay
        result = watch_decay()
        print(f"Prediction watchdog ok={result['ok']} alerts={result['alerts']}")
        if result.get("retrain"):
            print("  Propose model retraining (10 consecutive misses vs momentum).")

    all_commands = [
        args.init_db, args.ingest, args.preprocess, args.extract,
        args.batch, args.resolve_outcomes, args.score, args.recalibrate,
        args.watchdog, args.learn, args.vindicate, args.link_trends, args.link_decay,
        args.export_qlora, args.migrate_tickers,
        args.list_tickers, args.dashboard, args.api,
        args.approve is not None, args.reject is not None,
        args.predict, args.score_predictions, args.correlate,
        args.link_linguistics, args.link_surprise, args.reader_health,
        args.refresh_views, args.profile_data, args.lineage, args.completeness,
        args.audit_queries, args.cleanup_exemplars, args.evaluate,
        args.drift, args.watch_predictions,
    ]
    if not any(all_commands):
        parser.print_help()


if __name__ == "__main__":
    main()
