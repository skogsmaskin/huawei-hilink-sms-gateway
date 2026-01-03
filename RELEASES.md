# Release Guide

This document explains how to create releases for the SMS Gateway project.

## Automated Release Process

The project uses GitHub Actions to automate releases. When you push a version tag, the following happens automatically:

1. **Tests run** - All tests must pass before release
2. **Docker image is built** - Multi-architecture images (amd64, arm64) are built
3. **Docker image is published** - Images are pushed to GitHub Container Registry
4. **GitHub Release is created** - With changelog and release notes

## Creating a Release

### Step 1: Update Version

Update the version in `app.py`:
- Line 141: `log.info("SMS Gateway started (version X.Y)")`
- Line 154: `version="X.Y"`
- Line 168: `'User-Agent': 'sms-gateway/X.Y'`

### Step 2: Update CHANGELOG.md

Add a new entry in `CHANGELOG.md` following the [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [X.Y] - YYYY-MM-DD

### Added
- New feature description

### Changed
- Change description

### Fixed
- Bug fix description
```

### Step 3: Commit Changes

```bash
git add app.py CHANGELOG.md
git commit -m "Bump version to X.Y"
git push
```

### Step 4: Create and Push Tag

```bash
# Create an annotated tag
git tag -a vX.Y -m "Release version X.Y"

# Push the tag (this triggers the release workflow)
git push origin vX.Y
```

### Step 5: Verify Release

1. Check GitHub Actions: The release workflow should run automatically
2. Check Releases page: A new release should appear at https://github.com/skogsmaskin/huawei-hilink-sms-gateway/releases
3. Check Docker images: Images should be available at https://github.com/skogsmaskin/huawei-hilink-sms-gateway/pkgs/container/sms-gateway

## Version Numbering

This project uses two-part versioning (MAJOR.MINOR):

- **MAJOR** (X.0): Breaking changes or major new features
- **MINOR** (0.X): New features, bug fixes, and improvements (backward compatible)

Examples:
- `v1.0` → `v1.1` (minor: new feature or bug fix)
- `v1.1` → `v2.0` (major: breaking change)

## Docker Image Tags

The following tags are automatically created:

- `vX.Y` - Specific version (e.g., `v1.0`)
- `X.Y` - Same as above, without 'v' prefix
- `X` - Major version (e.g., `1`)
- `latest` - Latest release (main branch only)

## Manual Release (Alternative)

If you prefer to create releases manually:

1. Go to https://github.com/skogsmaskin/huawei-hilink-sms-gateway/releases
2. Click "Draft a new release"
3. Choose or create a tag (e.g., `v1.0`)
4. Fill in release title and description
5. Publish the release

The Docker build workflow will still run automatically on tag push.
