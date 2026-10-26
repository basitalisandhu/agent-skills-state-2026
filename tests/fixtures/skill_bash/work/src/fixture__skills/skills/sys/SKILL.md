---
name: sys
description: Sets up a machine. Use when onboarding.
allowed-tools:
  - Bash
  - Read
---

```sh
$ sudo apt-get install -y jq
npx -y some-tool@latest init \
  --force
echo 'export X=1' >> ~/.zshrc
cat ~/.ssh/id_rsa.pub
```
