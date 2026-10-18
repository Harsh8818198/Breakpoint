# nodegoat [hints]  (13 known bugs, 13 distinct issues kept across all runs)

- DEV SET: this repository was used while building Breakpoint. Do not quote these numbers as held-out.
- Contamination: Public since 2014 and one of the most reproduced vulnerable apps; models have very likely seen it. Its code comments also name the bugs ('Fix for A8 - CSRF') and its tutorial pages explain them: use the cleaned variants.
- Fewer than 3 runs for plain: run-to-run spread is not meaningful.
- Labels: 13 bugs labelled by Claude from the source and the project's tutorial, line ranges checked by reading; one reader, not independently reviewed.

| Arm | Runs | Bugs found (mechanical) | Bugs found (adjudicated) | Kept | Precision | Calls | Est. tokens | Seconds | Calls per bug found |
|---|---|---|---|---|---|---|---|---|---|
| plain | 1 | 10.0 of 13 | 9.0 of 13 | 13 | 85% | 46 | 406596 | 33489 | 5.1 (adjudicated) |

## Per known bug (runs that found it / runs)

| Bug | plain |
|---|---|
| Remote code execution through unsafe evaluation of contribution amount | 0/1 |
| Any logged-in user can read other users' retirement allocations | 0/1 |
| Open redirect on the learning-resources link | 1/1 |
| NoSQL injection in the allocations threshold filter | 1/1 |
| Cross-site scripting because template auto-escaping is disabled | 1/1 |
| Server-side request forgery in the research page | 1/1 |
| No server-side CSRF protection on state-changing forms | 1/1 |
| Session cookie lacks HttpOnly and Secure flags | 1/1 |
| Session fixation at login | 1/1 |
| Login errors reveal whether a username exists | 0/1 |
| Hard-coded session signing secret | 0/1 |
| User passwords are stored in plaintext in the database | 1/1 |
| Non-admin users can open the admin benefits page | 1/1 |

Estimated tokens are characters / 4. 'Mechanical' counts a bug as found when a kept finding's evidence line falls inside its location; only the adjudicated column reflects what the findings actually say.
