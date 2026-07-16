# AWS production deployment

This Terraform stack deploys the application on ECS Fargate behind an HTTPS
Application Load Balancer. It provisions Multi-AZ Amazon RDS PostgreSQL 16,
RDS Proxy, encrypted ElastiCache Redis, ECR, Secrets Manager, CloudWatch logs,
two or more API tasks, scalable Celery workers, and a singleton scheduler.
The Qwen checkpoint is not fetched from an API. It is stored once on encrypted
EFS and mounted read-only at `/models/qwen3` by API and worker tasks.

The VPC must have two public subnets for the ALB and at least two private
subnets with NAT egress for ECS, RDS, and Redis. Neo4j Aura and Qdrant Cloud are
supplied as private runtime secrets. The API does not keep session state in a
container, so Fargate tasks can scale horizontally.

Deployment order:

1. Copy `terraform.tfvars.example` to a secret, untracked `terraform.tfvars`.
2. Create ECR first with `terraform apply -target=aws_ecr_repository.app`, then
   authenticate Docker and push the image tagged `latest`.
3. Apply the complete Terraform stack.
4. Copy a complete Qwen3 checkpoint into the EFS access-point root before
   starting API/worker services. The directory must contain `config.json`,
   tokenizer files, and all local `safetensors` shards. The application uses
   `local_files_only=True` and will never download a missing checkpoint.
5. Run the `vlegal-migrate` task definition once in the private subnets.
6. Force a new deployment of the `api`, `worker`, and `beat` ECS services.
7. Point DNS at the ALB and register
   `https://<domain>/api/auth/google/callback` as an Authorized redirect URI in
   the Google Cloud OAuth client.

Database migrations are a separate one-off task. They are not executed by every
API replica, preventing concurrent migration races during autoscaling.

The default Fargate configuration runs Qwen3-4B on CPU with one model copy and
one generation at a time per task. For production latency, move the same image
and EFS mount to ECS on GPU-backed EC2 capacity, set `qwen_device = "cuda"` and
use `bfloat16` or `float16`; the application code remains unchanged.
