#!/usr/bin/env python3
"""
Upload CSV/parquet samples to the annotation database.

This script assigns non-overlapping chunks from a CSV or parquet file to users:
- user 1 gets rows [start_row, start_row + samples_per_user)
- user 2 gets the next chunk, and so on.

It upserts by (user_number, sample_index), so it can be rerun safely.
"""

import argparse
import importlib
import os
import csv


def get_app_objects():
    from app import app, db, AnnotationSample, Answer
    return app, db, AnnotationSample, Answer


def upsert_samples(
    file_path,
    num_users=10,
    samples_per_user=20,
    start_row=0,
    replace_existing=False,
    clear_answers=False,
):
    app, db, AnnotationSample, Answer = get_app_objects()

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    print(f"Using database: {db_uri}")
    print(f"Reading file: {file_path}")
    
    # Determine file type and read accordingly
    if file_path.endswith('.csv'):
        all_records = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                all_records.append(row)
    elif file_path.endswith('.parquet'):
        pq = importlib.import_module("pyarrow.parquet")
        table = pq.read_table(file_path)
        all_records = table.to_pylist()
    else:
        raise ValueError("File must be .csv or .parquet")

    required = num_users * samples_per_user
    end_row = start_row + required

    if len(all_records) < end_row:
        raise ValueError(
            f"File has {len(all_records)} rows, but {required} rows are needed from start_row={start_row}."
        )

    records = all_records[start_row:end_row]

    upserted = 0

    with app.app_context():
        if replace_existing:
            deleted = AnnotationSample.query.delete()
            print(f"Deleted {deleted} existing samples before import")
        
        if clear_answers:
            deleted = Answer.query.delete()
            print(f"Deleted {deleted} user answers before import")

        for user_number in range(1, num_users + 1):
            base = (user_number - 1) * samples_per_user

            for sample_index in range(samples_per_user):
                record = records[base + sample_index]
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
        f"({samples_per_user} each)."
    )
    print(f"Total rows currently in annotation_sample: {total_rows}")


def main():
    parser = argparse.ArgumentParser(description="Upload CSV/parquet data into annotation Postgres/SQL database.")
    parser.add_argument("file_path", help="Path to CSV or parquet file")
    parser.add_argument(
        "--database-url",
        help="Optional DB URL override for this run (useful when running locally against Render Postgres).",
    )
    parser.add_argument("--num-users", type=int, default=10, help="Number of users to assign data to")
    parser.add_argument(
        "--samples-per-user",
        type=int,
        default=20,
        help="Number of samples per user",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=0,
        help="Start row in parquet from which assignment begins",
    )
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
        samples_per_user=args.samples_per_user,
        start_row=args.start_row,
        replace_existing=args.replace_existing,
        clear_answers=args.clear_answers,
    )


if __name__ == "__main__":
    main()
