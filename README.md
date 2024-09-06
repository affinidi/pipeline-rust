# pipeline-rust

pipleline for Affinidi rust projects

## How to use

add file to `.github/workflows/on-push.yaml`

```yaml
name: on-push

on:
  # Run pipeline in context of branch, but with action config from main for opened and rebased mr's
  # also run on  branch main
  push:
    branches:
      - main
  pull_request_target:
    types:
      - opened
      - synchronize

jobs:
  call-workflow:
    uses: affinidi/pipeline-rust/.github/workflows/on-push.yaml@main
    secrets: inherit
```
