# dvna [clean]  (18 known bugs, 12 distinct issues kept across all runs)

- Contamination: Public teaching app since 2017; models have probably seen it and its write-ups. The docs and the in-app 'learn' pages explain every bug: use the cleaned variants.
- Fewer than 3 runs for plain: run-to-run spread is not meaningful.
- Labels: 18 bugs: the project's own documented list (docs/solution) mapped to source lines by Claude; one reader, not independently reviewed. 'Insufficient logging and monitoring' is documented but is an absence with no code location, so it is not a label.

| Arm | Runs | Bugs found (mechanical) | Bugs found (adjudicated) | Kept | Precision | Calls | Est. tokens | Seconds | Calls per bug found |
|---|---|---|---|---|---|---|---|---|---|
| plain | 1 | 14.0 of 18 | 12.0 of 18 | 14 | 100% | 46 | 354493 | 196 | 3.8 (adjudicated) |

## Per known bug (runs that found it / runs)

| Bug | plain |
|---|---|
| SQL injection in the user search query | 1/1 |
| OS command injection in the ping feature | 1/1 |
| Password reset token is predictable (md5 of the login name) | 1/1 |
| Hard-coded session signing secret | 1/1 |
| Admin pages and the users API are open to any logged-in user | 1/1 |
| Users API returns password hashes | 1/1 |
| XML external entity injection in the bulk product upload | 1/1 |
| Edit-user takes the target user id from the request body, not the sess | 0/1 |
| Calculator errors are not handled and reach the user | 0/1 |
| Server announces itself in the X-Powered-By header | 0/1 |
| Reflected XSS: the product search term is rendered unescaped | 0/1 |
| Stored XSS: product fields are rendered unescaped | 1/1 |
| DOM XSS: user fields are written with innerHTML | 0/1 |
| Insecure deserialization of an uploaded file (node-serialize) | 1/1 |
| Remote code execution through mathjs.eval on user input (vulnerable ma | 1/1 |
| No CSRF protection on state-changing routes | 1/1 |
| Open redirect: /app/redirect sends the user to any url | 1/1 |
| Every SQL query, including user input, is logged by Sequelize | 0/1 |

Estimated tokens are characters / 4. 'Mechanical' counts a bug as found when a kept finding's evidence line falls inside its location; only the adjudicated column reflects what the findings actually say.
