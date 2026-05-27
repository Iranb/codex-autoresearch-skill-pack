# Negative Evidence Protocol

Negative evidence can be:

- direct hit showing prior art already solves the target problem
- adjacent hit showing strong novelty risk
- searched query with no direct hit and explicit `absence_confidence`
- provider/live discovery snippet indicating risk

If no negative evidence is found:

1. Record searched queries.
2. Record filters/time window.
3. Record `absence_confidence`.
4. Add recommended next queries.
5. Mark idea as `open_with_constraints`, not `novel_by_default`.
