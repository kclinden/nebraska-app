locals {
  alb_tls      = var.alb_certificate_arn != ""
  app_nodeport = 32080
  app_service  = { type = var.public_alb_enabled ? "NodePort" : "ClusterIP", nodePort = local.app_nodeport }
}

resource "aws_security_group" "alb" {
  count       = var.public_alb_enabled ? 1 : 0
  name_prefix = "${var.cluster_name}-alb-"
  description = "Public application ALB"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  for_each = var.public_alb_enabled ? var.alb_ingress_cidrs : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = var.public_alb_enabled && local.alb_tls ? var.alb_ingress_cidrs : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "alb_nodes" {
  count = var.public_alb_enabled ? 1 : 0

  security_group_id            = aws_security_group.alb[0].id
  referenced_security_group_id = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = local.app_nodeport
  to_port                      = local.app_nodeport
}

resource "aws_vpc_security_group_ingress_rule" "nodes_alb" {
  count = var.public_alb_enabled ? 1 : 0

  security_group_id            = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.alb[0].id
  ip_protocol                  = "tcp"
  from_port                    = local.app_nodeport
  to_port                      = local.app_nodeport
}

resource "aws_lb" "app" {
  count                      = var.public_alb_enabled ? 1 : 0
  name_prefix                = "nebr-"
  internal                   = false
  load_balancer_type         = "application"
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb[0].id]
  drop_invalid_header_fields = true

  depends_on = [aws_route_table_association.public]
}

resource "aws_lb_target_group" "app" {
  count                = var.public_alb_enabled ? 1 : 0
  name_prefix          = "nebr-"
  vpc_id               = aws_vpc.main.id
  protocol             = "HTTP"
  port                 = local.app_nodeport
  target_type          = "instance"
  deregistration_delay = 30

  health_check {
    path                = "/nebraska_football.png"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_autoscaling_attachment" "app" {
  count                  = var.public_alb_enabled ? 1 : 0
  autoscaling_group_name = aws_eks_node_group.main.resources[0].autoscaling_groups[0].name
  lb_target_group_arn    = aws_lb_target_group.app[0].arn
}

resource "aws_lb_listener" "http" {
  count             = var.public_alb_enabled ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = local.alb_tls ? "redirect" : "forward"
    target_group_arn = local.alb_tls ? null : aws_lb_target_group.app[0].arn

    dynamic "redirect" {
      for_each = local.alb_tls ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.public_alb_enabled && local.alb_tls ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.alb_certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }

  lifecycle {
    precondition {
      condition     = var.alb_hostname != ""
      error_message = "Set alb_hostname to a certificate-covered DNS name and point it at the ALB."
    }
  }
}