# AWS Deploy — Gemma 4 brain on GPU

You'll run **Gemma 4** on a GPU EC2 instance via **vLLM**, with the Friday FastAPI brain in front.
Uses your AWS GPU credits.

## Prerequisites

- AWS CLI configured (`aws configure`) with permission to create EC2 + security groups.
- An EC2 **key pair** (for SSH).
- A **Hugging Face token** with access to the Gemma weights (accept the license on HF first).
- Your **public IP** (`curl -s ifconfig.me`) for the security-group lock-down.
- A **GPU quota** for `g` instances in your region (request via Service Quotas if needed).

## Model / instance sizing

| Model | Min GPU | Instance | Notes |
|-------|--------|----------|-------|
| Gemma 4 E4B / small | 24 GB | g5.xlarge (A10G) | cheapest, good for the agent loop |
| Gemma 4 12B-it | 24 GB | g5.xlarge | fine at 8k ctx; bump to g5.2xlarge for headroom |
| Gemma 4 26B/31B | 48 GB+ | g5.12xlarge / multi-GPU | only if you need max quality |

## One-command deploy (recommended)

```bash
HF_TOKEN=hf_xxx ./infra/deploy.sh
```

Or manually:

```bash
aws cloudformation deploy \
  --template-file infra/cloudformation/friday-brain.yaml \
  --stack-name friday-brain \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    KeyName=YOUR_EC2_KEYPAIR \
    MyIpCidr=$(curl -s ifconfig.me)/32 \
    HfToken=hf_xxx \
    FridayApiToken=$(openssl rand -hex 24) \
    GemmaModel=google/gemma-4-12b-it \
    InstanceType=g5.xlarge \
    GitRepoUrl=https://github.com/MiguelBits/FridayUGC.git
```

Get the URL + token:

```bash
aws cloudformation describe-stacks --stack-name friday-brain \
  --query "Stacks[0].Outputs" --output table
```

## Manual deploy (if you prefer SSH over CloudFormation)

```bash
# on a GPU box with Docker + NVIDIA toolkit (Deep Learning AMI has these):
git clone https://github.com/YOUR_GH_USER/FridayUGC.git && cd FridayUGC/infra
printf 'HF_TOKEN=hf_xxx\nGEMMA_MODEL=google/gemma-4-12b-it\nVLLM_API_KEY=friday-local-key\nFRIDAY_API_TOKEN=%s\n' "$(openssl rand -hex 24)" > .env
docker compose --env-file .env up -d --build
curl -s localhost:8080/health
```

## Cost control (important)

- GPU instances bill by the hour whether idle or not. **Stop the instance** when not in use:
  `aws ec2 stop-instances --instance-ids i-xxxx`.
- Consider an auto-stop Lambda on an idle CloudWatch alarm.
- First model load downloads several GB from HF (one-time, cached on the EBS volume).

## Security

- The template restricts SSH + API to **your IP only**. Keep it that way.
- Put the brain behind HTTPS (Caddy/nginx + Let's Encrypt, or an ALB) before using on mobile data.
- Rotate `FridayApiToken` if it leaks; update the APK build arg and rebuild.
