#!/usr/bin/env python3
"""
Upload parquet samples to the annotation database.

This script assigns non-overlapping chunks from a parquet file to users:
- user 1 gets rows [start_row, start_row + samples_per_user)
- user 2 gets the next chunk, and so on.

It upserts by (user_number, sample_index), so it can be rerun safely.
"""

import argparse
import importlib
import os


def get_app_objects():
    from app import app, db, AnnotationSample
    return app, db, AnnotationSample


def upsert_samples(
    parquet_path,
    num_users=10,
    samples_per_user=20,
    start_row=0,
    replace_existing=False,
):
    pq = importlib.import_module("pyarrow.parquet")
    app, db, AnnotationSample = get_app_objects()

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    print(f"Using database: {db_uri}")
    print(f"Reading parquet file: {parquet_path}")
    table = pq.read_table(parquet_path)
    all_records = table.to_pylist()

    required = num_users * samples_per_user
    end_row = start_row + required

    if len(all_records) < end_row:
        raise ValueError(
            f"Parquet has {len(all_records)} rows, but {required} rows are needed from start_row={start_row}."
        )

    records = all_records[start_row:end_row]

    upserted = 0

    with app.app_context():
        if replace_existing:
            deleted = AnnotationSample.query.delete()
            print(f"Deleted {deleted} existing samples before import")

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
    parser = argparse.ArgumentParser(description="Upload parquet data into annotation Postgres/SQL database.")
    parser.add_argument("parquet_path", help="Path to parquet file")
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

    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    upsert_samples(
        parquet_path=args.parquet_path,
        num_users=args.num_users,
        samples_per_user=args.samples_per_user,
        start_row=args.start_row,
        replace_existing=args.replace_existing,
    )


if __name__ == "__main__":
    main()
