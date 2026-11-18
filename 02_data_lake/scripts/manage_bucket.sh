#!/usr/bin/env bash
set -euo pipefail

action="$1"
bucket="$2"
region="$3"

if [[ "$action" == "create" ]]; then
  if ! aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    if [[ "$region" == "us-east-1" ]]; then
      aws s3api create-bucket --bucket "$bucket" --region "$region"
    else
      aws s3api create-bucket --bucket "$bucket" --region "$region" \
        --create-bucket-configuration "LocationConstraint=$region"
    fi
  fi
  aws s3api put-public-access-block --bucket "$bucket" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$bucket" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  if [[ "$bucket" == *-bronze-* ]]; then
    aws s3api put-bucket-versioning --bucket "$bucket" \
      --versioning-configuration Status=Enabled
  fi
elif [[ "$action" == "destroy" ]]; then
  # aws s3 rb --force nao remove versoes nao atuais. Bronze possui
  # versionamento, portanto remove explicitamente versoes e delete markers.
  while :; do
    objects="$(aws s3api list-object-versions --bucket "$bucket" --output json | jq -c '[.Versions[]?, .DeleteMarkers[]? | {Key: .Key, VersionId: .VersionId}]')"
    if [[ "$objects" == "[]" ]]; then
      break
    fi
    aws s3api delete-objects --bucket "$bucket" --delete "{\"Objects\":$objects,\"Quiet\":true}"
  done
  aws s3api delete-bucket --bucket "$bucket"
else
  echo "Acao invalida: $action" >&2
  exit 2
fi
