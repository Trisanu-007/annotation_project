#!/usr/bin/env python3
"""
Upload depth-grouped CSV samples into the annotation database.

This script reads the standard CSV export, groups rows by depth, and assigns
non-overlapping samples to 10 users using alternating bucket patterns:

- Depths 1-5, 11-15, 21-25, 31-35, 41-45 -> bucket A
- Depths 6-10, 16-20, 26-30, 36-40, 46-50 -> bucket B

Users are assigned alternately by bucket:
- user 1, 3, 5, 7, 9 -> bucket A
- user 2, 4, 6, 8, 10 -> bucket B

Each user receives exactly one sample from each of the five bucket instances,
for a total of 5 samples per user.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path


def get_app_objects():
    from app import app, db, AnnotationSample, Answer

    return app, db, AnnotationSample, Answer


def resolve_input_path(file_path: str) -> Path:
    """Resolve the input CSV path, with a fallback for hyphen/underscore variants."""
    path = Path(file_path)
    if path.exists():
        return path

    alternate_name = path.name.replace("_", "-") if "_" in path.name else path.name.replace("-", "_")
    alternate_path = path.with_name(alternate_name)
    if alternate_path.exists():
        return alternate_path

    raise FileNotFoundError(f"Could not find input file: {file_path}")


def load_csv_records(file_path: str):
    """Load CSV rows and keep the original row order for tie-breaking."""
    resolved_path = resolve_input_path(file_path)

    with resolved_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        records = []

        for order, row in enumerate(reader):
            normalized_row = dict(row)
            normalized_row["_source_order"] = order
            records.append(normalized_row)

    return records, resolved_path


def parse_depth(record):
    try:
        return int(str(record.get("Depth", "")).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid depth value: {record.get('Depth')!r}") from exc


def parse_question_no(record):
    value = str(record.get("Question_No", "")).strip()
    try:
        return int(value)
    except ValueError:
        return record.get("_source_order", 0)


def bucket_for_depth(depth):
    """Return A or B for a 5-depth block."""
    block_index = (depth - 1) // 5
    return "A" if block_index % 2 == 0 else "B"


def depth_block_start(depth):
    return ((depth - 1) // 5) * 5 + 1


def build_depth_groups(records):
    """Group records by exact depth while preserving sorted order inside each depth."""
    grouped = defaultdict(list)

    sorted_records = sorted(
        records,
        key=lambda record: (
            parse_depth(record),
            parse_question_no(record),
            record.get("_source_order", 0),
        ),
    )

    for record in sorted_records:
        grouped[parse_depth(record)].append(record)

    return grouped


def build_user_assignments(records, num_users=10):
    """Assign one sample from each bucket instance to alternating users.
    
    Ensures each user gets at least 2 samples with Response='No'.
    """
    if num_users != 10:
        raise ValueError("This assignment scheme currently expects exactly 10 users.")

    depth_groups = build_depth_groups(records)
    expected_depths = list(range(1, 51))

    missing_depths = [depth for depth in expected_depths if depth not in depth_groups]
    if missing_depths:
        raise ValueError(f"Missing rows for depths: {missing_depths}")

    users_by_bucket = {
        "A": [1, 3, 5, 7, 9],
        "B": [2, 4, 6, 8, 10],
    }

    # Categorize rows by depth and response type
    depth_groups_by_response = {}
    for depth, rows in depth_groups.items():
        yes_rows = [r for r in rows if str(r.get("Response", "")).strip() == "Yes"]
        no_rows = [r for r in rows if str(r.get("Response", "")).strip() == "No"]
        depth_groups_by_response[depth] = {"Yes": yes_rows, "No": no_rows}

    assignments = {user_number: [] for user_number in range(1, num_users + 1)}
    no_response_count = {user_number: 0 for user_number in range(1, num_users + 1)}
    used_source_orders = set()
    used_by_depth = {depth: set() for depth in range(1, 51)}

    for block_index, block_start in enumerate(range(1, 51, 5)):
        block_depths = list(range(block_start, block_start + 5))
        bucket = bucket_for_depth(block_start)
        target_users = users_by_bucket[bucket]
        remaining_instances = 5 - block_index - 1  # How many block instances left (including this one)

        selected_rows = []
        for depth in block_depths:
            yes_rows = [r for r in depth_groups_by_response[depth]["Yes"] 
                       if r.get("_source_order") not in used_by_depth[depth]]
            no_rows = [r for r in depth_groups_by_response[depth]["No"] 
                      if r.get("_source_order") not in used_by_depth[depth]]

            if not yes_rows and not no_rows:
                raise ValueError(f"No available rows for depth {depth}")

            # Determine if we should prefer "No" responses
            # Count how many users still need "No" responses
            users_needing_no = [u for u in target_users if no_response_count[u] < 2]
            
            # Prefer "No" if users still need them and rows are available
            if users_needing_no and no_rows:
                chosen_row = no_rows[0]
            elif yes_rows:
                chosen_row = yes_rows[0]
            elif no_rows:
                chosen_row = no_rows[0]
            else:
                raise ValueError(f"No available rows for depth {depth}")

            selected_rows.append(chosen_row)

        if len(selected_rows) != len(target_users):
            raise ValueError(
                f"Block starting at depth {block_start} produced {len(selected_rows)} rows, "
                f"but {len(target_users)} users need samples."
            )

        for user_number, record in zip(target_users, selected_rows):
            source_order = record.get("_source_order")
            if source_order in used_source_orders:
                raise ValueError(
                    f"Duplicate assignment detected for source row {source_order} "
                    f"at depth {record.get('Depth')}"
                )

            used_source_orders.add(source_order)
            used_by_depth[parse_depth(record)].add(source_order)

            response = str(record.get("Response", "")).strip()
            if response == "No":
                no_response_count[user_number] += 1

            payload = dict(record)
            payload.pop("_source_order", None)

            assignments[user_number].append(
                {
                    "depth": parse_depth(record),
                    "bucket": bucket,
                    "block_start": block_start,
                    "record": payload,
                }
            )

    for user_number, user_records in assignments.items():
        if len(user_records) != 5:
            raise ValueError(f"User {user_number} was assigned {len(user_records)} samples instead of 5.")

    # Verify constraint is satisfied
    for user_number, count in no_response_count.items():
        if count < 2:
            raise ValueError(
                f"User {user_number} only has {count} 'No' response samples, "
                f"but at least 2 are required. Not enough 'No' responses available in the CSV."
            )

    return assignments


def upsert_samples(
    file_path,
    num_users=10,
    replace_existing=False,
    clear_answers=False,
):
    app, db, AnnotationSample, Answer = get_app_objects()

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    print(f"Using database: {db_uri}")

    records, resolved_path = load_csv_records(file_path)
    print(f"Reading file: {resolved_path}")
    print(f"Loaded {len(records)} rows")

    assignments = build_user_assignments(records, num_users=num_users)

    upserted = 0

    with app.app_context():
        if replace_existing:
            deleted = AnnotationSample.query.delete()
            print(f"Deleted {deleted} existing samples before import")

        if clear_answers:
            deleted = Answer.query.delete()
            print(f"Deleted {deleted} user answers before import")

        for user_number, user_assignments in assignments.items():
            for sample_index, item in enumerate(user_assignments):
                record = item["record"]
                question = str(record.get("Question", ""))

                existing = AnnotationSample.query.filter_by(
                    user_number=user_number,
                    sample_index=sample_index,
                ).first()

                if existing:
                    existing.question = question
                    existing.payload = record
                else:
                    db.session.add(
                        AnnotationSample(
                            user_number=user_number,
                            sample_index=sample_index,
                            question=question,
                            payload=record,
                        )
                    )

                upserted += 1

        db.session.commit()

        total_rows = AnnotationSample.query.count()

    print(
        f"Done. Upserted {upserted} samples across {num_users} users "
        f"({len(next(iter(assignments.values()), []))} each)."
    )
    print(f"Total rows currently in annotation_sample: {total_rows}")

    for user_number in range(1, num_users + 1):
        depth_list = [item["depth"] for item in assignments[user_number]]
        bucket = "A" if user_number % 2 == 1 else "B"
        print(f"user{user_number} ({bucket}): depths {depth_list}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload depth-grouped CSV data into the annotation SQL database."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default="output-standard.csv",
        help="Path to the CSV file to import",
    )
    parser.add_argument(
        "--database-url",
        help="Optional DB URL override for this run (useful when running locally against Render Postgres).",
    )
    parser.add_argument("--num-users", type=int, default=10, help="Number of users to assign data to")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing annotation_sample rows before import",
    )
    parser.add_argument(
        "--clear-answers",
        action="store_true",
        help="Delete all user answers before import (starts fresh)",
    )

    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    upsert_samples(
        file_path=args.file_path,
        num_users=args.num_users,
        replace_existing=args.replace_existing,
        clear_answers=args.clear_answers,
    )


if __name__ == "__main__":
    main()
