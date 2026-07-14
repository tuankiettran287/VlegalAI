data "aws_caller_identity" "current" {}

locals {
  db_name     = "vlegal"
  db_username = "vlegal_admin"
  redis_url   = "rediss://:${urlencode(random_password.redis.result)}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379"
  common_environment = [
    { name = "APP_ENV", value = "production" },
    { name = "PUBLIC_URL", value = var.public_url },
    { name = "FRONTEND_URL", value = var.public_url },
    { name = "CORS_ORIGINS", value = var.public_url },
    { name = "COOKIE_SECURE", value = "true" },
    { name = "RETRIEVER_BACKEND", value = "hybrid_rag" },
    { name = "REQUIRE_FRESHNESS_CHECK", value = "true" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "WEB_CONCURRENCY", value = "2" },
  ]
  secret_keys = [
    "DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND",
    "SESSION_SECRET", "MESSAGE_ENCRYPTION_KEY", "OIDC_ISSUER", "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI", "QWEN_API_KEY", "TAVILY_API_KEY",
    "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "QDRANT_URL", "QDRANT_API_KEY"
  ]
  container_secrets = [for key in local.secret_keys : {
    name      = key
    valueFrom = "${aws_secretsmanager_secret.runtime.arn}:${key}::"
  }]
}

resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "_-"
}
resource "random_password" "redis" {
  length  = 32
  special = false
}
resource "random_password" "session" {
  length  = 64
  special = false
}
resource "random_password" "encryption" {
  length  = 43
  special = false
}

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{
    rulePriority = 1
    description  = "Keep the most recent 30 images"
    selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30 }
    action       = { type = "expire" }
  }] })
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  vpc_id      = var.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "${var.name}-ecs-"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name_prefix = "${var.name}-db-"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id, aws_security_group.proxy.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "proxy" {
  name_prefix = "${var.name}-proxy-"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "redis" {
  name_prefix = "${var.name}-redis-"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}
resource "aws_db_parameter_group" "main" {
  name_prefix = "${var.name}-pg16-"
  family      = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

resource "aws_db_instance" "postgres" {
  identifier                     = "${var.name}-postgres"
  engine                         = "postgres"
  engine_version                 = "16"
  instance_class                 = var.db_instance_class
  allocated_storage              = var.db_allocated_storage
  max_allocated_storage          = var.db_allocated_storage * 5
  storage_type                   = "gp3"
  storage_encrypted              = true
  db_name                        = local.db_name
  username                       = local.db_username
  password                       = random_password.db.result
  port                           = 5432
  multi_az                       = true
  publicly_accessible            = false
  db_subnet_group_name           = aws_db_subnet_group.main.name
  vpc_security_group_ids         = [aws_security_group.db.id]
  parameter_group_name           = aws_db_parameter_group.main.name
  backup_retention_period        = 14
  backup_window                  = "18:00-19:00"
  maintenance_window             = "sun:19:00-sun:20:00"
  performance_insights_enabled   = true
  monitoring_interval            = 60
  monitoring_role_arn            = aws_iam_role.rds_monitoring.arn
  deletion_protection            = true
  skip_final_snapshot            = false
  final_snapshot_identifier      = "${var.name}-final-snapshot"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  lifecycle { prevent_destroy = true }
}

resource "aws_iam_role" "rds_monitoring" {
  name_prefix = "${var.name}-rds-monitoring-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "monitoring.rds.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_secretsmanager_secret" "db" { name = "${var.name}/database" }
resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({ username = local.db_username, password = random_password.db.result })
}

resource "aws_iam_role" "proxy" {
  name_prefix = "${var.name}-rds-proxy-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "rds.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "proxy" {
  role = aws_iam_role.proxy.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.db.arn }] })
}
resource "aws_db_proxy" "main" {
  name                   = var.name
  debug_logging          = false
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  role_arn               = aws_iam_role.proxy.arn
  vpc_security_group_ids = [aws_security_group.proxy.id]
  vpc_subnet_ids         = var.private_subnet_ids
  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.db.arn
  }
}
resource "aws_db_proxy_default_target_group" "main" {
  db_proxy_name = aws_db_proxy.main.name
  connection_pool_config {
    connection_borrow_timeout    = 30
    max_connections_percent      = 90
    max_idle_connections_percent = 50
  }
}
resource "aws_db_proxy_target" "main" {
  db_instance_identifier = aws_db_instance.postgres.identifier
  db_proxy_name          = aws_db_proxy.main.name
  target_group_name      = aws_db_proxy_default_target_group.main.name
}

resource "aws_elasticache_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}
resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = var.name
  description                = "VLegal distributed locks, cache and Celery broker"
  node_type                  = "cache.r7g.large"
  num_cache_clusters         = 2
  engine                     = "redis"
  engine_version             = "7.1"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]
  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis.result
  snapshot_retention_limit   = 7
  apply_immediately          = false
}

