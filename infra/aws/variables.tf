variable "aws_region" {
  type    = string
  default = "ap-southeast-1"
}
variable "name" {
  type    = string
  default = "vlegal"
}
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "certificate_arn" { type = string }
variable "public_url" { type = string }
variable "oidc_issuer" {
  type        = string
  description = "Google OIDC issuer; use https://accounts.google.com"
  validation {
    condition     = trimsuffix(var.oidc_issuer, "/") == "https://accounts.google.com"
    error_message = "oidc_issuer must be https://accounts.google.com."
  }
}
variable "oidc_client_id" {
  type      = string
  sensitive = true
}
variable "oidc_client_secret" {
  type      = string
  sensitive = true
}
variable "qwen_model" {
  type    = string
  default = "Qwen3-4B"
}
variable "qwen_device" {
  type    = string
  default = "cpu"
  validation {
    condition     = contains(["auto", "cuda", "cpu"], var.qwen_device)
    error_message = "qwen_device must be auto, cuda, or cpu."
  }
}
variable "qwen_dtype" {
  type    = string
  default = "auto"
  validation {
    condition     = contains(["auto", "bfloat16", "float16", "float32"], var.qwen_dtype)
    error_message = "qwen_dtype must be auto, bfloat16, float16, or float32."
  }
}
variable "tavily_api_key" {
  type      = string
  sensitive = true
}
variable "neo4j_uri" { type = string }
variable "neo4j_user" {
  type    = string
  default = "neo4j"
}
variable "neo4j_password" {
  type      = string
  sensitive = true
}
variable "qdrant_url" { type = string }
variable "qdrant_api_key" {
  type      = string
  sensitive = true
}
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "db_instance_class" {
  type    = string
  default = "db.r7g.large"
}
variable "db_allocated_storage" {
  type    = number
  default = 100
}
variable "api_min_tasks" {
  type    = number
  default = 2
}
variable "api_max_tasks" {
  type    = number
  default = 20
}
variable "worker_min_tasks" {
  type    = number
  default = 2
}
variable "worker_max_tasks" {
  type    = number
  default = 20
}
variable "api_task_cpu" {
  type    = number
  default = 4096
}
variable "api_task_memory" {
  type    = number
  default = 16384
}
variable "worker_task_cpu" {
  type    = number
  default = 4096
}
variable "worker_task_memory" {
  type    = number
  default = 16384
}
variable "tags" {
  type = map(string)
  default = {
    Project   = "VLegalAI"
    ManagedBy = "Terraform"
  }
}
