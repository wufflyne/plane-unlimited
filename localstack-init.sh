#!/bin/bash
# plane-unlimited: LocalStack init hook (runs once at "Ready").
# Create the S3 bucket Plane expects (AWS_S3_BUCKET_NAME=plane).
# Author: wufflyne <wufflyne@proton.me> — wufflyne.com
awslocal s3api create-bucket --bucket plane || true
echo "plane-unlimited: s3 bucket 'plane' ready"
