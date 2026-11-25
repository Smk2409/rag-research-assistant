#!/usr/bin/env bash
# One-command deployment: backend (SAM) + frontend (S3/CloudFront).
# Usage: ./deploy.sh [region] [stack-name]      Optional env: ALERT_EMAIL, MODEL_ID, ENABLE_OCR
set -euo pipefail
REGION="${1:-us-east-1}"; STACK="${2:-rag-research-assistant}"
OVERRIDES="ProjectName=$STACK EnableOcr=${ENABLE_OCR:-true}"
[ -n "${ALERT_EMAIL:-}" ] && OVERRIDES="$OVERRIDES AlertEmail=$ALERT_EMAIL"
[ -n "${MODEL_ID:-}" ]    && OVERRIDES="$OVERRIDES GenerationModelId=$MODEL_ID"

echo "==> Running unit tests"; python -m pytest tests -q
echo "==> Building and deploying backend to $REGION (stack: $STACK)"
sam build
sam deploy --stack-name "$STACK" --region "$REGION" --resolve-s3 --capabilities CAPABILITY_IAM \
  --no-confirm-changeset --no-fail-on-empty-changeset --parameter-overrides $OVERRIDES

out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }

echo "==> Writing frontend/config.js"
cat > frontend/config.js <<CFG
window.APP_CONFIG = { region: "$REGION", apiUrl: "$(out ApiUrl)", clientId: "$(out UserPoolClientId)" };
CFG
echo "==> Uploading frontend"
aws s3 sync frontend "s3://$(out FrontendBucketName)" --region "$REGION" --delete
echo; echo "Deployed!  Open: $(out WebsiteUrl)"
echo "Dashboard: CloudWatch -> Dashboards -> $(out DashboardName)"
