mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = {
      names = ["us-east-1a", "us-east-1b"]
    }
  }
  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }
}

mock_provider "random" {}

run "isolated_eks_stack" {
  command = plan
  variables {
    public_access_cidrs = ["192.0.2.10/32"]
  }

  assert {
    condition     = aws_eks_cluster.main.vpc_config[0].endpoint_private_access && aws_eks_cluster.main.vpc_config[0].public_access_cidrs == toset(["192.0.2.10/32"])
    error_message = "Cluster API access must be private for nodes and CIDR-restricted for operators."
  }

  assert {
    condition     = aws_dynamodb_table.app["players"].name == "nebraska-eks-players" && aws_dynamodb_table.app["schedule"].name == "nebraska-eks-schedule" && aws_dynamodb_table.app["users"].name == "nebraska-eks-users"
    error_message = "EKS tables must not collide with the ECS table names."
  }

  assert {
    condition     = aws_eks_pod_identity_association.app.service_account == "nebraska-app" && aws_eks_pod_identity_association.app.namespace == "nebraska-app"
    error_message = "Pod Identity must match the Helm service account and namespace."
  }

  assert {
    condition     = aws_eks_node_group.main.labels["Application"] == "Husker-Roster-App" && aws_eks_node_group.main.labels["app.kubernetes.io/part-of"] == "husker-roster-app"
    error_message = "EKS worker nodes must carry the shared application identity labels."
  }

  assert {
    condition     = alltrue([for specification in aws_launch_template.nodes.tag_specifications : specification.tags["Application"] == "Husker-Roster-App"])
    error_message = "EKS worker instances and volumes must carry the shared AWS application tag."
  }

  assert {
    condition     = length(aws_iam_role_policy.app_s3_read_all) == 0
    error_message = "Broad S3 read access must be disabled by default."
  }

  assert {
    condition     = aws_launch_template.nodes.metadata_options[0].http_tokens == "required" && aws_launch_template.nodes.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "App pods must not fall back to the EC2 node credentials."
  }

  assert {
    condition     = !aws_lb.app[0].internal && local.app_service.type == "NodePort" && aws_lb_target_group.app[0].port == local.app_service.nodePort
    error_message = "The public ALB must forward to the same NodePort exposed by Helm."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.nodes_alb[0].from_port == 32080 && aws_vpc_security_group_egress_rule.alb_nodes[0].to_port == 32080
    error_message = "ALB-to-node traffic must be limited to the application NodePort."
  }
}

run "private_access" {
  command = plan
  variables {
    public_alb_enabled = false
  }
  assert {
    condition     = length(aws_lb.app) == 0 && length(aws_autoscaling_attachment.app) == 0 && local.app_service.type == "ClusterIP"
    error_message = "Private mode must not provision a public ALB or NodePort."
  }
}

run "s3_read_all_opt_in" {
  command = plan
  variables {
    enable_s3_read_all = true
  }

  assert {
    condition     = length(aws_iam_role_policy.app_s3_read_all) == 1
    error_message = "Opting in must attach the S3 read policy to the app role."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.app_s3_read_all[0].policy).Statement[0].Action == ["s3:ListAllMyBuckets"] && jsondecode(aws_iam_role_policy.app_s3_read_all[0].policy).Statement[1].Action == ["s3:GetBucketLocation", "s3:ListBucket"] && jsondecode(aws_iam_role_policy.app_s3_read_all[0].policy).Statement[2].Action == ["s3:GetObject"]
    error_message = "The opt-in S3 policy must allow only listing and object reads."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.app_s3_read_all[0].policy).Statement[1].Resource == "arn:aws:s3:::*" && jsondecode(aws_iam_role_policy.app_s3_read_all[0].policy).Statement[2].Resource == "arn:aws:s3:::*/*"
    error_message = "The opt-in S3 read policy must cover bucket and object ARNs."
  }
}

run "https_access" {
  command = plan
  variables {
    alb_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"
    alb_hostname        = "nebraska.example.com"
    alb_ingress_cidrs   = ["192.0.2.10/32"]
  }
  assert {
    condition     = aws_lb_listener.http[0].default_action[0].type == "redirect" && aws_lb_listener.https[0].port == 443 && local.alb_tls
    error_message = "TLS must redirect HTTP to HTTPS."
  }
  assert {
    condition     = keys(aws_vpc_security_group_ingress_rule.alb_https) == ["192.0.2.10/32"]
    error_message = "The public application CIDR allowlist must be enforced."
  }
}

run "unrestricted_api_default" {
  command = plan
  assert {
    condition     = aws_eks_cluster.main.vpc_config[0].endpoint_public_access && aws_eks_cluster.main.vpc_config[0].endpoint_private_access && aws_eks_cluster.main.vpc_config[0].public_access_cidrs == toset(["0.0.0.0/0"])
    error_message = "The API must default to internet-wide access while retaining the private endpoint for nodes."
  }
  assert {
    condition     = aws_eks_cluster.main.access_config[0].authentication_mode == "API"
    error_message = "Public API access must retain EKS IAM authentication."
  }
}

run "reject_invalid_api_cidr" {
  command = plan
  variables {
    public_access_cidrs = ["not-a-cidr"]
  }
  expect_failures = [var.public_access_cidrs]
}