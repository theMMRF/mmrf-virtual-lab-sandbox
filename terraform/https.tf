# Browser TLS uses the AWS-owned CloudFront hostname. Origin HTTP stays inside
# the VPC; there is no public ALB, ACM validation or DNS ownership dependency.
resource "aws_subnet" "origin" {
  count             = var.enable_https ? 2 : 0
  vpc_id            = aws_vpc.sandbox.id
  cidr_block        = cidrsubnet(aws_vpc.sandbox.cidr_block, 8, 10 + count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "${var.name}-origin-${count.index}" }
}
resource "aws_route_table" "origin" {
  count  = var.enable_https ? 1 : 0
  vpc_id = aws_vpc.sandbox.id
}
resource "aws_route_table_association" "origin" {
  count          = var.enable_https ? 2 : 0
  subnet_id      = aws_subnet.origin[count.index].id
  route_table_id = aws_route_table.origin[0].id
}
data "aws_ec2_managed_prefix_list" "cloudfront" {
  count = var.enable_https ? 1 : 0
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}
resource "aws_security_group" "origin" {
  count       = var.enable_https ? 1 : 0
  name_prefix = "${var.name}-origin-"
  vpc_id      = aws_vpc.sandbox.id
  description = "CloudFront VPC origin to password-protected synthetic entry"
}
resource "aws_vpc_security_group_ingress_rule" "cloudfront" {
  count             = var.enable_https ? 1 : 0
  security_group_id = aws_security_group.origin[0].id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront[0].id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}
resource "aws_vpc_security_group_egress_rule" "origin_nodes" {
  count                        = var.enable_https ? 1 : 0
  security_group_id            = aws_security_group.origin[0].id
  referenced_security_group_id = aws_eks_cluster.sandbox.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}
resource "aws_vpc_security_group_ingress_rule" "node_entry" {
  count                        = var.enable_https ? 1 : 0
  security_group_id            = aws_eks_cluster.sandbox.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.origin[0].id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}
resource "aws_lb" "sandbox" {
  count                      = var.enable_https ? 1 : 0
  name                       = var.name
  internal                   = true
  load_balancer_type         = "application"
  subnets                    = aws_subnet.origin[*].id
  security_groups            = [aws_security_group.origin[0].id]
  idle_timeout               = 180
  drop_invalid_header_fields = true
}
resource "aws_lb_target_group" "entry" {
  count                = var.enable_https ? 1 : 0
  name_prefix          = "synth-"
  port                 = 30080
  protocol             = "HTTP"
  target_type          = "instance"
  vpc_id               = aws_vpc.sandbox.id
  deregistration_delay = 10
  health_check {
    path                = "/_status"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
  }
}
resource "aws_lb_listener" "entry" {
  count             = var.enable_https ? 1 : 0
  load_balancer_arn = aws_lb.sandbox[0].arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.entry[0].arn
  }
}
# Terraform owns the ALB and its ASG registration; no Kubernetes AWS controller
# or cloud credentials in application pods are necessary. Replacement nodes
# register automatically through the managed node group's ASG attachment.
resource "aws_autoscaling_attachment" "entry" {
  count                  = var.enable_https ? 1 : 0
  autoscaling_group_name = aws_eks_node_group.sandbox.resources[0].autoscaling_groups[0].name
  lb_target_group_arn    = aws_lb_target_group.entry[0].arn
}
resource "aws_cloudfront_vpc_origin" "sandbox" {
  count = var.enable_https ? 1 : 0
  vpc_origin_endpoint_config {
    name                   = var.name
    arn                    = aws_lb.sandbox[0].arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"
    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
  depends_on = [aws_lb_listener.entry, aws_vpc_security_group_ingress_rule.cloudfront, aws_route_table_association.origin, aws_internet_gateway.sandbox]
}
# Resolve managed policies during planning so a missing policy is detected
# before infrastructure is created, rather than relying on copied UUIDs.
data "aws_cloudfront_cache_policy" "caching_disabled" {
  count = var.enable_https ? 1 : 0
  name  = "Managed-CachingDisabled"
  lifecycle {
    postcondition {
      condition     = self.min_ttl == 0 && self.default_ttl == 0 && self.max_ttl == 0
      error_message = "The CloudFront policy must disable caching for credentials and cohort-specific results."
    }
  }
}
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  count = var.enable_https ? 1 : 0
  name  = "Managed-AllViewer"
}
resource "aws_cloudfront_distribution" "sandbox" {
  count               = var.enable_https ? 1 : 0
  enabled             = true
  wait_for_deployment = true
  comment             = "${var.name}: synthetic-only password-protected Virtual Lab"
  price_class         = "PriceClass_100"
  origin {
    domain_name = aws_lb.sandbox[0].dns_name
    origin_id   = "synthetic-vpc"
    vpc_origin_config {
      vpc_origin_id            = aws_cloudfront_vpc_origin.sandbox[0].id
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }
  default_cache_behavior {
    target_origin_id       = "synthetic-vpc"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    # AWS managed CachingDisabled and AllViewer policies. No synthetic sessions,
    # Basic authorization, API responses, or cohort-dependent plots are cached.
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled[0].id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer[0].id
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
}
