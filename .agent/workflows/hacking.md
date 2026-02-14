---
description: Ethical Hacking and Security Auditing with VIKI
---

VIKI now includes a suite of advanced security and hacking tools for ethical pentesting and system auditing.

### 1. Available Tools
You can trigger specialized security tools using the `/hack` or `/scan` commands.

- **Automated Reconnaissance**: Scan targets for open ports and services.
  ```viki
  /scan 192.168.1.1
  ```
- **Exploit Lookup**: Search for known vulnerabilities in a software version.
  ```viki
  /hack tool="exploit_db" target="Apache 2.4.49"
  ```
- **Payload Generation**: Create ethical POC scripts for reverse shells.
  ```viki
  /hack tool="payload_gen" target="10.0.0.5:4444" payload_type="python"
  ```
- **Hash Identification**: Analyze unknown hashes to find their algorithm.
  ```viki
  /hack tool="hash_id" target="5d41402abc4b2a76b9719d911017c592"
  ```

### 2. Safety Constraints
VIKI enforces strict ethical boundaries:
- **Local Only**: Most tools are restricted to local network ranges (`192.168.x.x`, `10.x.x.x`, etc.).
- **No Public Targets**: Scanning public domains or critical infrastructure is blocked by the `SafetyLayer`.
- **Confirmation**: High-risk actions (Medium severity) may require a `/confirm`.

### 3. Usage Examples
- `"VIKI, scan my local server and see if there are any open ports."`
- `"What are the vulnerabilities of log4j?"`
- `"Identify this hash: $2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi"`
