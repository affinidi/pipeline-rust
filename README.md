# pipeline-rust

pipleline for Affinidi rust projects

## How to use

1. add file to `.github/workflows/checks.yaml`

```yaml
name: checks

on:
  pull_request_target:
    types:
      - opened
      - synchronize
      
jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/checks.yaml@fix/release-issue
    secrets: inherit
    with:
      auditIgnore: "RUSTSEC-2022-0040,RUSTSEC-2023-0071,RUSTSEC-2024-0373"


```

2. add file to `.github/workflows/checks.yaml`

```yaml
name: "release"

on:
  push:
    branches:
      - main

 
jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/release.yaml@fix/release-issue
    secrets: inherit
    with:
      auditIgnore: "RUSTSEC-2022-0040,RUSTSEC-2023-0071,RUSTSEC-2024-0373"
```
