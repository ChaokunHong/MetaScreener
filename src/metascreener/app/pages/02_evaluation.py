"""Streamlit page for evaluation dashboard."""
from __future__ import annotations

import csv
import json
from io import StringIO

import streamlit as st

from metascreener.core.enums import Decision, ScreeningStage, Tier
from metascreener.core.models import ScreeningDecision
from metascreener.evaluation.calibrator import EvaluationRunner
from metascreener.evaluation.metrics import format_lancet
from metascreener.evaluation.visualizer import (
    plot_calibration_curve,
    plot_roc_curve,
    plot_score_distribution,
    plot_threshold_analysis,
)


def main() -> None:
    """Render the evaluation dashboard page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Evaluation",
        page_icon="\U0001f4ca",
        layout="wide",
    )
    st.title("Evaluation Dashboard")
    st.markdown("Evaluate screening performance with metrics and visualizations.")

    # Sidebar — file upload
    with st.sidebar:
        st.header("Data Upload")
        labels_file = st.file_uploader(
            "Gold standard labels (CSV)",
            type=["csv"],
            help="CSV with record_id and label columns",
        )
        preds_file = st.file_uploader(
            "Predictions (JSON)",
            type=["json"],
            help="JSON array of screening decisions",
        )
        seed = st.number_input("Bootstrap seed", value=42, min_value=0)

    # Main area
    if labels_file is not None and preds_file is not None:
        try:
            # Load gold labels
            content = labels_file.read().decode("utf-8")
            reader = csv.DictReader(StringIO(content))
            gold_labels: dict[str, Decision] = {}
            for row in reader:
                gold_labels[row["record_id"]] = Decision(row["label"].strip().upper())

            # Load predictions
            preds_data = json.loads(preds_file.read().decode("utf-8"))
            decisions = [
                ScreeningDecision(
                    record_id=item["record_id"],
                    stage=ScreeningStage(item.get("stage", "ta")),
                    decision=Decision(item["decision"]),
                    tier=Tier(item.get("tier", 1)),
                    final_score=float(item.get("final_score", 0.5)),
                    ensemble_confidence=float(
                        item.get("ensemble_confidence", 0.5)
                    ),
                )
                for item in preds_data
            ]

            st.success(
                f"Loaded {len(gold_labels)} labels and "
                f"{len(decisions)} predictions."
            )

            # Compute button
            if st.button("Compute Metrics", type="primary"):
                runner = EvaluationRunner()
                report = runner.evaluate_screening(
                    decisions, gold_labels, seed=seed
                )
                st.session_state["eval_report"] = report
                st.session_state["eval_decisions"] = decisions
                st.session_state["eval_gold"] = gold_labels

        except Exception as exc:  # noqa: BLE001
            st.error(f"Error loading data: {exc}")

    else:
        st.info("Upload gold labels and predictions in the sidebar.")

    # Display results
    if "eval_report" in st.session_state:
        report = st.session_state["eval_report"]
        m = report.metrics

        # Metrics table
        st.subheader("Screening Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Sensitivity", f"{m.sensitivity:.4f}")
        col2.metric("Specificity", f"{m.specificity:.4f}")
        col3.metric("Precision", f"{m.precision:.4f}")
        col4.metric("F1", f"{m.f1:.4f}")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("WSS@95", f"{m.wss_at_95:.4f}")
        col6.metric("AUROC", f"{report.auroc.auroc:.4f}")
        col7.metric("ECE", f"{report.calibration.ece:.4f}")
        col8.metric("N", str(m.n_total))

        # Bootstrap CIs in Lancet format
        if report.bootstrap_cis:
            st.subheader("Bootstrap 95% CIs (Lancet format)")
            ci_data = []
            for name, ci in report.bootstrap_cis.items():
                ci_data.append(
                    {
                        "Metric": name,
                        "Estimate": format_lancet(
                            ci.point, ci.ci_lower, ci.ci_upper
                        ),
                    }
                )
            st.table(ci_data)

        # Visualization tabs
        st.subheader("Visualizations")
        tab1, tab2, tab3, tab4 = st.tabs(
            [
                "ROC Curve",
                "Calibration",
                "Score Distribution",
                "Threshold Analysis",
            ]
        )

        with tab1:
            st.plotly_chart(
                plot_roc_curve(report.auroc), use_container_width=True
            )

        with tab2:
            st.plotly_chart(
                plot_calibration_curve(report.calibration),
                use_container_width=True,
            )

        with tab3:
            decisions_list = st.session_state["eval_decisions"]
            gold = st.session_state["eval_gold"]
            scores = [
                d.final_score
                for d in decisions_list
                if d.record_id in gold
            ]
            int_labels = [
                1 if gold[d.record_id] == Decision.INCLUDE else 0
                for d in decisions_list
                if d.record_id in gold
            ]
            st.plotly_chart(
                plot_score_distribution(scores, int_labels),
                use_container_width=True,
            )

        with tab4:
            st.plotly_chart(
                plot_threshold_analysis(scores, int_labels),
                use_container_width=True,
            )

        # Optimize Thresholds
        st.markdown("---")
        st.subheader("Threshold Optimization")
        min_sens = st.slider(
            "Minimum sensitivity constraint",
            min_value=0.80,
            max_value=1.00,
            value=0.95,
            step=0.01,
        )
        if st.button("Optimize Thresholds"):
            decisions_list = st.session_state["eval_decisions"]
            gold = st.session_state["eval_gold"]
            runner = EvaluationRunner()
            try:
                thresholds = runner.optimize_thresholds(
                    decisions_list,
                    gold,
                    min_sensitivity=min_sens,
                    seed=seed,
                )
                st.session_state["optimized_thresholds"] = thresholds
            except Exception as exc:  # noqa: BLE001
                st.error(f"Threshold optimization failed: {exc}")

        if "optimized_thresholds" in st.session_state:
            t = st.session_state["optimized_thresholds"]
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("\u03c4 high (Tier 1)", f"{t.tau_high:.3f}")
            tc2.metric("\u03c4 mid (Tier 2)", f"{t.tau_mid:.3f}")
            tc3.metric("\u03c4 low (Tier 3)", f"{t.tau_low:.3f}")

        # Export
        st.markdown("---")
        st.download_button(
            "Export Report (JSON)",
            data=report.model_dump_json(indent=2),
            file_name="evaluation_report.json",
            mime="application/json",
        )

        # ------------------------------------------------------------------
        # Paper-quality figure export
        # ------------------------------------------------------------------
        st.markdown("---")
        st.subheader("Export for Paper")
        st.caption(
            "Generate 300 DPI figures suitable for "
            "Lancet Digital Health submission."
        )

        _export_figure_downloads(
            report,
            st.session_state["eval_decisions"],
            st.session_state["eval_gold"],
        )

        # ------------------------------------------------------------------
        # Copy-for-paper text area with Lancet-formatted metrics
        # ------------------------------------------------------------------
        if report.bootstrap_cis:
            st.markdown("---")
            st.subheader("Copy for Paper")
            st.caption(
                "Pre-formatted metrics text using Lancet Digital Health "
                "conventions (middle dot, en dash, 95% CI)."
            )
            paper_text = _build_paper_metrics_text(report)
            st.text_area(
                "Formatted metrics (select all \u2192 copy)",
                value=paper_text,
                height=200,
            )

        # ------------------------------------------------------------------
        # Comparison placeholder
        # ------------------------------------------------------------------
        st.markdown("---")
        with st.expander("Compare Multiple Runs"):
            st.info(
                "Multi-run comparison is planned for a future release. "
                "Upload multiple evaluation reports side-by-side to "
                "compare screening configurations, threshold settings, "
                "and model ablations."
            )


# ------------------------------------------------------------------
# Helper functions for paper export
# ------------------------------------------------------------------


def _export_figure_downloads(
    report: object,
    decisions_list: list[ScreeningDecision],
    gold: dict[str, Decision],
) -> None:
    """Render download buttons for each visualisation figure.

    Attempts PNG export at 300 DPI via *kaleido*.  Falls back to
    interactive HTML export when kaleido is not installed.

    Args:
        report: The evaluation report stored in session state.
        decisions_list: List of screening decisions.
        gold: Gold-standard label mapping.
    """
    scores = [
        d.final_score for d in decisions_list if d.record_id in gold
    ]
    int_labels = [
        1 if gold[d.record_id] == Decision.INCLUDE else 0
        for d in decisions_list
        if d.record_id in gold
    ]

    figures: dict[str, object] = {}
    try:
        figures["roc_curve"] = plot_roc_curve(
            report.auroc,  # type: ignore[attr-defined]
        )
        figures["calibration"] = plot_calibration_curve(
            report.calibration,  # type: ignore[attr-defined]
        )
        figures["score_distribution"] = plot_score_distribution(
            scores, int_labels
        )
        figures["threshold_analysis"] = plot_threshold_analysis(
            scores, int_labels
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not build figures for export: {exc}")
        return

    # Detect kaleido availability once
    has_kaleido = _kaleido_available()

    if has_kaleido:
        st.caption("Exporting as 300 DPI PNG (kaleido detected).")
    else:
        st.caption(
            "kaleido not installed \u2014 exporting as interactive HTML. "
            "Install kaleido (`pip install kaleido`) for PNG export."
        )

    cols = st.columns(len(figures))
    for idx, (name, fig) in enumerate(figures.items()):
        with cols[idx]:
            label = name.replace("_", " ").title()
            if has_kaleido:
                try:
                    png_bytes = fig.to_image(  # type: ignore[attr-defined]
                        format="png", width=1200, height=900, scale=3
                    )
                    st.download_button(
                        f"\u2b07 {label} (PNG)",
                        data=png_bytes,
                        file_name=f"{name}.png",
                        mime="image/png",
                        key=f"dl_png_{name}",
                    )
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"PNG export failed for {label}: {exc}")
            else:
                html_str = fig.to_html(  # type: ignore[attr-defined]
                    include_plotlyjs="cdn",
                )
                st.download_button(
                    f"\u2b07 {label} (HTML)",
                    data=html_str,
                    file_name=f"{name}.html",
                    mime="text/html",
                    key=f"dl_html_{name}",
                )


def _kaleido_available() -> bool:
    """Check whether the kaleido package is importable.

    Returns:
        True if kaleido can be imported, False otherwise.
    """
    try:
        import kaleido  # noqa: F401

        return True
    except ImportError:
        return False


def _build_paper_metrics_text(report: object) -> str:
    """Build a copy-paste-ready block of Lancet-formatted metrics.

    Each line contains the metric name followed by its point estimate
    and 95% CI formatted with middle dot and en dash.

    Args:
        report: The evaluation report with ``bootstrap_cis`` attribute.

    Returns:
        Multi-line string of formatted metrics.
    """
    lines: list[str] = []
    bootstrap_cis: dict[str, object] = getattr(
        report, "bootstrap_cis", {}
    ) or {}
    for name, ci in bootstrap_cis.items():
        formatted = format_lancet(
            ci.point,  # type: ignore[attr-defined]
            ci.ci_lower,  # type: ignore[attr-defined]
            ci.ci_upper,  # type: ignore[attr-defined]
        )
        display_name = name.replace("_", " ").title()
        lines.append(f"{display_name} {formatted}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