resource "aws_secretsmanager_secret" "runtime" { name = "${var.name}/runtime" }
resource "aws_secretsmanager_secret_version" "runtime" {
  secret_id = aws_secretsmanager_secret.runtime.id
  secret_string = jsonencode({
    DATABASE_URL           = "postgresql+asyncpg://${local.db_username}:${urlencode(random_password.db.result)}@${aws_db_proxy.main.endpoint}:5432/${local.db_name}?ssl=require"
    REDIS_URL              = "${local.redis_url}/0"
    CELERY_BROKER_URL      = "${local.redis_url}/1"
    CELERY_RESULT_BACKEND  = "${local.redis_url}/2"
    SESSION_SECRET         = random_password.session.result
    MESSAGE_ENCRYPTION_KEY = random_password.encryption.result
    OIDC_ISSUER            = var.oidc_issuer
    OIDC_CLIENT_ID         = var.oidc_client_id
    OIDC_CLIENT_SECRET     = var.oidc_client_secret
    OIDC_REDIRECT_URI      = "${var.public_url}/api/auth/google/callback"
    QWEN_API_KEY           = var.qwen_api_key
    TAVILY_API_KEY         = var.tavily_api_key
    NEO4J_URI              = var.neo4j_uri
    NEO4J_USER             = var.neo4j_user
    NEO4J_PASSWORD         = var.neo4j_password
    QDRANT_URL             = var.qdrant_url
    QDRANT_API_KEY         = var.qdrant_api_key
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}/api"
  retention_in_days = 30
}
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name}/worker"
  retention_in_days = 30
}
resource "aws_ecs_cluster" "main" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_iam_role" "ecs_execution" {
  name_prefix = "${var.name}-ecs-execution-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "ecs_secrets" {
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn }] })
}
resource "aws_iam_role" "ecs_task" {
  name_prefix = "${var.name}-ecs-task-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_lb" "main" {
  name               = var.name
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
}
resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  deregistration_delay = 30
  health_check {
    path                = "/api/health/ready"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 20
    timeout             = 5
    matcher             = "200"
  }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port = 80
  protocol = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port = 443
  protocol = "HTTPS"
  ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_task_definition" "api" {
  depends_on = [aws_secretsmanager_secret_version.runtime]
  family = "${var.name}-api"
  network_mode = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu = 2048
  memory = 4096
  execution_role_arn = aws_iam_role.ecs_execution.arn
  task_role_arn = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name = "api", image = "${aws_ecr_repository.app.repository_url}:${var.image_tag}", essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = local.common_environment
    secrets = local.container_secrets
    healthCheck = { command = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live')\""], interval = 30, timeout = 5, retries = 3, startPeriod = 45 }
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.api.name, "awslogs-region" = var.aws_region, "awslogs-stream-prefix" = "api" } }
  }])
}

resource "aws_ecs_service" "api" {
  name = "api"
  cluster = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count = var.api_min_tasks
  launch_type = "FARGATE"
  platform_version = "LATEST"
  enable_execute_command = true
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent = 200
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_task_definition" "worker" {
  depends_on = [aws_secretsmanager_secret_version.runtime]
  family = "${var.name}-worker"
  network_mode = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu = 2048
  memory = 4096
  execution_role_arn = aws_iam_role.ecs_execution.arn
  task_role_arn = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name = "worker", image = "${aws_ecr_repository.app.repository_url}:${var.image_tag}", essential = true
    command = ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=4"]
    environment = local.common_environment
    secrets = local.container_secrets
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.worker.name, "awslogs-region" = var.aws_region, "awslogs-stream-prefix" = "worker" } }
  }])
}
resource "aws_ecs_service" "worker" {
  name = "worker"
  cluster = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count = var.worker_min_tasks
  launch_type = "FARGATE"
  platform_version = "LATEST"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_task_definition" "beat" {
  depends_on = [aws_secretsmanager_secret_version.runtime]
  family                   = "${var.name}-beat"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name        = "beat"
    image       = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential   = true
    command     = ["celery", "-A", "app.worker.celery_app", "beat", "--loglevel=INFO"]
    environment = local.common_environment
    secrets     = local.container_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "beat"
      }
    }
  }])
}

resource "aws_ecs_service" "beat" {
  name             = "beat"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.beat.arn
  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "LATEST"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_task_definition" "migrate" {
  depends_on = [aws_secretsmanager_secret_version.runtime]
  family                   = "${var.name}-migrate"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  container_definitions = jsonencode([{
    name        = "migrate"
    image       = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential   = true
    command     = ["alembic", "upgrade", "head"]
    environment = local.common_environment
    secrets     = local.container_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])
}

resource "aws_appautoscaling_target" "api" {
  max_capacity = var.api_max_tasks
  min_capacity = var.api_min_tasks
  resource_id = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace = "ecs"
}
resource "aws_appautoscaling_policy" "api_cpu" {
  name = "${var.name}-api-cpu"
  policy_type = "TargetTrackingScaling"
  resource_id = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace = aws_appautoscaling_target.api.service_namespace
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 120
    scale_out_cooldown = 30
  }
}
resource "aws_appautoscaling_target" "worker" {
  max_capacity = var.worker_max_tasks
  min_capacity = var.worker_min_tasks
  resource_id = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace = "ecs"
}
resource "aws_appautoscaling_policy" "worker_cpu" {
  name = "${var.name}-worker-cpu"
  policy_type = "TargetTrackingScaling"
  resource_id = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace = aws_appautoscaling_target.worker.service_namespace
  target_tracking_scaling_policy_configuration {
    target_value = 65
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 180
    scale_out_cooldown = 30
  }
}
