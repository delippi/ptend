#!/usr/bin/env python3
"""
Plot maximum absolute pressure changes from RRFS ensemble forecast logs.

For each requested date, the script:
  1. Finds forecast-log attempts for each ensemble member and cycle.
  2. Extracts every "max abs change ... bar" value.
  3. Converts bar to hPa.
  4. Writes a CSV summary with threshold exceedance counts.
  5. Creates one daily member-by-cycle-attempt summary plot.
  6. Creates one full time-series plot for each cycle.

By default, every job attempt is processed. This is important when an original
forecast failed and one or more reruns exist in the same output directory.
Attempts are labeled a1, a2, and so on in ascending PBS job-ID order.

Example:
  python plot_rrfs_ens_pressure_change.py 20260615

  python plot_rrfs_ens_pressure_change.py 20260615 \
      --root /lfs/h1/ops/para/output \
      --output-dir ./pressure_change_20260615
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

# Use a noninteractive backend so the script works in cron and batch jobs.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


VALUE_RE = re.compile(
    r"max abs change\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?)"
    r"\s+bar\b"
)

LOG_NAME_RE = re.compile(
    r"^rrfs_ensf_forecast_mem(?P<member>\d{3})_"
    r"(?P<cycle>\d{2})\.o(?P<job_id>\d+)$"
)


@dataclass(frozen=True)
class LogCandidate:
    """One forecast-log attempt discovered in the date directory."""

    cycle: str
    member: str
    job_id: int
    attempt: int
    attempt_count: int
    path: Path


@dataclass
class LogResult:
    """Parsed pressure-change information for one job attempt."""

    date: str
    cycle: str
    member: str
    job_id: int
    attempt: int
    attempt_count: int
    path: Path
    values_hpa: np.ndarray
    malformed_lines: int
    expected_lines: int
    threshold_low: float
    threshold_high: float

    @property
    def line_count(self) -> int:
        return int(self.values_hpa.size)

    @property
    def status(self) -> str:
        if self.line_count == 0:
            return "NO_DATA"
        if self.line_count < self.expected_lines:
            return "SHORT"
        return "OK"

    @property
    def is_short(self) -> bool:
        return self.status == "SHORT"

    @property
    def has_data(self) -> bool:
        return self.line_count > 0

    @property
    def max_hpa(self) -> float:
        if not self.has_data:
            return float("nan")
        return float(np.max(self.values_hpa))

    @property
    def mean_hpa(self) -> float:
        if not self.has_data:
            return float("nan")
        return float(np.mean(self.values_hpa))

    @property
    def median_hpa(self) -> float:
        if not self.has_data:
            return float("nan")
        return float(np.median(self.values_hpa))

    @property
    def p95_hpa(self) -> float:
        if not self.has_data:
            return float("nan")
        return float(np.percentile(self.values_hpa, 95.0))

    @property
    def p99_hpa(self) -> float:
        if not self.has_data:
            return float("nan")
        return float(np.percentile(self.values_hpa, 99.0))

    @property
    def count_ge_low(self) -> int:
        return int(np.count_nonzero(self.values_hpa >= self.threshold_low))

    @property
    def count_ge_high(self) -> int:
        return int(np.count_nonzero(self.values_hpa >= self.threshold_high))

    def first_index_ge(self, threshold: float) -> Optional[int]:
        """Return the one-based report index of the first exceedance."""

        matches = np.flatnonzero(self.values_hpa >= threshold)
        if matches.size == 0:
            return None
        return int(matches[0]) + 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract and plot RRFS ensemble maximum absolute pressure changes."
        )
    )
    parser.add_argument(
        "date",
        help="Run date in YYYYMMDD format.",
    )
    parser.add_argument(
        "--root",
        default="/lfs/h1/ops/para/output",
        help=(
            "Root directory containing YYYYMMDD output directories. "
            "Default: /lfs/h1/ops/para/output"
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help=(
            "Directory for plots and CSV output. "
            "Default: ./rrfs_ens_pressure_change_YYYYMMDD"
        ),
    )
    parser.add_argument(
        "--cycles",
        nargs="+",
        default=["00", "06", "12", "18"],
        help="Cycles to process. Default: 00 06 12 18",
    )
    parser.add_argument(
        "--attempt-policy",
        choices=["all", "oldest", "newest"],
        default="all",
        help=(
            "Select all attempts, only the oldest/original attempt, or only "
            "the newest attempt for each member and cycle. Default: all"
        ),
    )
    parser.add_argument(
        "--threshold-low",
        type=float,
        default=20.0,
        help="Lower exceedance threshold in hPa. Default: 20",
    )
    parser.add_argument(
        "--threshold-high",
        type=float,
        default=30.0,
        help="Upper exceedance threshold in hPa. Default: 30",
    )
    parser.add_argument(
        "--expected-lines",
        type=int,
        default=5000,
        help=(
            "Logs with fewer parsed values are marked SHORT. "
            "This is only a warning, not a failure diagnosis. Default: 5000"
        ),
    )
    parser.add_argument(
        "--plot-ymax",
        type=float,
        default=None,
        help=(
            "Optional upper y-axis limit for cycle time-series plots. "
            "The CSV and summary plot still retain the true maxima."
        ),
    )
    parser.add_argument(
        "--alert-file",
        default=None,
        help=(
            "Optional text file written when at least one selected log reaches "
            "the lower threshold. If no logs reach the threshold, any existing "
            "alert file is removed."
        ),
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"\d{8}", args.date):
        raise ValueError("DATE must use YYYYMMDD format.")

    invalid_cycles = [
        cycle for cycle in args.cycles if not re.fullmatch(r"\d{2}", cycle)
    ]
    if invalid_cycles:
        raise ValueError(
            "Cycles must be two digits. Invalid value(s): "
            + ", ".join(invalid_cycles)
        )

    if args.threshold_low < 0.0 or args.threshold_high < 0.0:
        raise ValueError("Pressure-change thresholds must be nonnegative.")

    if args.threshold_low >= args.threshold_high:
        raise ValueError(
            "--threshold-low must be smaller than --threshold-high."
        )

    if args.expected_lines < 1:
        raise ValueError("--expected-lines must be at least 1.")

    if args.plot_ymax is not None and args.plot_ymax <= 0.0:
        raise ValueError("--plot-ymax must be greater than zero.")


def discover_logs(
    date_dir: Path,
    cycles: Sequence[str],
    attempt_policy: str,
) -> Tuple[List[LogCandidate], List[str]]:
    """
    Find and label forecast-log attempts.

    Attempt labels are assigned using ascending numeric PBS job ID. Processing
    every attempt prevents failed originals from being hidden by later reruns.
    """

    grouped_paths: Dict[Tuple[str, str], List[Tuple[int, Path]]] = {}

    for path in date_dir.glob("rrfs_ensf_forecast_mem???_??.o*"):
        match = LOG_NAME_RE.match(path.name)
        if match is None:
            continue

        cycle = match.group("cycle")
        if cycle not in cycles:
            continue

        member = match.group("member")
        job_id = int(match.group("job_id"))
        key = (cycle, member)
        grouped_paths.setdefault(key, []).append((job_id, path))

    selected: List[LogCandidate] = []
    messages: List[str] = []

    for (cycle, member), attempts in sorted(
        grouped_paths.items(),
        key=lambda item: (item[0][0], int(item[0][1])),
    ):
        attempts.sort(key=lambda item: item[0])
        attempt_count = len(attempts)

        candidates = [
            LogCandidate(
                cycle=cycle,
                member=member,
                job_id=job_id,
                attempt=index,
                attempt_count=attempt_count,
                path=path,
            )
            for index, (job_id, path) in enumerate(attempts, start=1)
        ]

        if attempt_policy == "oldest":
            selected.append(candidates[0])
        elif attempt_policy == "newest":
            selected.append(candidates[-1])
        else:
            selected.extend(candidates)

        if attempt_count > 1:
            job_list = ", ".join(
                f"a{candidate.attempt}=o{candidate.job_id}"
                for candidate in candidates
            )
            messages.append(
                f"mem{member} cycle {cycle}: found {attempt_count} attempts "
                f"({job_list}); policy={attempt_policy}"
            )

    return selected, messages


def parse_log(
    candidate: LogCandidate,
    date: str,
    expected_lines: int,
    threshold_low: float,
    threshold_high: float,
) -> LogResult:
    """
    Stream one log and extract pressure changes.

    The source line is already labeled "max abs change", but abs() is retained
    defensively in case a signed value appears in a future log format.
    """

    values_hpa: List[float] = []
    malformed_lines = 0

    with candidate.path.open("r", errors="replace") as infile:
        for line in infile:
            if "max abs change" not in line:
                continue

            match = VALUE_RE.search(line)
            if match is None:
                malformed_lines += 1
                continue

            # Support Fortran D exponents in addition to normal E exponents.
            value_bar = float(
                match.group(1).replace("D", "E").replace("d", "e")
            )

            # 1 bar = 1000 hPa. Millibars and hPa are numerically equivalent.
            values_hpa.append(abs(value_bar) * 1000.0)

    return LogResult(
        date=date,
        cycle=candidate.cycle,
        member=candidate.member,
        job_id=candidate.job_id,
        attempt=candidate.attempt,
        attempt_count=candidate.attempt_count,
        path=candidate.path,
        values_hpa=np.asarray(values_hpa, dtype=np.float64),
        malformed_lines=malformed_lines,
        expected_lines=expected_lines,
        threshold_low=threshold_low,
        threshold_high=threshold_high,
    )


def format_float_for_csv(value: float) -> str:
    """Format a metric while leaving unavailable values blank."""

    if not np.isfinite(value):
        return ""
    return f"{value:.6f}"


def write_summary_csv(results: Sequence[LogResult], output_path: Path) -> None:
    fieldnames = [
        "date",
        "cycle",
        "member",
        "attempt",
        "attempt_count",
        "job_id",
        "log_file",
        "parsed_values",
        "status",
        "malformed_matching_lines",
        "max_hpa",
        "mean_hpa",
        "median_hpa",
        "p95_hpa",
        "p99_hpa",
        "threshold_low_hpa",
        "threshold_high_hpa",
        "count_ge_low_threshold",
        "count_ge_high_threshold",
        "first_index_ge_low_threshold",
        "first_index_ge_high_threshold",
    ]

    with output_path.open("w", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for result in sorted(
            results,
            key=lambda item: (
                item.cycle,
                int(item.member),
                item.attempt,
            ),
        ):
            first_low = result.first_index_ge(result.threshold_low)
            first_high = result.first_index_ge(result.threshold_high)

            writer.writerow(
                {
                    "date": result.date,
                    "cycle": result.cycle,
                    "member": f"mem{result.member}",
                    "attempt": result.attempt,
                    "attempt_count": result.attempt_count,
                    "job_id": result.job_id,
                    "log_file": str(result.path),
                    "parsed_values": result.line_count,
                    "status": result.status,
                    "malformed_matching_lines": result.malformed_lines,
                    "max_hpa": format_float_for_csv(result.max_hpa),
                    "mean_hpa": format_float_for_csv(result.mean_hpa),
                    "median_hpa": format_float_for_csv(result.median_hpa),
                    "p95_hpa": format_float_for_csv(result.p95_hpa),
                    "p99_hpa": format_float_for_csv(result.p99_hpa),
                    "threshold_low_hpa": f"{result.threshold_low:.6f}",
                    "threshold_high_hpa": f"{result.threshold_high:.6f}",
                    "count_ge_low_threshold": result.count_ge_low,
                    "count_ge_high_threshold": result.count_ge_high,
                    "first_index_ge_low_threshold": (
                        "" if first_low is None else first_low
                    ),
                    "first_index_ge_high_threshold": (
                        "" if first_high is None else first_high
                    ),
                }
            )


def write_alert_summary(
    results: Sequence[LogResult],
    output_path: Path,
    threshold_low: float,
    threshold_high: float,
) -> bool:
    """
    Write an alert summary when the lower threshold is reached.

    Return True when an alert file was written and False when no selected
    result reached the lower threshold.
    """

    alert_results = sorted(
        (
            result
            for result in results
            if result.count_ge_low > 0
        ),
        key=lambda item: (
            item.cycle,
            int(item.member),
            item.attempt,
        ),
    )

    if not alert_results:
        # Prevent an alert from a previous run from being emailed again.
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass

        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as outfile:
        outfile.write(
            "RRFS ensemble pressure-change threshold alert\n"
        )
        outfile.write(
            f"Date: {alert_results[0].date}\n"
        )
        outfile.write(
            f"Lower threshold: {threshold_low:g} hPa\n"
        )
        outfile.write(
            f"Upper threshold: {threshold_high:g} hPa\n"
        )
        outfile.write(
            f"Matching job attempts: {len(alert_results)}\n"
        )
        outfile.write("\n")

        outfile.write(
            "cycle  member  attempt  job_id      max_hPa  "
            f"count>={threshold_low:g}  count>={threshold_high:g}  "
            "first_index\n"
        )
        outfile.write("-" * 100 + "\n")

        for result in alert_results:
            first_low = result.first_index_ge(threshold_low)

            outfile.write(
                f"{result.cycle:>5}  "
                f"mem{result.member:<3}  "
                f"a{result.attempt:<6d}  "
                f"{result.job_id:>10d}  "
                f"{result.max_hpa:>9.3f}  "
                f"{result.count_ge_low:>10d}  "
                f"{result.count_ge_high:>10d}  "
                f"{first_low if first_low is not None else '-'}\n"
            )

            outfile.write(
                f"       Log: {result.path}\n"
            )

    return True

def plot_cycle_time_series(
    cycle_results: Sequence[LogResult],
    output_path: Path,
    threshold_low: float,
    threshold_high: float,
    plot_ymax: Optional[float],
) -> None:
    """Plot all selected ensemble-member attempts for one cycle."""

    ordered = sorted(
        cycle_results,
        key=lambda item: (int(item.member), item.attempt),
    )
    cycle = ordered[0].cycle
    date = ordered[0].date

    fig, ax = plt.subplots(figsize=(13, 7), dpi=200)

    for result in ordered:
        label = (
            f"mem{result.member} a{result.attempt} "
            f"o{result.job_id}"
        )
        if result.status != "OK":
            label += f" ({result.status})"

        if result.has_data:
            report_index = np.arange(1, result.line_count + 1)
            ax.plot(
                report_index,
                result.values_hpa,
                linewidth=0.7,
                alpha=0.80,
                label=label,
            )
        else:
            # Add a legend entry even when the attempt has no matching data.
            ax.plot([], [], linewidth=0.7, label=label)

    ax.axhline(
        threshold_low,
        linewidth=1.0,
        linestyle="--",
        label=f"{threshold_low:g} hPa",
    )
    ax.axhline(
        threshold_high,
        linewidth=1.0,
        linestyle=":",
        label=f"{threshold_high:g} hPa",
    )

    if plot_ymax is not None:
        ax.set_ylim(0.0, plot_ymax)

    ax.set_title(
        f"RRFS Ensemble Maximum Absolute Pressure Change\n"
        f"{date} cycle {cycle}Z, all selected attempts"
    )
    ax.set_xlabel("Reported pressure-change index")
    ax.set_ylabel("Maximum absolute pressure change (hPa)")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=4,
        fontsize=7,
        frameon=False,
    )

    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def plot_daily_summary(
    results: Sequence[LogResult],
    cycles: Sequence[str],
    output_path: Path,
    threshold_low: float,
    threshold_high: float,
) -> None:
    """
    Plot a member-attempt-by-cycle heatmap.

    Cell color is the maximum pressure change. Cell text is:
      maximum hPa
      count >= lower threshold / count >= upper threshold

    An asterisk marks a log with fewer than --expected-lines parsed values.
    Attempts are ordered by numeric PBS job ID within each member and cycle.
    """

    row_keys = sorted(
        {(result.member, result.attempt) for result in results},
        key=lambda item: (int(item[0]), item[1]),
    )
    cycle_list = [
        cycle
        for cycle in cycles
        if any(result.cycle == cycle for result in results)
    ]

    result_map = {
        (result.member, result.attempt, result.cycle): result
        for result in results
    }

    max_values = np.full(
        (len(row_keys), len(cycle_list)),
        np.nan,
        dtype=np.float64,
    )

    for row, (member, attempt) in enumerate(row_keys):
        for column, cycle in enumerate(cycle_list):
            result = result_map.get((member, attempt, cycle))
            if result is not None and result.has_data:
                max_values[row, column] = result.max_hpa

    finite_values = max_values[np.isfinite(max_values)]
    color_max = max(
        threshold_high,
        float(np.max(finite_values)) if finite_values.size else threshold_high,
    )

    figure_height = max(6.0, 0.38 * len(row_keys) + 2.5)
    fig, ax = plt.subplots(figsize=(10, figure_height), dpi=200)

    image = ax.imshow(
        np.ma.masked_invalid(max_values),
        aspect="auto",
        interpolation="nearest",
        vmin=0.0,
        vmax=color_max,
    )

    ax.set_xticks(np.arange(len(cycle_list)))
    ax.set_xticklabels([f"{cycle}Z" for cycle in cycle_list])
    ax.set_yticks(np.arange(len(row_keys)))
    ax.set_yticklabels(
        [f"mem{member} a{attempt}" for member, attempt in row_keys]
    )

    for row, (member, attempt) in enumerate(row_keys):
        for column, cycle in enumerate(cycle_list):
            result = result_map.get((member, attempt, cycle))

            if result is None:
                annotation = ""
            elif not result.has_data:
                annotation = f"NO DATA\no{result.job_id}"
            else:
                short_marker = "*" if result.is_short else ""
                annotation = (
                    f"{result.max_hpa:.1f}{short_marker}\n"
                    f"{result.count_ge_low}/{result.count_ge_high}"
                )

            ax.text(
                column,
                row,
                annotation,
                ha="center",
                va="center",
                fontsize=7,
            )

    date = results[0].date
    ax.set_title(
        f"RRFS Ensemble Pressure-Change Summary for {date}\n"
        f"Cell: max hPa; counts >= {threshold_low:g} / "
        f">= {threshold_high:g} hPa"
    )
    ax.set_xlabel("Forecast cycle")
    ax.set_ylabel("Ensemble member and job attempt")

    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label("Maximum absolute pressure change (hPa)")

    fig.subplots_adjust(bottom=0.14)
    fig.text(
        0.125,
        0.035,
        "a# is ordered by PBS job ID. * means fewer than expected lines.",
        ha="left",
        va="bottom",
        fontsize=8,
    )

    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def format_terminal_max(result: LogResult) -> str:
    """Format the maximum value for terminal output."""

    if not result.has_data:
        return "-"
    return f"{result.max_hpa:.3f}"


def print_terminal_summary(
    results: Sequence[LogResult],
    threshold_low: float,
    threshold_high: float,
) -> None:
    print("")
    print(
        "cycle  member  att      job_id   values  status     max_hPa  "
        f">={threshold_low:g}hPa  >={threshold_high:g}hPa"
    )
    print("-" * 91)

    for result in sorted(
        results,
        key=lambda item: (
            item.cycle,
            int(item.member),
            item.attempt,
        ),
    ):
        print(
            f"{result.cycle:>5}  "
            f"mem{result.member:<3}  "
            f"a{result.attempt:<2d}  "
            f"{result.job_id:>10d}  "
            f"{result.line_count:>7d}  "
            f"{result.status:<7}  "
            f"{format_terminal_max(result):>9}  "
            f"{result.count_ge_low:>8d}  "
            f"{result.count_ge_high:>8d}"
        )


def main() -> int:
    args = parse_args()

    try:
        validate_args(args)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    date_dir = Path(args.root) / args.date
    if not date_dir.is_dir():
        print(
            f"ERROR: Date directory does not exist: {date_dir}",
            file=sys.stderr,
        )
        return 2

    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else Path(f"rrfs_ens_pressure_change_{args.date}")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates, discovery_messages = discover_logs(
        date_dir=date_dir,
        cycles=args.cycles,
        attempt_policy=args.attempt_policy,
    )

    for message in discovery_messages:
        print(f"INFO: {message}", file=sys.stderr)

    if not candidates:
        print(
            f"ERROR: No matching forecast logs found in {date_dir}",
            file=sys.stderr,
        )
        return 1

    results: List[LogResult] = []

    for candidate in candidates:
        print(
            f"Scanning mem{candidate.member} {candidate.cycle}Z "
            f"a{candidate.attempt}/{candidate.attempt_count}: "
            f"{candidate.path}"
        )

        try:
            result = parse_log(
                candidate=candidate,
                date=args.date,
                expected_lines=args.expected_lines,
                threshold_low=args.threshold_low,
                threshold_high=args.threshold_high,
            )
        except OSError as error:
            print(
                f"WARNING: Could not read {candidate.path}: {error}",
                file=sys.stderr,
            )
            continue

        if not result.has_data:
            print(
                f"WARNING: No parsable pressure changes found in "
                f"{candidate.path}",
                file=sys.stderr,
            )

        results.append(result)

    if not results:
        print(
            "ERROR: No forecast logs could be read.",
            file=sys.stderr,
        )
        return 1

    policy_label = f"{args.attempt_policy}_attempts"
    csv_path = output_dir / (
        f"rrfs_ens_pressure_change_{args.date}_{policy_label}_summary.csv"
    )
    write_summary_csv(results, csv_path)

    alert_path: Optional[Path] = None
    alert_created = False

    if args.alert_file is not None:
        alert_path = Path(args.alert_file)
        alert_created = write_alert_summary(
            results=results,
            output_path=alert_path,
            threshold_low=args.threshold_low,
            threshold_high=args.threshold_high,
        )

    daily_plot_path = output_dir / (
        f"rrfs_ens_pressure_change_{args.date}_{policy_label}_summary.png"
    )
    plot_daily_summary(
        results=results,
        cycles=args.cycles,
        output_path=daily_plot_path,
        threshold_low=args.threshold_low,
        threshold_high=args.threshold_high,
    )

    for cycle in args.cycles:
        cycle_results = [
            result for result in results if result.cycle == cycle
        ]
        if not cycle_results:
            continue

        cycle_plot_path = output_dir / (
            f"rrfs_ens_pressure_change_{args.date}_{policy_label}_{cycle}Z.png"
        )
        plot_cycle_time_series(
            cycle_results=cycle_results,
            output_path=cycle_plot_path,
            threshold_low=args.threshold_low,
            threshold_high=args.threshold_high,
            plot_ymax=args.plot_ymax,
        )

    print_terminal_summary(
        results=results,
        threshold_low=args.threshold_low,
        threshold_high=args.threshold_high,
    )

    print("")
    print(f"Attempt policy: {args.attempt_policy}")
    print(f"CSV summary:    {csv_path}")
    print(f"Daily summary:  {daily_plot_path}")
    print(f"Cycle plots:    {output_dir}")

    if alert_path is not None:
        if alert_created:
            print(f"Alert summary:  {alert_path}")
        else:
            print(
                "Alert summary:  not created; lower threshold was not reached"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

