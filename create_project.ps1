# create_project.ps1
# Script to generate the Shopify Auth Backend project structure

# Root project name
$projectRoot = "shopify-auth-backend"

# Define all directories
$directories = @(
    "$projectRoot/app",
    "$projectRoot/app/api",
    "$projectRoot/app/api/v1",
    "$projectRoot/app/core",
    "$projectRoot/app/models",
    "$projectRoot/app/services",
    "$projectRoot/app/utils",
    "$projectRoot/tests",
    "$projectRoot/alembic"
)

# Define all files
$files = @(
    "$projectRoot/app/__init__.py",
    "$projectRoot/app/main.py",
    "$projectRoot/app/api/__init__.py",
    "$projectRoot/app/api/deps.py",
    "$projectRoot/app/api/v1/__init__.py",
    "$projectRoot/app/api/v1/auth.py",
    "$projectRoot/app/core/__init__.py",
    "$projectRoot/app/core/config.py",
    "$projectRoot/app/core/security.py",
    "$projectRoot/app/core/logging.py",
    "$projectRoot/app/models/__init__.py",
    "$projectRoot/app/models/auth.py",
    "$projectRoot/app/models/database.py",
    "$projectRoot/app/services/__init__.py",
    "$projectRoot/app/services/auth_service.py",
    "$projectRoot/app/services/database_service.py",
    "$projectRoot/app/utils/__init__.py",
    "$projectRoot/app/utils/exceptions.py",
    "$projectRoot/tests/__init__.py",
    "$projectRoot/tests/conftest.py",
    "$projectRoot/tests/test_auth_service.py",
    "$projectRoot/tests/test_auth_endpoints.py",
    "$projectRoot/requirements.txt",
    "$projectRoot/requirements-dev.txt",
    "$projectRoot/Dockerfile",
    "$projectRoot/docker-compose.yml",
    "$projectRoot/.env.example",
    "$projectRoot/.gitignore",
    "$projectRoot/pyproject.toml",
    "$projectRoot/alembic.ini",
    "$projectRoot/README.md"
)

# Create directories
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Output "Created directory: $dir"
    }
}

# Create files
foreach ($file in $files) {
    if (-not (Test-Path $file)) {
        New-Item -ItemType File -Path $file | Out-Null
        Write-Output "Created file: $file"
    }
}

Write-Output "✅ Project structure created successfully!"
