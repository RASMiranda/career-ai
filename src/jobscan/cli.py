"""jobscan <command>   (also: python -m jobscan <command>)

  cv-check --data PATH   names the CV files changed or missing since cv_manifest.json was written

Exit codes: 0 all fresh · 1 stale or missing files (named) · 2 the check could not run.
"""

import argparse
import sys

from . import cvcheck
from .config import ConfigError, data_root


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cv-check", help="are the CV files still the ones the manifest was written for")
    p.add_argument("--data", help="path to the private data repo (or CAREER_DATA)")
    args = ap.parse_args(argv)

    try:
        root = data_root(args.data)
        report = cvcheck.check(root)
    except (ConfigError, cvcheck.CvCheckError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if report.fresh:
        print(f"cv-check: all {report.checked} CV file(s) match {cvcheck.MANIFEST}")
        return 0
    print(f"cv-check: {len(report.stale)} changed and {len(report.missing)} missing "
          f"of {report.checked} CV file(s):")
    for name in report.stale:
        print(f"  changed: {name}")
    for name in report.missing:
        print(f"  missing: {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
