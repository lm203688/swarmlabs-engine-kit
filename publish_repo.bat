@echo off
REM Maintainer-local helper. The public repo already exists:
REM   https://github.com/lm203688/swarmlabs-engine-kit
REM
REM Note: on some networks (incl. mainland China) a direct `git push` to
REM github.com is reset mid-transfer. When that happens, push via the GitHub
REM Contents API from the maintainer's own toolbox instead of the git remote.
REM Uncomment the git line only when the network actually permits it.

cd /d "%~dp0"
REM git push -u origin main
echo Push skipped. See the comment above.
pause
