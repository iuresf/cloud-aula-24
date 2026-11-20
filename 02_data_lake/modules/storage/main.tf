# O AWS Academy bloqueia GetBucketObjectLockConfiguration. Por isso este
# modulo usa AWS CLI idempotente em vez de aws_s3_bucket.
resource "terraform_data" "zones" {
  for_each = var.bucket_names

  input = {
    bucket      = each.value
    region      = var.region
    script_path = var.manage_script_path
  }

  provisioner "local-exec" {
    command = "bash ${self.input.script_path} create ${self.input.bucket} ${self.input.region}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "bash ${self.input.script_path} destroy ${self.input.bucket} ${self.input.region}"
  }
}
