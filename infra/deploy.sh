#!/usr/bin/env bash
# One-shot Friday brain deploy to AWS GPU (EC2 + CloudFormation).
# NOT Lambda — Gemma 4 needs a GPU box (g5.xlarge).
#
# Prerequisites (one time):
#   1. aws configure   (or Cursor AWS MCP authenticated)
#   2. EC2 key pair    (friday-key)
#   3. Hugging Face token with Gemma access
#   4. GPU quota for G/VT instances in your region
#
# Usage:
#   HF_TOKEN=hf_xxx ./infra/deploy.sh
#   HF_TOKEN=hf_xxx GIT_REPO=https://github.com/YOU/FridayUGC.git ./infra/deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"
STACK="${FRIDAY_STACK:-friday-brain}"
KEY_NAME="${FRIDAY_KEY_NAME:-friday-key}"
INSTANCE_TYPE="${FRIDAY_INSTANCE_TYPE:-g5.xlarge}"
GEMMA_MODEL="${GEMMA_MODEL:-google/gemma-4-12b-it}"
GIT_REPO="${GIT_REPO:-https://github.com/MiguelBits/FridayUGC.git}"

# Windows Git Bash: pip-installed awscli may not be on PATH.
if command -v aws >/dev/null 2>&1; then
  AWS=(aws)
elif python -m awscli --version >/dev/null 2>&1; then
  AWS=(python -m awscli)
else
  echo "Install AWS CLI: python -m pip install awscli" >&2
  exit 1
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "Set HF_TOKEN=hf_xxx (Hugging Face token with Gemma license accepted)." >&2
  exit 1
fi

FRIDAY_API_TOKEN="${FRIDAY_API_TOKEN:-$(openssl rand -hex 24)}"
MY_IP="$("${AWS[@]}" ec2 describe-security-groups --region "$REGION" --query 'SecurityGroups[0].GroupId' >/dev/null 2>&1; curl -s --max-time 5 ifconfig.me || curl -s --max-time 5 icanhazip.com)"
MY_CIDR="${MY_IP}/32"

echo "==> Region:      $REGION"
echo "==> Stack:       $STACK"
echo "==> Key pair:    $KEY_NAME"
echo "==> Instance:    $INSTANCE_TYPE"
echo "==> Your IP:     $MY_CIDR"
echo "==> Git repo:    $GIT_REPO"
echo "==> API token:   $FRIDAY_API_TOKEN  (save this for the Android APK)"
echo ""

echo "==> Checking AWS credentials…"
"${AWS[@]}" sts get-caller-identity --region "$REGION" >/dev/null

echo "==> Deploying CloudFormation stack (10–20 min first boot after stack completes)…"
"${AWS[@]}" cloudformation deploy \
  --template-file "$ROOT/infra/cloudformation/friday-brain.yaml" \
  --stack-name "$STACK" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "KeyName=$KEY_NAME" \
    "MyIpCidr=$MY_CIDR" \
    "HfToken=$HF_TOKEN" \
    "FridayApiToken=$FRIDAY_API_TOKEN" \
    "GemmaModel=$GEMMA_MODEL" \
    "InstanceType=$INSTANCE_TYPE" \
    "GitRepoUrl=$GIT_REPO"

echo ""
echo "==> Stack outputs:"
"${AWS[@]}" cloudformation describe-stacks \
  --stack-name "$STACK" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table

echo ""
echo "Done. Wait ~20–40 min for Gemma download + docker on first boot."
echo "Then: curl http://YOUR_BRAIN_DNS:8080/health"
echo ""
echo "Build APK:"
echo "  cd android && ./gradlew assembleDebug -Pfriday.brainUrl=http://YOUR_BRAIN_DNS:8080 -Pfriday.apiToken=$FRIDAY_API_TOKEN"
