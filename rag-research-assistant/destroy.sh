#!/usr/bin/env bash
# Delete everything (empties buckets first). Usage: ./destroy.sh [region] [stack-name]
set -euo pipefail
REGION="${1:-us-east-1}"; STACK="${2:-rag-research-assistant}"
out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
read -p "Delete stack $STACK and ALL data in $REGION? (yes/no) " ok; [ "$ok" = "yes" ] || exit 1
aws s3 rm "s3://$(out DocsBucketName)" --recursive --region "$REGION"
aws s3 rm "s3://$(out FrontendBucketName)" --recursive --region "$REGION"
aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION"
echo "Stack deleted."
