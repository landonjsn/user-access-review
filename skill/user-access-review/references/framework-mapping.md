# Framework mapping for access review findings

Use these only where the finding actually fits. Don't stretch a mapping to make a report look more thorough.

## NIST Cybersecurity Framework 2.0 (Protect: Identity Management, Authentication, and Access Control)

| Subcategory | What it covers | Typical findings |
|---|---|---|
| PR.AA-01 | Identities and credentials for authorized users, services, and hardware are managed | Terminated users with access, unowned or shared accounts, accounts not tied to anyone in HR |
| PR.AA-03 | Users, services, and hardware are authenticated | Missing MFA |
| PR.AA-05 | Access permissions are defined in policy, managed, enforced, and reviewed, using least privilege and separation of duties | Access beyond the role matrix, leftover access after job changes, separation-of-duties conflicts, overdue access reviews |

## PCI DSS v4.0 (only if the system stores, processes, or transmits card data)

| Requirement | What it covers |
|---|---|
| 7.2.2 | Access is assigned based on job function and least privilege |
| 7.2.4 | All user accounts and access are reviewed at least once every six months |
| 8.2.2 | Group, shared, or generic accounts are only used when necessary, on an exception basis |
| 8.2.5 | Access for terminated users is immediately revoked |
| 8.2.6 | Inactive user accounts are removed or disabled within 90 days |
| 8.4.1 | MFA for all non-console administrative access into the cardholder data environment |

Check the current version of each framework before citing it in a real report.
