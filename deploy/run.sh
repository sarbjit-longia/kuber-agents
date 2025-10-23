#!/bin/bash

# Deployment script for Trading Platform
# Usage: ./run.sh [command] [options]

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="trading-platform"
ENV_FILE=".env"

# Functions
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}➜ $1${NC}"
}

# Select AWS Profile
select_profile() {
    echo "Available AWS Profiles:"
    aws configure list-profiles
    echo ""
    read -p "Enter AWS profile name (or press Enter for default): " AWS_PROFILE
    export AWS_PROFILE=${AWS_PROFILE:-default}
    print_success "Using AWS profile: $AWS_PROFILE"
}

# Load environment variables
load_env() {
    if [ -f "$ENV_FILE" ]; then
        export $(cat $ENV_FILE | grep -v '^#' | xargs)
        print_success "Environment variables loaded from $ENV_FILE"
    else
        print_error "$ENV_FILE not found"
        exit 1
    fi
}

# Build Docker images
build_images() {
    print_info "Building Docker images..."
    
    cd ..
    
    # Build backend image
    print_info "Building backend image..."
    docker build -f deploy/Dockerfile.prod -t ${ECR_REPO_NAME}:latest .
    
    # Tag images
    docker tag ${ECR_REPO_NAME}:latest ${ECR_REPO_NAME}:api-latest
    docker tag ${ECR_REPO_NAME}:latest ${ECR_REPO_NAME}:worker-latest
    docker tag ${ECR_REPO_NAME}:latest ${ECR_REPO_NAME}:beat-latest
    
    print_success "Images built successfully"
    cd deploy
}

# Push Docker images to ECR
push_images() {
    print_info "Pushing images to ECR..."
    
    # Get AWS account ID
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Login to ECR
    print_info "Logging in to ECR..."
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URL}
    
    # Create ECR repository if it doesn't exist
    aws ecr describe-repositories --repository-names ${ECR_REPO_NAME} --region ${AWS_REGION} 2>/dev/null || \
        aws ecr create-repository --repository-name ${ECR_REPO_NAME} --region ${AWS_REGION}
    
    # Tag and push images
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    
    for service in api worker beat; do
        print_info "Pushing $service image..."
        docker tag ${ECR_REPO_NAME}:${service}-latest ${ECR_URL}/${ECR_REPO_NAME}:${service}-${TIMESTAMP}
        docker tag ${ECR_REPO_NAME}:${service}-latest ${ECR_URL}/${ECR_REPO_NAME}:${service}-latest
        
        docker push ${ECR_URL}/${ECR_REPO_NAME}:${service}-${TIMESTAMP}
        docker push ${ECR_URL}/${ECR_REPO_NAME}:${service}-latest
    done
    
    print_success "Images pushed successfully"
    echo "ECR_URL: ${ECR_URL}/${ECR_REPO_NAME}"
}

# Initialize Terraform
terraform_init() {
    print_info "Initializing Terraform..."
    cd terraform
    terraform init
    print_success "Terraform initialized"
    cd ..
}

# Plan Terraform changes
terraform_plan() {
    print_info "Planning Terraform changes..."
    cd terraform
    
    # Get ECR URL for image variables
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
    
    terraform plan \
        -var="api_docker_image=${ECR_URL}:api-latest" \
        -var="worker_docker_image=${ECR_URL}:worker-latest" \
        -var="beat_docker_image=${ECR_URL}:beat-latest" \
        -out=tfplan
    
    print_success "Terraform plan created"
    cd ..
}

# Apply Terraform changes
terraform_apply() {
    print_info "Applying Terraform changes..."
    cd terraform
    terraform apply tfplan
    print_success "Infrastructure deployed"
    cd ..
}

# Deploy to ECS (update services)
deploy_ecs() {
    print_info "Deploying to ECS..."
    
    CLUSTER_NAME="${ECS_CLUSTER_NAME:-trading-platform-prod}"
    
    for service in api worker beat; do
        SERVICE_NAME="trading-${service}"
        print_info "Updating ECS service: $SERVICE_NAME"
        
        aws ecs update-service \
            --cluster ${CLUSTER_NAME} \
            --service ${SERVICE_NAME} \
            --force-new-deployment \
            --region ${AWS_REGION}
    done
    
    print_success "ECS services updated"
}

