# Deploying on AWS

A design note. I haven't deployed any of this.

## Compute

CloudFront serves the dashboard from a private S3 bucket and routes `/api` to an ALB. The API runs on ECS Fargate across two availability zones. `POST /api/scans` puts the scan ID on SQS, and a separate Fargate worker runs the scan. If a worker crashes, SQS hands the message to another.

## Database

RDS Postgres, Multi-AZ, encrypted, with 7 days of backups. SQLite can't sit behind several tasks.

## Networking

The ALB sits in public subnets. ECS and RDS sit in private ones. The ALB accepts traffic from CloudFront only, the API from the ALB only, and RDS from the API and worker only. ACM handles TLS, and WAF rate-limits scan requests.

## Secrets

Secrets Manager holds the database password and ECS injects it at runtime. Each task gets its own IAM role, so the app holds no access keys.

## Logs

Containers log to CloudWatch. Alarms cover 5xx rates, unhealthy tasks, RDS storage and stuck SQS messages.

## CI deploys

GitHub Actions signs in to AWS through OIDC. The deploy role trusts only `repo:woustachemax/mini-gauntlet:ref:refs/heads/main` and gets one-hour credentials. It can push to ECR, update the two ECS services and sync the dashboard bucket.

## Scanner permissions

The scanner assumes a read-only role in each customer account, with an `ExternalId` per customer.

- AWS-S3-01 needs `s3:ListAllMyBuckets`, `s3:GetBucketLocation` and `s3:GetBucketPublicAccessBlock`
- AWS-EC2-01 needs `ec2:DescribeRegions` and `ec2:DescribeSecurityGroups`
- AWS-IAM-01 needs `iam:ListUsers`, `iam:GetLoginProfile` and `iam:ListMFADevices`
- AWS-IAM-02 needs `iam:ListUsers` and `iam:ListAccessKeys`
- AWS-RDS-01 needs `rds:DescribeDBInstances`

Azure needs `Microsoft.Storage/storageAccounts/read` and `Microsoft.Network/networkSecurityGroups/read`. GCP needs `storage.buckets.list`, `storage.buckets.getIamPolicy` and `compute.firewalls.list`. Both connect through workload identity federation, so neither needs a stored secret.
