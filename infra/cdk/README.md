# CDK deploy (ECS Fargate)

This module deploys `kaax-ai` to AWS using CDK.

## 1) Prepare config

```bash
cd infra/cdk
cp config/environments.example.json config/environments.json
```

Edit `config/environments.json`:
- AWS account/region
- per-agent service name and sizing
- `cpu_architecture` (`X86_64` default, or `ARM64` to match ARM images)
- `enable_https=true` + `certificate_arn` (ACM) if you want TLS on ALB
- optional `public_base_url` (recommended when using custom domain)
- environment variables
- `secret_name` (recommended) or `secret_arn`, and `secret_keys`

## 2) Bootstrap and deploy

From repository root:

```bash
./ops/bootstrap.sh
./ops/deploy.sh dev default
```

Deploy another agent in same env:

```bash
./ops/deploy.sh dev sales
```

Override secret mapping from shell env (no JSON edit):

```bash
export CDK_SECRET_NAME=kaax/dev/default
export CDK_SECRET_KEYS=API_TOKENS,DATABASE_URL,AWS_REGION,BEDROCK_MODEL,DEFAULT_PROMPT_NAME,WHATSAPP_META_VERIFY_TOKEN,WHATSAPP_META_APP_SECRET,WHATSAPP_META_ACCESS_TOKEN,WHATSAPP_META_PHONE_NUMBER_ID
./ops/deploy.sh dev default
```

## 3) Useful commands

```bash
./ops/diff.sh dev default
./ops/destroy.sh dev default
```

## 4) Secrets strategy

Keep runtime secrets in one Secrets Manager secret JSON per agent, for example:

```json
{
  "API_TOKENS": "token-1,token-2",
  "DATABASE_URL": "postgresql://...",
  "BEDROCK_MODEL": "amazon.nova-lite-v1:0",
  "WHATSAPP_META_ACCESS_TOKEN": "...",
  "WHATSAPP_META_APP_SECRET": "...",
  "WHATSAPP_META_VERIFY_TOKEN": "...",
  "WHATSAPP_META_PHONE_NUMBER_ID": "1234567890"
}
```

Then list those keys in `secret_keys` for that agent.

You can sync from your current shell exports:

```bash
export CDK_SECRET_NAME=kaax/dev/default
export CDK_SECRET_KEYS=API_TOKENS,DATABASE_URL,AWS_REGION,BEDROCK_MODEL,DEFAULT_PROMPT_NAME,WHATSAPP_META_VERIFY_TOKEN,WHATSAPP_META_APP_SECRET,WHATSAPP_META_ACCESS_TOKEN,WHATSAPP_META_PHONE_NUMBER_ID
./ops/secrets-sync.sh
```

Note:
- Prefer `secret_name` to avoid ARN suffix issues.
- If you use `secret_arn`, partial ARN is supported.
