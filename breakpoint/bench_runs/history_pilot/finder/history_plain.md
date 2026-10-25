# Advisory sets: plain arm [raw]  (22 sets, 66 runs)

- Each set is one advisory: the repository one commit before the maintainers' fix, labelled by the lines the fix changed.
- 'Location' = a candidate's cited lines fall in the lines the fix changed (before the code check; over-credits and under-credits). 'Read yes / partial' = a person read the candidates: yes describes the advisory's flaw, partial is the right place and class with a different or vaguer mechanism. 'Kept (read)' = the same judgement on findings that survived the code check. Trust the read columns.
- One flaw per set: a single set says little, the total over many sets says something. Every advisory in the selection log (selection.json) is counted, not only the ones that worked.
- Some sets are not fully read yet: adjudicated columns count only fully read sets.

| Advisory | Package | Class | Candidates | Location | Read yes | Read partial | Kept (location) | Kept (read) | Kept | Real other | Wrong | Calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ghsa-2933-q333-qg83 | i18next-fs-backend | prototype-pollution | 15 | 1/3 | 1/3 | 0/3 | 1/3 | - | 15 | - | - | 1 |
| ghsa-5846-7qm3-r52j | dssrf | ssrf | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-5gmw-xhrv-c9v3 | tinypool | prototype-pollution | 15 | 1/3 | 0/3 | 1/3 | 1/3 | - | 15 | - | - | 1 |
| ghsa-6m44-fpc8-c3rq | mistune | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-73wf-gq98-2v4g | browserslist | prototype-pollution | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-83w8-p2f5-377r | @fastify/static | path-traversal | 15 | 3/3 | 1/3 | 2/3 | 3/3 | - | 15 | - | - | 1 |
| ghsa-8r9p-f939-6h3c | follow-redirects | disclosure | 15 | 0/3 | 0/3 | 2/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-8x88-c5mf-7j5w | tar | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-9m6g-wc8r-q59c | scim-patch | prototype-pollution | 15 | 0/3 | 3/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-9v7f-9g4p-ffgj | PyJWT | disclosure | 15 | 0/3 | 0/3 | 2/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-c83g-rgw3-j3cx | browserslist | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-c96f-x56v-gq3h | find-my-way | prototype-pollution | 15 | 1/3 | 0/3 | 0/3 | 1/3 | - | 15 | - | - | 1 |
| ghsa-f2hq-32vh-53cc | postal-mime | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-g3jj-5cmm-3hxx | fast-jwt | crypto | 15 | 1/3 | 0/3 | 1/3 | 1/3 | - | 15 | - | - | 1 |
| ghsa-jqcg-44mw-7w3h | proxy-addr | authentication | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-mxm6-v9r6-r94c | @nuxtjs/mdc | xss | 15 | 2/3 | 0/3 | 2/3 | 2/3 | - | 15 | - | - | 1 |
| ghsa-pm4m-ph32-ghv5 | js-yaml | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-pqg4-j6r4-53mv | shell-quote | injection | 15 | 0/3 | 0/3 | 2/3 | 0/3 | - | 15 | - | - | 1 |
| ghsa-r9w8-h9r3-54w4 | devalue | other | 15 | 3/3 | 0/3 | 2/3 | 3/3 | - | 15 | - | - | 1 |
| ghsa-wc9g-mqfw-jrwm | multer | other | 15 | 3/3 | 0/3 | 3/3 | 3/3 | - | 15 | - | - | 1 |
| ghsa-xcpc-8h2w-3j85 | adm-zip | dos | 15 | 1/3 | 1/3 | 0/3 | 1/3 | - | 15 | - | - | 1 |
| ghsa-xjh9-v7x6-24jw | @fastify/busboy | dos | 15 | 0/3 | 0/3 | 0/3 | 0/3 | - | 15 | - | - | 1 |

**Read by a person (22 sets, 66 runs):** a candidate described the advisory's flaw in 6/66 runs (strict), and described it or was in the right place and class in 23/66 (lenient). By set: 4 of 22 sets strict, 12 of 22 lenient, in at least one of their runs.

**Total over 22 sets (66 runs):** location match 16/66; kept by location 16/66; not yet read by a person; 990 findings kept in all, about 66 model calls.
