output "cluster_name" { value = aws_eks_cluster.sandbox.name }
output "region" { value = var.region }
output "image_repositories" { value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url } }
output "frontend_access" {
  value = var.enable_https ? "https://${aws_cloudfront_distribution.sandbox[0].domain_name}" : "After installing the Helm chart: kubectl -n mmrf-synthetic port-forward service/identity 3081:8080 --address 127.0.0.1"
}
output "https_url" { value = var.enable_https ? "https://${aws_cloudfront_distribution.sandbox[0].domain_name}" : null }
output "origin_cidrs" { value = aws_subnet.origin[*].cidr_block }
output "target_group_arn" { value = var.enable_https ? aws_lb_target_group.entry[0].arn : null }
