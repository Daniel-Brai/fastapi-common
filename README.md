# fastapi-common Installer

This repository includes a simple install script to download a specific folder from the GitHub repository and copy it locally.

## Install Script

Use `curl` to download the install script and make it executable:

```bash
curl -fsSL https://raw.githubusercontent.com/Daniel-Brai/fastapi-common/main/install.sh -o install-fastapi-common.sh
chmod +x install-fastapi-common.sh
```

## Usage

Copy a folder from the repository root to the current directory:

```bash
./install-fastapi-common.sh mailer
```

Copy a folder to a specific destination directory:

```bash
./install-fastapi-common.sh auth ./local-auth
```

## Notes

- The script downloads the repository archive from GitHub and extracts only the requested folder.
- The folder path is relative to the repository root.
