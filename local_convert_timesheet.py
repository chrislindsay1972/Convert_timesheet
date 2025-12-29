#!/usr/bin/env python3
"""
Local deterministic converter for the Zoho Deluge `convert_timesheet` logic.

This does NOT call OpenAI. It converts the known input CSV schema into the
payroll CSV schema using explicit rules:
 - one output row per component (Expenses, Std Hrs, OT1 Hrs)
 - never create OT/Expenses lines when their driving value is 0
 - never swap amount/rate
 - weekending converted from DD/MM/YYYY (or DD/MM/YY) to YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _norm_spaces(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _desc(prefix: str, client: str, job: str) -> str:
    # Ensure "Type - Client - Job" with single spaces around hyphens
    return f"{_norm_spaces(prefix)} - {_norm_spaces(client)} - {_norm_spaces(job)}"


def _parse_decimal(s: str) -> Decimal:
    s = (s or "").strip()
    if not s:
        return Decimal(0)
    # Remove thousands separators
    s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(0)


def _fmt_decimal(x: Decimal) -> str:
    # Produce a human-ish decimal string without scientific notation
    # and without unnecessary trailing zeros.
    s = format(x.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _parse_weekending(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            return d.isoformat()
        except ValueError:
            continue
    # If already ISO-ish, pass through
    try:
        return dt.date.fromisoformat(s).isoformat()
    except ValueError:
        return s


def convert_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    out: list[list[str]] = []
    for r in rows:
        employeeid = _norm_spaces(r.get("Candidate RefNo", ""))
        firstname = _norm_spaces(r.get("Candidate Forename", ""))
        surname = _norm_spaces(r.get("Candidate Surname", ""))
        client = r.get("Client Name", "") or ""
        job = r.get("Contract JobTitle", "") or ""
        weekending = _parse_weekending(r.get("Weekending", ""))

        # Valid detail row check (matches Deluge instructions)
        if not employeeid or not firstname or not surname or not weekending:
            continue
        if employeeid.lower() == "candidate refno":
            continue

        std_hours = _parse_decimal(r.get("Std1 Hrs", ""))
        ot1_hours = _parse_decimal(r.get("OT1 Hrs", ""))
        std_rate = _parse_decimal(r.get("Std Rate", ""))
        ot1_rate = _parse_decimal(r.get("OT1 Rate", ""))
        expenses = _parse_decimal(r.get("Expenses", ""))

        # Expenses line first
        if expenses != 0:
            out.append(
                [
                    employeeid,
                    firstname,
                    surname,
                    _desc("Expenses", client, job),
                    "1",
                    _fmt_decimal(expenses),
                    weekending,
                    "expense",
                ]
            )

        # Standard hours
        if std_hours != 0 and std_rate != 0:
            out.append(
                [
                    employeeid,
                    firstname,
                    surname,
                    _desc("Std Hrs", client, job),
                    _fmt_decimal(std_hours),
                    _fmt_decimal(std_rate),
                    weekending,
                    "hours",
                ]
            )

        # OT1 hours
        if ot1_hours != 0 and ot1_rate != 0:
            out.append(
                [
                    employeeid,
                    firstname,
                    surname,
                    _desc("OT1 Hrs", client, job),
                    _fmt_decimal(ot1_hours),
                    _fmt_decimal(ot1_rate),
                    weekending,
                    "hours",
                ]
            )

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv", type=Path)
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("generated_output.csv"),
        help="Output CSV path (default: generated_output.csv)",
    )
    args = ap.parse_args()

    with args.input_csv.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    out_rows = convert_rows(rows)

    header = [
        "employeeid",
        "firstname",
        "surname",
        "description",
        "amount",
        "rate",
        "weekending",
        "unit",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

