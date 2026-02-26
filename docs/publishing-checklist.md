# Publishing Checklist (Public Repo)

Before pushing to GitHub:

- [ ] Run `scripts/sanitize_check.sh`
- [ ] Confirm no real IPs/domains, tokens, phone numbers, or emails are present
- [ ] Confirm `.gitignore` excludes `.env`, `*.log`, `config/`, and any secrets
- [ ] Do **not** commit `.git/` from a previous repo (re-init clean)
- [ ] Remove macOS artifacts: `.DS_Store`, `__MACOSX/`
