# Main Terraform configuration for Trading Platform
# This creates all AWS resources for production deployment

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    bucket = "trading-platform-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "TradingPlatform"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# Modules
module "vpc" {
  source = "./modules/vpc"
  
  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "rds" {
  source = "./modules/rds"
  
  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  database_subnet_ids = module.vpc.database_subnet_ids
  db_instance_class   = var.db_instance_class
  db_name             = var.db_name
  db_username         = var.db_username
}

module "elasticache" {
  source = "./modules/elasticache"
  
  environment      = var.environment
  vpc_id           = module.vpc.vpc_id
  cache_subnet_ids = module.vpc.cache_subnet_ids
  node_type        = var.redis_node_type
}

module "ecs" {
  source = "./modules/ecs"
  
  environment          = var.environment
  vpc_id               = module.vpc.vpc_id
  private_subnet_ids   = module.vpc.private_subnet_ids
  public_subnet_ids    = module.vpc.public_subnet_ids
  
  # Pass DB and Redis endpoints
  database_endpoint    = module.rds.endpoint
  redis_endpoint       = module.elasticache.endpoint
  
  # ECS configuration
  api_desired_count    = var.api_desired_count
  worker_desired_count = var.worker_desired_count
  
  # Docker images
  api_image            = var.api_docker_image
  worker_image         = var.worker_docker_image
  beat_image           = var.beat_docker_image
}

module "s3" {
  source = "./modules/s3"
  
  environment = var.environment
}

module "secrets" {
  source = "./modules/secrets"
  
  environment = var.environment
}

module "cloudfront" {
  source = "./modules/cloudfront"
  
  environment     = var.environment
  frontend_bucket = module.s3.frontend_bucket_name
  api_domain      = module.ecs.api_domain
}

# Outputs
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "rds_endpoint" {
  value     = module.rds.endpoint
  sensitive = true
}

output "redis_endpoint" {
  value     = module.elasticache.endpoint
  sensitive = true
}

output "api_url" {
  value = module.ecs.api_url
}

output "frontend_url" {
  value = module.cloudfront.distribution_domain
}

output "ecr_repository_url" {
  value = module.ecs.ecr_repository_url
}

