# Deployment Guide

This directory contains all deployment-related files for the Trading Platform production environment.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed
- Terraform >= 1.0
- Access to AWS account with appropriate permissions

## Directory Structure

```
deploy/
├── terraform/               # Infrastructure as Code
│   ├── main.tf             # Main Terraform configuration
│   ├── variables.tf        # Input variables
│   ├── outputs.tf          # Output values
│   └── modules/            # Terraform modules
│       ├── vpc/            # VPC and networking
│       ├── rds/            # PostgreSQL database
│       ├── elasticache/    # Redis cache
│       ├── ecs/            # ECS Fargate services
│       ├── s3/             # S3 buckets
│       ├── secrets/        # Secrets Manager
│       └── cloudfront/     # CDN for frontend
├── scripts/                # Utility scripts
├── Dockerfile.prod         # Production Dockerfile
├── run.sh                  # Main deployment script
└── .env                    # Environment variables (create from template)
```

## Quick Start

### 1. Initial Setup

```bash
# Copy environment template
cp ../docs/env.production.template .env

# Edit .env with your values
vim .env

# Select AWS profile
./run.sh profile

# Initialize Terraform
./run.sh tf-init
```

### 2. Deploy Infrastructure

```bash
# Plan infrastructure changes
./run.sh tf-plan

# Review the plan, then apply
./run.sh tf-apply
```

This will create:
- VPC with public/private subnets across 2 AZs
- RDS PostgreSQL (Multi-AZ)
- ElastiCache Redis
- ECS Fargate cluster
- Application Load Balancer
- S3 buckets for frontend and reports
- CloudFront distribution
- Secrets Manager for sensitive data

### 3. Deploy Application

```bash
# Build, push, and deploy in one command
./run.sh deploy

# Or step by step:
./run.sh build           # Build Docker images
./run.sh push            # Push to ECR
./run.sh deploy-ecs      # Update ECS services
```

## Script Commands

### Build & Deploy

```bash
# Build Docker images
./run.sh build

# Push images to ECR
./run.sh push

# Build and push
./run.sh build-push

# Full deployment (build + push + deploy)
./run.sh deploy
```

### Infrastructure Management

```bash
# Initialize Terraform
./run.sh tf-init

# Plan changes
./run.sh tf-plan

# Apply changes
./run.sh tf-apply

# Destroy all infrastructure (⚠️ DANGEROUS)
./run.sh destroy
```

### Monitoring & Debugging

```bash
# Get ECS service status
./run.sh status

# View logs for a service
./run.sh logs api      # API service
./run.sh logs worker   # Celery worker
./run.sh logs beat     # Celery beat

# SSH into EC2 instance (if applicable)
./run.sh ssh trading-worker
```

## Environment Variables

Key environment variables (stored in `.env`):

- **AWS Configuration**
  - `AWS_REGION`: AWS region (default: us-east-1)
  - `AWS_PROFILE`: AWS CLI profile to use

- **Database**
  - `DATABASE_URL`: PostgreSQL connection string
  - `DB_USER`, `DB_PASSWORD`: Database credentials

- **Redis**
  - `REDIS_URL`: Redis connection string

- **API Keys** (stored in AWS Secrets Manager)
  - `OPENAI_API_KEY`
  - `FINNHUB_API_KEY`
  - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
  - `JWT_SECRET`

- **ECS**
  - `ECS_CLUSTER_NAME`: ECS cluster name
  - `ECS_SERVICE_API`: API service name
  - `ECS_SERVICE_WORKER`: Worker service name
  - `ECS_SERVICE_BEAT`: Beat service name

## CI/CD with GitHub Actions

The project includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that automatically:

1. Runs tests on push to `main`
2. Builds Docker images
3. Pushes to ECR
4. Deploys frontend to S3/CloudFront
5. Updates ECS services
6. Verifies deployment

### Required Secrets

Add these secrets to your GitHub repository:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `S3_FRONTEND_BUCKET`
- `CLOUDFRONT_DISTRIBUTION_ID`

## Manual Deployment Steps

### First-Time Setup

