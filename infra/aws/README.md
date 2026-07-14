# AWS production deployment

This Terraform stack deploys the application on ECS Fargate behind an HTTPS
Application Load Balancer. It provisions Multi-AZ Amazon RDS PostgreSQL 16,
RDS Proxy, encrypted ElastiCache Redis, ECR, Secrets Manager, CloudWatch logs,
two or more API tasks, scalable Celery workers, and a singleton scheduler.

The VPC must have two public subnets for the ALB and at least two private
subnets with NAT egress for ECS, RDS, and Redis. Neo4j Aura and Qdrant Cloud are
supplied as private runtime secrets. The API does not keep session state in a
container, so Fargate tasks can scale horizontally.

Deployment order:

1. Copy `terraform.tfvars.example` to a secret, untracked `terraform.tfvars`.
2. Create ECR first with `terraform apply -target=aws_ecr_repository.app`, then
   authenticate Docker and push the image tagged `latest`.
3. Apply the complete Terraform stack.
4. Run the `vlegal-migrate` task definition once in the private subnets.
5. Force a new deployment of the `api`, `worker`, and `beat` ECS services.
6. Point DNS at the ALB and register
   `https://<domain>/api/auth/google/callback` as an Authorized redirect URI in
   the Google Cloud OAuth client.

Database migrations are a separate one-off task. They are not executed by every
API replica, preventing concurrent migration races during autoscaling.
