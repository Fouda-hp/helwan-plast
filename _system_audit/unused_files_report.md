# Unused Files Report — Helwan Plast ERP

**Generated**: 2026-02-18
**Method**: Full recursive dependency scan (Python imports, server callables, JS bridges, YAML references)

---

## Confirmed Unused Files (Safe to Delete)

| # | File/Folder | Type | Reason |
|---|---|---|---|
| 1 | `tmp_mod.py` | Python script | One-off utility referencing old path `D:\OneDrive...`. Not imported by any module. |
| 2 | `schema.txt` | Text | Empty file (0 bytes content). Not referenced anywhere. |
| 3 | `server_code/schema_export.py` | Server module | No `@anvil.server.callable` decorators. Not imported by any module. Not called from client. |
| 4 | `server_code/access_policy.py` | Server module | No `@anvil.server.callable` decorators. Not imported by any module. Not called from client. |
| 5 | `client_code/ImportCSV/` | Empty directory | Contains no files. No form_template.yaml or __init__.py. |
| 6 | `theme/assets/js_originals_backup/` | Backup folder (12 files) | Duplicate copies of Calculator JS files. Git history provides version control. |
| 7 | `theme/assets/originals_backup/` | Backup folder (4 files) | Duplicate copies of image assets. Git history provides version control. |
| 8 | `_ul` | Marker file | Empty file at root. Not used by Anvil framework. |
| 9 | `_UL-Fouda-Pc` | Marker file | Empty file at root. Not used by Anvil framework. |
| 10 | `theme/assets/Calculator/.gitkeep` | Git marker | Directory now contains 9 JS files. `.gitkeep` is no longer needed. |

## Stale Documentation (Move to _archive/)

| # | File | Reason |
|---|---|---|
| 1 | `AUDIT_FIX_PLAN.md` | Stale AI-generated audit report. Not referenced by code. |
| 2 | `BACKUP_SCHEDULE.md` | Stale documentation. Not referenced by code. |
| 3 | `CONNECTION_AND_PERFORMANCE.md` | Stale report. Not referenced by code. |
| 4 | `CONTRACTS_SAVE_REFERENCE.md` | Stale reference. Not referenced by code. |
| 5 | `CURRENT_PROJECT_STATUS_REPORT.md` | Stale status report. Not referenced by code. |
| 6 | `DEBUG_REPORT.md` | Stale debug report. Not referenced by code. |
| 7 | `DETAILED_PROJECT_REVIEW_REPORT.md` | Stale review. Not referenced by code. |
| 8 | `ENTERPRISE_CHANGES.md` | Stale changelog. Not referenced by code. |
| 9 | `FULL_PROJECT_REVIEW_AND_DEBUG.md` | Stale review. Not referenced by code. |
| 10 | `INSPECTION_REPORT.md` | Stale report. Not referenced by code. |
| 11 | `MIGRATION_PLAN.md` | Stale migration plan. Not referenced by code. |
| 12 | `MOBILE_INPUT_TYPES_SUMMARY.md` | Stale summary. Not referenced by code. |
| 13 | `OTP_CHANNEL_SETUP.md` | Stale setup guide. Not referenced by code. |
| 14 | `PROJECT_ARCHITECTURE_AND_FLOW.md` | Stale architecture doc. Replaced by `_system_docs/`. |
| 15 | `PROJECT_EVALUATION_REPORT.md` | Stale evaluation. Not referenced by code. |
| 16 | `PROJECT_REVIEW_REPORT.md` | Stale review. Not referenced by code. |
| 17 | `PROJECT_STATUS_AND_LINE_REVIEW.md` | Stale status. Not referenced by code. |
| 18 | `PUBLISH_ANVIL.md` | Stale publish guide. Not referenced by code. |
| 19 | `REVIEW_REPORT_DETAILED.md` | Stale review. Not referenced by code. |
| 20 | `ROLES_AND_PERMISSIONS.md` | Stale roles doc. Not referenced by code. |
| 21 | `SECRETS.md` | Stale secrets reference. Not referenced by code. |
| 22 | `مراجعة_السيناريوهات_والمشاكل.md` | Stale Arabic review. Not referenced by code. |

## Confirmed USED — DO NOT DELETE

| File | Evidence |
|---|---|
| `server_code/pdf_reports.py` | Imported by `accounting.py` lines 34-36 |
| `server_code/quotation_backup.py` | Imported by `QuotationManager.py` lines 44-46 |
| `server_code/quotation_pdf.py` | Has `@anvil.server.callable` (`get_quotation_pdf_data`), called by QuotationPrintForm and ContractPrintForm |
| `server_code/quotation_numbers.py` | Has `@anvil.server.callable` (`peek_next_client_code`, etc.), called by CalculatorForm |
| `server_code/notifications.py` | Has `@anvil.server.callable` (9 functions), called by notification-bell.js bridge |
| `server_code/client_notes.py` | Has `@anvil.server.callable` (6 functions), called by ClientDetailForm |
| `server_code/client_timeline.py` | Has `@anvil.server.callable` (2 functions), called by ClientDetailForm |
| `server_code/followup_reminders.py` | Has `@anvil.server.callable` (6 functions), called by FollowUpDashboardForm |
| All `auth_*.py` modules | Part of authentication chain, imported by AuthManager.py |
| All form `__init__.py` + `form_template.yaml` | Required by Anvil framework for form rendering |
| `theme/assets/notification-system.js` | Fallback notification system loaded in standard-page.html |
| `theme/assets/webauthn-helper.js` | Used by LoginForm and LauncherForm for WebAuthn |
| `.auto-claude/` | AI development framework, contains worktrees and specs |

---

## Summary

- **Files to delete**: 10 items (including 2 folders with 16 files total)
- **Files to archive**: 22 stale documentation files
- **Files confirmed used**: All remaining files verified as active dependencies
