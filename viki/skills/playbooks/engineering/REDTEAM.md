# Red Team & Penetration Testing Playbook

Use this playbook for authorized security assessments, penetration testing, and red-teaming exercises.

## Process

### 1. Passive Reconnaissance
- Use `research_skill` to find public information about the target.
- Identify subdomains, public email addresses, and technology stacks.
- Search for leaked credentials in public repositories.

### 2. Active Reconnaissance
- Use `security_tools.net_scan` for fast port discovery.
- Use `security_tools.deep_recon` for OS fingerprinting and service versioning.
- Identify entry points: web servers, SSH, VPNs, databases.

### 3. Vulnerability Research
- Cross-reference found versions with `security_tools.exploit_search`.
- Identify high-impact CVEs (RCE, Auth Bypass).
- Analyze the application logic for custom vulnerabilities (IDOR, XSS, SQLi) using `autonomous_auditor`.

### 4. Exploitation (Authorized Only)
- Draft exploit PoCs based on research.
- Test payloads on isolated local targets first.
- Document successful entry points and lateral movement paths.

### 5. Reporting & Remediation
- Categorize findings by severity (Critical, High, Medium, Low).
- Provide clear remediation steps for each vulnerability.
- Verify fixes using the same testing vectors.

## Red Flags

- [ ] Scanning public assets without explicit authorization.
- [ ] Using destructive payloads on production systems.
- [ ] Storing cleartext passwords or sensitive data in audit reports.
- [ ] Ignoring local law or project-specific Rules of Engagement (RoE).

## Verification

- [ ] Target is confirmed local or authorized.
- [ ] Scan results are documented and timestamped.
- [ ] No permanent changes made to target system without prior agreement.
