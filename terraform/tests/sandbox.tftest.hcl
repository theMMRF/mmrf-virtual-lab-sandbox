mock_provider "aws" {}
override_data {
  target = data.aws_availability_zones.available
  values = { names = ["us-east-1a", "us-east-1b"] }
}
variables {
  sandbox_account_id = "123456789012"
  operator_role_arn  = "arn:aws:iam::123456789012:role/SandboxOperator"
  operator_cidrs     = ["192.0.2.1/32"]
}
run "isolated_synthetic_infrastructure" {
  command = plan
  assert {
    condition     = aws_eks_cluster.sandbox.vpc_config[0].public_access_cidrs == toset(["192.0.2.1/32"])
    error_message = "Only the requested operator address may reach the EKS API."
  }
  assert {
    condition     = aws_eks_node_group.sandbox.scaling_config[0].max_size == 1
    error_message = "Sandbox must remain one explicitly sized node."
  }
  assert {
    condition     = length(aws_ecr_repository.service) == 6
    error_message = "Every application image needs its own sandbox registry."
  }
}
run "reject_wrong_account_role" {
  command = plan
  variables { operator_role_arn = "arn:aws:iam::999999999999:role/OtherAccount" }
  expect_failures = [aws_eks_cluster.sandbox]
}
run "reject_open_api" {
  command = plan
  variables { operator_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.operator_cidrs]
}

run "reject_ipv6_api" {
  command = plan
  variables { operator_cidrs = ["2001:db8::/32"] }
  expect_failures = [var.operator_cidrs]
}

run "private_https_entry" {
  command = plan
  variables { enable_https = true }
  assert {
    condition     = aws_lb.sandbox[0].internal && length(aws_subnet.origin) == 2
    error_message = "The ALB must stay private in dedicated origin subnets."
  }
  assert {
    condition     = aws_cloudfront_distribution.sandbox[0].default_cache_behavior[0].viewer_protocol_policy == "https-only"
    error_message = "The public endpoint must refuse plain HTTP."
  }
  assert {
    condition     = aws_cloudfront_distribution.sandbox[0].viewer_certificate[0].cloudfront_default_certificate
    error_message = "No operator-provided domain or certificate may be required."
  }
  assert {
    condition     = aws_cloudfront_distribution.sandbox[0].default_cache_behavior[0].cache_policy_id == "413f160f-6d90-4db8-a6e7-74cbb926abc1"
    error_message = "Do not cache credentials, API responses or cohort-dependent results."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.node_entry[0].from_port == 30080 && aws_vpc_security_group_ingress_rule.node_entry[0].to_port == 30080 && aws_vpc_security_group_ingress_rule.node_entry[0].cidr_ipv4 == null
    error_message = "The NodePort rule must use the ALB security group, not a public CIDR."
  }
}
