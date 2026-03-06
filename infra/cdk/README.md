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

Scaffold a new env/agent entry (for example, `clinicas.kaax.ai`):

```bash
./ops/env-create.sh dev clinicas clinicas.kaax.ai
```

Optional: create empty secret in AWS immediately:

```bash
CREATE_SECRET=true ./ops/env-create.sh dev clinicas clinicas.kaax.ai
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
./ops/awsctl.sh dns-config dev default api.kaax.ai
```

## 4) Deploy a new agent

Example: `dev/clinicas` with `clinicas.kaax.ai`.

```bash
./ops/env-create.sh dev clinicas clinicas.kaax.ai
export CDK_SECRET_NAME=kaax/dev/clinicas
./ops/secrets-sync.sh
./ops/diff.sh dev clinicas
./ops/deploy.sh dev clinicas
./ops/awsctl.sh dns-config dev clinicas clinicas.kaax.ai
```

Example `config/environments.json` entry (pre-filled, change only placeholders):

```json
{
  "dev": {
    "account": "301782007691",
    "region": "us-east-1",
    "agents": {
      "clinicas": {
        "service_name": "kaax-dev-clinicas",
        "cpu": 512,
        "memory_mib": 1024,
        "cpu_architecture": "X86_64",
        "desired_count": 1,
        "min_capacity": 1,
        "max_capacity": 2,
        "container_port": 8200,
        "health_check_path": "/health/live",
        "deregistration_delay_seconds": 30,
        "public_load_balancer": true,
        "enable_https": true,
        "redirect_http": true,
        "certificate_arn": "<CAMBIAR_ACM_CERT_ARN>",
        "public_base_url": "https://clinicas.kaax.ai",
        "environment": {
          "AUDRAI_DEPLOY_ENV": "dev",
          "AGENT_RUNTIME_BACKEND": "langgraph_mvp",
          "CHECKPOINT_BACKEND": "postgres",
          "CRM_BACKEND": "postgres",
          "INTERACTION_METRICS_BACKEND": "postgres",
          "KNOWLEDGE_BACKEND": "postgres",
          "KNOWLEDGE_TABLE_NAME": "agent_knowledge",
          "LOG_FORMAT": "json",
          "LOG_LEVEL": "INFO",
          "MULTI_AGENT_ENABLED": "true",
          "DEMO_LINK": "<CAMBIAR_LINK_DEMO>",
          "PRICING_LINK": "<CAMBIAR_LINK_PRECIOS>",
          "WHATSAPP_NOTIFY_TO": "<CAMBIAR_NUMERO_DESTINO>"
        },
        "secret_name": "kaax/dev/clinicas",
        "secret_keys": [
          "API_TOKENS",
          "DATABASE_URL",
          "AWS_REGION",
          "BEDROCK_MODEL",
          "DEFAULT_PROMPT_NAME",
          "WHATSAPP_META_VERIFY_TOKEN",
          "WHATSAPP_META_APP_SECRET",
          "WHATSAPP_META_ACCESS_TOKEN",
          "WHATSAPP_META_PHONE_NUMBER_ID"
        ]
      }
    }
  }
}
```

Minimal fields to change:
- `certificate_arn`
- `DEMO_LINK`
- `PRICING_LINK`
- `WHATSAPP_NOTIFY_TO`
- `secret_name` (if you want a different path)

What `dns-config` gives you:
- `LoadBalancerDNS` from CloudFormation outputs
- ready-to-copy CNAME fields (host/target/ttl) for your DNS manager

## 5) Considerations

- `public_base_url` is metadata/output; DNS is still manual (or Route53 separately).
- Keep one secret per agent (`kaax/<env>/<agent>`).
- Use modern secret keys only for new agents.
- Ensure ACM certificate includes the final hostname when HTTPS is enabled.
- Different agents can run in same account/region while staying runtime-isolated.

## 6) Secrets strategy

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
