import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
NEEDED = ["headline_confidence_intervals.csv", "monthly_activity.csv", "established_activity.csv",
          "reactivation_gap3.csv", "spend_by_year_jan_oct.csv", "spend_concentration.csv", "category_mix.csv",
          "rfm_segment_summary.csv", "rfm_stability_transitions.csv", "rfm_profile.csv", "hypothesis_tests.csv",
          "ab_sample_size.csv", "ab_simulation_results.csv", "ab_example_experiment.csv"]


@pytest.mark.skipif(not all((TABLES / n).exists() for n in NEEDED),
                    reason="run the analysis scripts first so reports/tables is filled")
def test_dashboard_runs_without_errors():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=90).run()
    assert not at.exception
    assert at.title[0].value == "Retail behaviour analytics"
    assert len(at.tabs) == 7
    assert len(at.slider) == 2
    at.slider[0].set_value(5.0).run()                      # moving a slider must not break the page
    assert not at.exception