# Get logs from ECS
get_logs() {
    SERVICE=${1:-api}
    CLUSTER_NAME="${ECS_CLUSTER_NAME:-trading-platform-prod}"
    
    print_info "Fetching logs for $SERVICE..."
    
    # Get task ARN
    TASK_ARN=$(aws ecs list-tasks \
        --cluster ${CLUSTER_NAME} \
        --service-name trading-${SERVICE} \
        --desired-status RUNNING \
        --query 'taskArns[0]' \
        --output text \
        --region ${AWS_REGION})
    
    if [ "$TASK_ARN" == "None" ]; then
        print_error "No running tasks found for service: $SERVICE"
        exit 1
    fi
    
    # Get log stream
    LOG_GROUP="/ecs/trading-${SERVICE}"
    
    print_info "Tailing logs from CloudWatch..."
    aws logs tail ${LOG_GROUP} --follow --region ${AWS_REGION}
}

# Get ECS service status
get_status() {
    CLUSTER_NAME="${ECS_CLUSTER_NAME:-trading-platform-prod}"
    
    print_info "ECS Service Status:"
    echo ""
    
    for service in api worker beat; do
        SERVICE_NAME="trading-${service}"
        
        STATUS=$(aws ecs describe-services \
            --cluster ${CLUSTER_NAME} \
            --services ${SERVICE_NAME} \
            --query 'services[0].[status,runningCount,desiredCount]' \
            --output text \
            --region ${AWS_REGION})
        
        echo "Service: $SERVICE_NAME"
        echo "  Status: $(echo $STATUS | awk '{print $1}')"
        echo "  Running: $(echo $STATUS | awk '{print $2}') / Desired: $(echo $STATUS | awk '{print $3}')"
        echo ""
    done
}

# SSH into EC2 (if using EC2 for Celery workers)
ssh_ec2() {
    INSTANCE_TAG=${1:-trading-worker}
    
    print_info "Finding EC2 instance with tag: $INSTANCE_TAG"
    
    INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=$INSTANCE_TAG" \
                  "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].InstanceId' \
        --output text \
        --region ${AWS_REGION})
    
    if [ "$INSTANCE_ID" == "None" ]; then
        print_error "No running instance found"
        exit 1
    fi
    
    print_info "Connecting to instance: $INSTANCE_ID"
    aws ssm start-session --target $INSTANCE_ID --region ${AWS_REGION}
}

# Destroy infrastructure
destroy() {
    read -p "Are you sure you want to destroy all infrastructure? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        print_info "Aborted"
        exit 0
    fi
    
    print_info "Destroying infrastructure..."
    cd terraform
    terraform destroy
    cd ..
    print_success "Infrastructure destroyed"
}

# Main command handler
case "$1" in
    profile)
        select_profile
        ;;
    build)
        select_profile
        build_images
        ;;
    push)
        select_profile
        load_env
        push_images
        ;;
    build-push)
        select_profile
        build_images
        load_env
        push_images
        ;;
    tf-init)
        select_profile
        terraform_init
        ;;
    tf-plan)
        select_profile
        terraform_plan
        ;;
    tf-apply)
        select_profile
        terraform_apply
        ;;
    deploy)
        select_profile
        build_images
        load_env
        push_images
        deploy_ecs
        print_success "Deployment complete!"
        ;;
    logs)
        select_profile
        get_logs $2
        ;;
    status)
        select_profile
        get_status
        ;;
    ssh)
        select_profile
        ssh_ec2 $2
        ;;
    destroy)
        select_profile
        destroy
        ;;
    *)
        echo "Trading Platform Deployment Script"
        echo ""
        echo "Usage: ./run.sh [command] [options]"
        echo ""
        echo "Commands:"
        echo "  profile          Select AWS profile"
        echo "  build            Build Docker images"
        echo "  push             Push images to ECR"
        echo "  build-push       Build and push images"
        echo "  tf-init          Initialize Terraform"
        echo "  tf-plan          Plan Terraform changes"
        echo "  tf-apply         Apply Terraform changes"
        echo "  deploy           Full deployment (build, push, update ECS)"
        echo "  logs [service]   Tail logs (service: api|worker|beat)"
        echo "  status           Get ECS service status"
        echo "  ssh [tag]        SSH into EC2 instance"
        echo "  destroy          Destroy all infrastructure"
        echo ""
        echo "Examples:"
        echo "  ./run.sh build"
        echo "  ./run.sh deploy"
        echo "  ./run.sh logs api"
        echo "  ./run.sh status"
        ;;
esac

