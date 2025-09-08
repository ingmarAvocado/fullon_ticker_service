# Poetry Update Automation Prompt

You are tasked with updating all Poetry-managed Python packages across multiple subdirectories in this repository.

## Overview
This repository contains multiple Python packages, each managed with Poetry. Each subdirectory with a `pyproject.toml` file represents a separate package that needs to be updated.

## Processing Order
**IMPORTANT**: Process the subdirectories in this exact order due to dependencies:

1. `fullon_log/`
2. `fullon_orm/`
3. `fullon_cache/`
4. `fullon_ohlcv/`
5. `fullon_exchange/`

## Handling New Directories
If you discover additional subdirectories with `pyproject.toml` files that are not in the list above:

1. **STOP** processing immediately
2. Ask the user: "I found a new Poetry project directory: `[directory_name]`. Where should this be placed in the processing order?"
3. Wait for the user's response
4. Update the file `POETRY_UPDATE_ORDER.txt` in the repository root with the complete ordered list
5. Continue processing in the updated order

## Task Instructions

For each subdirectory in the specified order, perform the following steps:

### 1. Navigate to Directory
```bash
cd [subdirectory_name]
```

### 2. Update Poetry Dependencies
```bash
poetry update
```

### 3. Version Bump (Minor-Minor)
Update the version in `pyproject.toml` by incrementing the patch version (e.g., 1.2.3 → 1.2.4).

You can either:
- Use `poetry version patch` command, or
- Manually edit the version field in `pyproject.toml`

### 4. Git Commit and Push
```bash
git add .
git commit -m "chore: update dependencies and bump version to [new_version]"
git push
```

### 5. Return to Parent Directory
```bash
cd ..
```

## Important Notes
- Always verify that each directory has a `pyproject.toml` file before attempting poetry operations
- If poetry update fails, check the error message and resolve dependency conflicts if possible
- Ensure you're in the correct directory before running each command
- The repository may not be a git repository, so handle git operations gracefully if they fail
- If any step fails for a particular directory, document the failure and continue with the next directory

## Expected Workflow
1. Start in the repository root directory (`/home/ingmar/code/fullon2`)
2. Process each subdirectory sequentially
3. For each subdirectory:
   - Enter the directory
   - Run poetry update
   - Bump version (patch increment)
   - Commit changes
   - Push to remote (if git repo exists)
   - Return to root
4. Provide a summary of all operations performed

## Error Handling
- If a directory doesn't exist, skip it and note the issue
- If poetry commands fail, document the error and continue
- If git operations fail (e.g., not a git repo), note this but don't treat as a fatal error
- Always continue processing remaining directories even if some fail

Execute this workflow systematically for all Poetry-managed subdirectories.