1. **Create S3 bucket for Terraform state**
   ```bash
   aws s3 mb s3://trading-platform-terraform-state
   aws s3api put-bucket-versioning \
     --bucket trading-platform-terraform-state \
     --versioning-configuration Status=Enabled
   ```

2. **Create DynamoDB table for state locking**
   ```bash
   aws dynamodb create-table \
     --table-name terraform-state-lock \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST
   ```

3. **Store secrets in AWS Secrets Manager**
   ```bash
   aws secretsmanager create-secret \
     --name trading-platform/prod/openai \
     --secret-string '{"api_key":"sk-..."}'
   
   aws secretsmanager create-secret \
     --name trading-platform/prod/finnhub \
     --secret-string '{"api_key":"..."}'
   
   # Repeat for other secrets
   ```

4. **Deploy infrastructure**
   ```bash
   cd terraform
   terraform init
   terraform plan
   terraform apply
   ```

5. **Build and push images**
   ```bash
   cd ..
   ./run.sh build-push
   ```

6. **Deploy to ECS**
   ```bash
   ./run.sh deploy-ecs
   ```

### Database Migrations

```bash
# SSH into ECS task or run locally with production DB
docker exec -it trading-backend bash

# Run migrations
alembic upgrade head
```

### Updating Services

```bash
# After code changes, build new images
./run.sh build-push

# Update ECS services (zero-downtime deployment)
./run.sh deploy-ecs
```

## Monitoring

- **CloudWatch Logs**: `/ecs/trading-api`, `/ecs/trading-worker`, `/ecs/trading-beat`
- **CloudWatch Metrics**: ECS service metrics, RDS metrics, ElastiCache metrics
- **Application Logs**: Check ECS task logs via `./run.sh logs [service]`

## Cost Optimization

Estimated monthly costs (us-east-1):

- **RDS (db.t3.medium)**: ~$60
- **ElastiCache (cache.t3.medium)**: ~$50
- **ECS Fargate**: ~$100-200 (depends on usage)
- **ALB**: ~$20
- **NAT Gateway**: ~$30-60 (per AZ)
- **Data transfer**: Variable
- **Total**: ~$260-390/month

### Reduce Costs

- Use smaller RDS/Redis instances for non-prod
- Single AZ for dev/staging
- Reduce ECS task count during off-hours
- Use scheduled scaling

## Troubleshooting

### Deployment Fails

```bash
# Check ECS service events
aws ecs describe-services \
  --cluster trading-platform-prod \
  --services trading-api

# Check task logs
./run.sh logs api
```

### Database Connection Issues

```bash
# Verify security groups allow traffic from ECS tasks
# Check RDS endpoint in .env matches actual endpoint
aws rds describe-db-instances --db-instance-identifier trading-db-prod
```

### High Costs

```bash
# Check running tasks
./run.sh status

# Scale down if needed
aws ecs update-service \
  --cluster trading-platform-prod \
  --service trading-worker \
  --desired-count 1
```

## Rollback

```bash
# Rollback to previous task definition
PREVIOUS_TASK_DEF=$(aws ecs describe-services \
  --cluster trading-platform-prod \
  --services trading-api \
  --query 'services[0].taskDefinition' \
  --output text | sed 's/:2$/:1/')

aws ecs update-service \
  --cluster trading-platform-prod \
  --service trading-api \
  --task-definition $PREVIOUS_TASK_DEF
```

## Security Best Practices

1. **Never commit secrets** - Use AWS Secrets Manager
2. **Use IAM roles** - Avoid hardcoded credentials
3. **Enable encryption** - RDS encryption at rest, SSL/TLS in transit
4. **Restrict security groups** - Minimum required access
5. **Enable CloudTrail** - Audit all API calls
6. **Regular updates** - Keep dependencies updated
7. **MFA for AWS** - Require MFA for production access

## Support

For issues:
1. Check CloudWatch logs
2. Review ECS service events
3. Verify environment variables
4. Check AWS service health dashboard
5. Contact team lead

---

**Last Updated**: October 2025  
**Maintained By**: DevOps Team

