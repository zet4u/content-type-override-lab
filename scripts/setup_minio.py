#!/usr/bin/env python3
"""Prepare the local MinIO for the lab, without mc.exe.

Creates the 'public' bucket, applies the anonymous download policy and
uploads the demo objects with their forced Content-Type. Idempotent:
safe to run on every lab start (and after 'docker compose down -v').
"""
import json
import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
ROOT_USER = os.environ.get("MINIO_ROOT_USER", "labadmin")
ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "labdev-only-change-me")
BUCKET = os.environ.get("BUCKET", "public")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OBJECTS = [
    (os.path.join("payloads", "avatar-payload.png"), "avatar-payload.png", "image/png"),
    (os.path.join("payloads", "secret-notes.txt"), "secret-notes.txt", "text/plain"),
]

ANONYMOUS_DOWNLOAD_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::%s/*" % BUCKET],
        }
    ],
}


def main():
    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ROOT_USER,
        aws_secret_access_key=ROOT_PASSWORD,
        config=Config(signature_version="s3v4", retries={"max_attempts": 10}),
        region_name="us-east-1",
    )

    try:
        s3.create_bucket(Bucket=BUCKET)
        print("[+] bucket '%s' created" % BUCKET)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print("[=] bucket '%s' already exists" % BUCKET)
        else:
            raise

    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(ANONYMOUS_DOWNLOAD_POLICY))
    print("[+] anonymous download policy applied")

    for relpath, key, content_type in OBJECTS:
        source = os.path.join(ROOT, relpath)
        if not os.path.isfile(source):
            print("[!] payload not found: %s" % source, file=sys.stderr)
            return 1
        s3.upload_file(
            source,
            BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        print("[+] uploaded %s (Content-Type: %s)" % (key, content_type))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[!] MinIO setup failed: %s" % e.__class__.__name__, file=sys.stderr)
        print("    Is MinIO running and healthy at %s ?" % ENDPOINT, file=sys.stderr)
        sys.exit(1)
