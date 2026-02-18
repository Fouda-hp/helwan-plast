# Cleanup Log — Helwan Plast ERP

**Date**: 2026-02-18
**Restore Branch**: `safety/restore_pre_cleanup` (at commit `1cad993`)

---

## Deleted Files

| # | File | Reason | Dependency Proof |
|---|---|---|---|
| 1 | `tmp_mod.py` | One-off script referencing old path | `grep -r "tmp_mod" *.py` = 0 results |
| 2 | `schema.txt` | Empty file (0 content) | Not referenced in any file |
| 3 | `server_code/schema_export.py` | No callable, no imports | `grep -r "schema_export" *.py` = 0 results |
| 4 | `server_code/access_policy.py` | No callable, no imports | `grep -r "access_policy" *.py` = 0 results |
| 5 | `theme/assets/Calculator/.gitkeep` | Dir has 9 real files | Git marker no longer needed |
| 6 | `_ul` | Empty marker | Not used by Anvil framework |
| 7 | `_UL-Fouda-Pc` | Empty marker | Not used by Anvil framework |

## Deleted Folders

| # | Folder | Files Inside | Reason |
|---|---|---|---|
| 1 | `theme/assets/js_originals_backup/` | 12 JS files | Duplicate backups; git tracks history |
| 2 | `theme/assets/originals_backup/` | 4 PNG files | Duplicate backups; git tracks history |
| 3 | `client_code/ImportCSV/` | 0 files | Empty directory |

## Archived Files (moved to `_archive/`)

22 stale root documentation files moved. Not deleted — available for reference.

| # | File | Original Location |
|---|---|---|
| 1 | `AUDIT_FIX_PLAN.md` | root |
| 2 | `BACKUP_SCHEDULE.md` | root |
| 3 | `CONNECTION_AND_PERFORMANCE.md` | root |
| 4 | `CONTRACTS_SAVE_REFERENCE.md` | root |
| 5 | `CURRENT_PROJECT_STATUS_REPORT.md` | root |
| 6 | `DEBUG_REPORT.md` | root |
| 7 | `DETAILED_PROJECT_REVIEW_REPORT.md` | root |
| 8 | `ENTERPRISE_CHANGES.md` | root |
| 9 | `FULL_PROJECT_REVIEW_AND_DEBUG.md` | root |
| 10 | `INSPECTION_REPORT.md` | root |
| 11 | `MIGRATION_PLAN.md` | root |
| 12 | `MOBILE_INPUT_TYPES_SUMMARY.md` | root |
| 13 | `OTP_CHANNEL_SETUP.md` | root |
| 14 | `PROJECT_ARCHITECTURE_AND_FLOW.md` | root |
| 15 | `PROJECT_EVALUATION_REPORT.md` | root |
| 16 | `PROJECT_REVIEW_REPORT.md` | root |
| 17 | `PROJECT_STATUS_AND_LINE_REVIEW.md` | root |
| 18 | `PUBLISH_ANVIL.md` | root |
| 19 | `REVIEW_REPORT_DETAILED.md` | root |
| 20 | `ROLES_AND_PERMISSIONS.md` | root |
| 21 | `SECRETS.md` | root |
| 22 | `مراجعة_السيناريوهات_والمشاكل.md` | root |

## Summary

- **Files deleted**: 7 individual files + 16 files in 2 backup folders = **23 files**
- **Folders deleted**: 3
- **Files archived**: 22 (moved to `_archive/`)
- **Restore point**: Branch `safety/restore_pre_cleanup` at `1cad993`
