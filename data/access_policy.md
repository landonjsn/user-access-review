# Redbud Resale Co. Access Control Policy (excerpt)

*Redbud Resale Co. is a fictional company. All names and data in this project are made up.*

**Version:** 1.2
**Policy owner:** Dana Whitfield, General Manager
**Administered by:** Tyler Brooks, IT Coordinator

## About the company

Redbud is a resale clothing retailer with three stores (Athens, Watkinsville, Gainesville) and a small corporate office, about 34 employees in total. Staff sign in with Microsoft Entra ID accounts. The stores use a cloud point-of-sale (POS) system that takes card payments, so the POS system is in scope for PCI DSS. For this exercise, assume the Entra ID directory is also connected to the card payment environment.

## Policy statements

1. **Least privilege.** Access is granted based on the Role Matrix (`role_matrix.csv`). Any access beyond the Role Matrix needs written approval from the General Manager. No approvals were on file at the time of this review.
2. **Terminations.** HR notifies IT the same day. All of the person's accounts, in both the directory and the POS system, are disabled on the termination date.
3. **Transfers and promotions.** Access the person no longer needs is removed within 5 business days of the change's effective date.
4. **Inactive accounts.** Enabled accounts with no sign-in for 90 days are disabled. New accounts are exempt for their first 30 days.
5. **Multi-factor authentication (MFA).** MFA is required for every member of IT-Admins, Domain Admins, Finance-AP, and Finance-Approvers.
6. **Admin accounts.** Domain Admin rights are only granted to separate admin accounts (usernames starting with `a-`), never to everyday accounts.
7. **Shared accounts.** Shared or generic logins are prohibited unless there's an approved exception in the Exceptions Register. The register is currently empty.
8. **Service and vendor accounts.** Every service or vendor account must have a named owner (`owner_employee_id`). Vendor accounts are disabled when the engagement ends, or after 90 days at most.
9. **Separation of duties.** No one may be in both Finance-AP (sets up vendors and enters invoices) and Finance-Approvers (approves payments).
10. **Access reviews.** The IT Coordinator reviews all user access every 6 months, and department managers sign off on the results.

## Data provided for the review (as of October 31, 2026)

| File | What it is |
|---|---|
| `hr_roster.csv` | Every employee, with job title, location, status, and hire and termination dates |
| `hr_job_changes.csv` | Transfers, promotions, rehires, and leaves of absence |
| `role_matrix.csv` | Approved access for each job title (easy to read) |
| `role_matrix_groups.csv` | The same approved directory groups, one row per group (easier for SQL) |
| `directory_accounts.csv` | Entra ID account export |
| `directory_group_members.csv` | Which groups each account belongs to |
| `pos_users.csv` | POS system user export |
