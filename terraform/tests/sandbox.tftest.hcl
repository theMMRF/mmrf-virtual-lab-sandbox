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
