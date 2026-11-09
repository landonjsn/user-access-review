"""User access review: compare HR, directory, and POS exports against access policy.

Usage:
    python access_review.py <data_folder> [--review-date YYYY-MM-DD] [--out findings.csv]

Expects these CSVs in <data_folder> (column names must match):
    hr_roster.csv                employee_id, name, job_title, location, status, hire_date, term_date
    hr_job_changes.csv           employee_id, effective_date, change_type, old_title, new_title, old_location, new_location
    role_matrix.csv              job_title, approved_directory_groups, approved_pos_role
    role_matrix_groups.csv       job_title, group_name
    directory_accounts.csv       username, employee_id, owner_employee_id, account_type, enabled,
                                 mfa_enabled, created_date, last_sign_in, disabled_date
    directory_group_members.csv  username, group_name
    pos_users.csv                pos_user_id, pos_username, employee_id, store, pos_role, enabled, last_login

The script only flags what the data shows. It does not decide what to do about it:
severity is a suggested starting point for a human (or the Claude skill) to review.
"""
import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---- Policy settings (edit these to match the organization's policy) ----
INACTIVE_DAYS = 90            # Rule 4: disable accounts unused this long
NEW_ACCOUNT_GRACE_DAYS = 30   # Rule 4: new accounts exempt for this long
VENDOR_MAX_DAYS = 90          # Rule 8: vendor accounts expire after this long
MFA_REQUIRED_GROUPS = {"IT-Admins", "Domain Admins", "Finance-AP", "Finance-Approvers"}  # Rule 5
PRIVILEGED_GROUPS = {"IT-Admins", "Domain Admins"}
SENSITIVE_GROUPS = PRIVILEGED_GROUPS | {"Finance-AP", "Finance-Approvers", "HR"}
ADMIN_ONLY_GROUPS = {"Domain Admins"}  # Rule 6: only on separate admin accounts
ADMIN_PREFIX = "a-"
SOD_CONFLICTS = [("Finance-AP", "Finance-Approvers")]  # Rule 9
# --------------------------------------------------------------------------

SEVERITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def read_csv(folder, name):
    path = Path(folder) / name
    if not path.exists():
        sys.exit(f"Missing file: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_date(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


class Findings:
    """Collects issues and merges them into one finding per account."""

    def __init__(self):
        self.items = {}

    def add(self, key, account, system, issue, rule, severity, incident=False):
        f = self.items.setdefault(key, {
            "account": account, "system": system, "issues": [], "rules": [],
            "severity": "Low", "incident": False,
        })
        if issue not in f["issues"]:
            f["issues"].append(issue)
        if rule not in f["rules"]:
            f["rules"].append(rule)
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[f["severity"]]:
            f["severity"] = severity
        f["incident"] = f["incident"] or incident

    def rows(self):
        ordered = sorted(self.items.values(),
                         key=lambda f: (-SEVERITY_ORDER[f["severity"]], f["account"]))
        for i, f in enumerate(ordered, 1):
            yield {
                "finding_id": f"A{i}",
                "account": f["account"],
                "system": f["system"],
                "what_is_wrong": "; ".join(f["issues"]),
                "policy_rule": "; ".join(f["rules"]),
                "suggested_severity": f["severity"],
                "possible_incident": "Yes" if f["incident"] else "No",
            }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_folder")
    ap.add_argument("--review-date", default=date.today().isoformat())
    ap.add_argument("--out", default="findings.csv")
    args = ap.parse_args()

    review_date = to_date(args.review_date)
    inactive_cutoff = review_date - timedelta(days=INACTIVE_DAYS)
    d = args.data_folder

    hr = {r["employee_id"]: r for r in read_csv(d, "hr_roster.csv")}
    changes = read_csv(d, "hr_job_changes.csv")
    role_pos = {r["job_title"]: r["approved_pos_role"] for r in read_csv(d, "role_matrix.csv")}
    role_groups = {}
    for r in read_csv(d, "role_matrix_groups.csv"):
        role_groups.setdefault(r["job_title"], set()).add(r["group_name"])
    accounts = read_csv(d, "directory_accounts.csv")
    groups = {}
    for r in read_csv(d, "directory_group_members.csv"):
        groups.setdefault(r["username"], set()).add(r["group_name"])
    pos = read_csv(d, "pos_users.csv")

    findings = Findings()
    cleared = []

    def is_inactive(last_used, created):
        last_used, created = to_date(last_used), to_date(created)
        if created and (review_date - created).days <= NEW_ACCOUNT_GRACE_DAYS:
            return False
        if last_used is None:
            return True
        return last_used < inactive_cutoff

    def leftover_from_change(emp_id, *, group=None, store=None):
        """True if this access came from the person's old job or old store."""
        for c in changes:
            if c["employee_id"] != emp_id or c["change_type"] not in ("Transfer", "Promotion"):
                continue
            if group and group in role_groups.get(c["old_title"], set()):
                return True
            if store and store == c["old_location"]:
                return True
        return False

    # ---------------- Directory accounts ----------------
    for a in accounts:
        user, emp_id, enabled = a["username"], a["employee_id"], a["enabled"] == "Yes"
        key = ("Directory", user)
        person = hr.get(emp_id)
        my_groups = groups.get(user, set())

        if emp_id and person is None:
            findings.add(key, user, "Directory", "Employee ID not found in HR roster (orphaned account)",
                         "Rule 1: Least privilege", "High")
            continue

        # Terminations (Rule 2)
        if person and person["status"] == "Terminated":
            term = to_date(person["term_date"])
            last = to_date(a["last_sign_in"])
            if enabled:
                findings.add(key, user, "Directory",
                             f"Terminated {term} but account still enabled",
                             "Rule 2: Terminations", "Medium")
            if last and term and last > term:
                findings.add(key, user, "Directory",
                             f"Signed in {last}, after termination",
                             "Rule 2: Terminations", "High", incident=True)
            if not enabled and not (last and term and last > term):
                cleared.append(f"{user}: terminated {term}, directory account disabled")
            continue

        if not enabled:
            continue

        # Accounts with no person behind them (Rule 8)
        if not emp_id:
            owner = a["owner_employee_id"]
            if not owner:
                sev = "High" if my_groups & PRIVILEGED_GROUPS else "Medium"
                findings.add(key, user, "Directory", f"{a['account_type']} account with no named owner",
                             "Rule 8: Service and vendor accounts", sev)
            elif a["account_type"] == "Service":
                cleared.append(f"{user}: service account with documented owner {owner}")
            if a["account_type"] == "Vendor":
                created = to_date(a["created_date"])
                if created and (review_date - created).days > VENDOR_MAX_DAYS:
                    expiry = created + timedelta(days=VENDOR_MAX_DAYS)
                    findings.add(key, user, "Directory",
                                 f"Vendor account created {created}, past the {VENDOR_MAX_DAYS}-day limit (ended {expiry})",
                                 "Rule 8: Service and vendor accounts", "Medium")
                    # Added after testing: use after the limit means someone used an account
                    # that should already have been off, the same as a login after termination.
                    last = to_date(a["last_sign_in"])
                    if last and last > expiry:
                        findings.add(key, user, "Directory",
                                     f"Signed in {last}, after the vendor limit ended",
                                     "Rule 8: Service and vendor accounts", "High", incident=True)

        # Leave of absence: the policy is silent, so this is a gap, not a violation
        if person and person["status"] == "Leave of Absence":
            findings.add(("Leave", emp_id), f"{user} (and any POS login)", "Directory and POS",
                         "On leave with access still enabled; policy has no rule for leave",
                         "Policy gap", "Low")

        # Role matrix and separation of duties (Rules 1, 3, 9)
        if person:
            allowed = role_groups.get(person["job_title"], set())
            sod_groups = set()
            for g1, g2 in SOD_CONFLICTS:
                if g1 in my_groups and g2 in my_groups:
                    sod_groups |= {g1, g2}
                    findings.add(key, user, "Directory",
                                 f"In both {g1} and {g2} (can create and approve the same transaction)",
                                 "Rule 9: Separation of duties", "High")
            for g in sorted(my_groups - allowed):
                if g in sod_groups:
                    continue
                sev = "Medium" if g in SENSITIVE_GROUPS else "Low"
                if leftover_from_change(emp_id, group=g):
                    findings.add(key, user, "Directory", f"Still in {g} from a previous job",
                                 "Rule 3: Job changes", sev)
                else:
                    findings.add(key, user, "Directory", f"In {g}, which the role matrix does not allow for {person['job_title']}",
                                 "Rule 1: Least privilege", sev)

        # Admin rights only on admin accounts (Rule 6)
        for g in my_groups & ADMIN_ONLY_GROUPS:
            if not user.startswith(ADMIN_PREFIX):
                findings.add(key, user, "Directory", f"{g} rights on an everyday account",
                             "Rule 6: Admin accounts", "High")

        # MFA (Rule 5)
        missing = sorted(my_groups & MFA_REQUIRED_GROUPS) if a["mfa_enabled"] != "Yes" else []
        if missing:
            sev = "High" if set(missing) & PRIVILEGED_GROUPS else "Medium"
            findings.add(key, user, "Directory", f"No MFA while in {', '.join(missing)}",
                         "Rule 5: MFA", sev)

        # Inactivity (Rule 4)
        if is_inactive(a["last_sign_in"], a["created_date"]):
            last = a["last_sign_in"][:10] or "never"
            findings.add(key, user, "Directory", f"No sign-in since {last}",
                         "Rule 4: Inactive accounts", "Low")
        elif not a["last_sign_in"]:
            cleared.append(f"{user}: never signed in, but created {a['created_date']} (inside {NEW_ACCOUNT_GRACE_DAYS}-day grace)")

    # ---------------- POS users ----------------
    for p in pos:
        user, emp_id, enabled = p["pos_username"], p["employee_id"], p["enabled"] == "Yes"
        key = ("POS", user)
        person = hr.get(emp_id)

        if not emp_id:
            if enabled:
                findings.add(key, user, "POS", "Shared login with no employee attached",
                             "Rule 7: Shared accounts", "Medium")
            continue
        if person is None:
            if enabled:
                findings.add(key, user, "POS", "Employee ID not found in HR roster",
                             "Rule 1: Least privilege", "High")
            continue
        if person["status"] == "Terminated":
            term = to_date(person["term_date"])
            last = to_date(p["last_login"])
            if enabled:
                findings.add(key, user, "POS", f"Terminated {term} but POS login still enabled ({p['pos_role']} rights)",
                             "Rule 2: Terminations", "Medium")
            if last and term and last > term:
                findings.add(key, user, "POS", f"POS login used {last}, after termination",
                             "Rule 2: Terminations", "High", incident=True)
            if not enabled and not (last and term and last > term):
                cleared.append(f"{user}: terminated {term}, POS login disabled")
            continue
        if not enabled:
            continue

        approved = role_pos.get(person["job_title"], "None")
        approved_role = approved.split(" (")[0]
        if approved_role == "None":
            findings.add(key, user, "POS", f"Has a POS login; role matrix gives {person['job_title']} no POS access",
                         "Rule 1: Least privilege", "Medium")
        elif p["pos_role"] != approved_role:
            findings.add(key, user, "POS",
                         f"POS role is {p['pos_role']}; role matrix allows {approved_role} for {person['job_title']}",
                         "Rule 1: Least privilege", "Medium")
        if "all stores" not in approved.lower() and p["store"] != person["location"]:
            if leftover_from_change(emp_id, store=p["store"]):
                findings.add(key, user, "POS", f"Still has a login at {p['store']} after transferring",
                             "Rule 3: Job changes", "Low")
            else:
                findings.add(key, user, "POS", f"Has a login at {p['store']}, but works at {person['location']}",
                             "Rule 1: Least privilege", "Low")
        if is_inactive(p["last_login"], person["hire_date"]):
            last = p["last_login"][:10] or "never"
            findings.add(key, user, "POS", f"No POS login since {last}",
                         "Rule 4: Inactive accounts", "Low")

    # ---------------- Output ----------------
    rows = list(findings.rows())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["finding_id"])
        w.writeheader()
        w.writerows(rows)

    counts = {s: sum(r["suggested_severity"] == s for r in rows) for s in ("High", "Medium", "Low")}
    print(f"Access review as of {review_date}: {len(rows)} findings "
          f"({counts['High']} High, {counts['Medium']} Medium, {counts['Low']} Low)")
    for r in rows:
        flag = "  [POSSIBLE INCIDENT]" if r["possible_incident"] == "Yes" else ""
        print(f"  {r['finding_id']} [{r['suggested_severity']}] {r['account']} ({r['system']}): {r['what_is_wrong']}{flag}")
    if cleared:
        print("\nChecked and cleared:")
        for c in cleared:
            print(f"  - {c}")
    print(f"\nFindings written to {args.out}")


if __name__ == "__main__":
    main()
