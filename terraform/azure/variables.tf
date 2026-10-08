variable "location" {
  description = "Azure region to deploy into"
  type        = string
  default     = "centralus"
}

variable "resource_group_name" {
  description = "Resource group that holds every resource in this stack"
  type        = string
  default     = "rg-husker-app"
}

variable "image_tag" {
  description = "Image tag the web app runs"
  type        = string
  default     = "latest"
}

variable "app_service_sku" {
  description = "App Service plan SKU (B1 is the cheapest tier with Always On)"
  type        = string
  default     = "B1"
}
