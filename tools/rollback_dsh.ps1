$ErrorActionPreference = 'Stop'

# Roll back the machine-wide DSH CLI to the version that was installed before
# the 2026-11-02 upgrade. Guga invokes this CLI through PATH.
$targetVersion = '0.1.7-rc.2'
npm install -g "@deepseek-ai/dsh@$targetVersion"
dsh --version
